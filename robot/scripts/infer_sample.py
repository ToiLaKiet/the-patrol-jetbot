"""Run PlaceNav checkpoints on image files, without ROS or JetBot hardware."""

import argparse
from collections import OrderedDict
import os
from pathlib import Path
import pickle
import platform
import resource
import statistics
import sys
import time
import types

if platform.machine() == "aarch64":
    os.environ.setdefault("OPENBLAS_CORETYPE", "ARMV8")

import torch
import cv2
from torchvision import models

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from utils import preprocess_frame


class GNMUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        # The published checkpoint uses the original training package's class path.
        if (module, name) == ("gnm_train.models.gnm", "GNM"):
            from placenav.models.wp_models.gnm.gnm import GNM
            return GNM
        return super().find_class(module, name)


def load_gnm(path):
    from placenav.models.wp_models.gnm.gnm import GNM

    checkpoint_pickle = types.ModuleType("gnm_checkpoint_pickle")
    checkpoint_pickle.Unpickler = GNMUnpickler
    checkpoint = torch.load(str(path), map_location="cpu", pickle_module=checkpoint_pickle)
    loaded = checkpoint["model"]
    if isinstance(loaded, torch.nn.DataParallel):
        loaded = loaded.module
    model = GNM()
    model.load_state_dict(loaded.state_dict(), strict=True)
    return model.eval()


def load_cosplace(path):
    from placenav.models.pr_models.cosplace_model.layers import Flatten, GeM, L2Norm

    # Match GeoLocalizationNet's keys while avoiding its extra ImageNet download.
    model = torch.nn.Sequential(OrderedDict([
        ("backbone", torch.nn.Sequential(models.efficientnet_b0(pretrained=False).features)),
        ("aggregation", torch.nn.Sequential(
            L2Norm(), GeM(), Flatten(), torch.nn.Linear(1280, 512), L2Norm(),
        )),
    ]))
    state = torch.load(str(path), map_location="cpu", pickle_module=pickle)
    model.load_state_dict(state, strict=True)
    return model.eval()


def prepare_inputs(paths, goal_path):
    if len(paths) not in (1, 6):
        raise ValueError("Context cần 1 ảnh thử hoặc 6 ảnh theo thứ tự cũ → mới.")
    images = []
    for path in list(paths) + [goal_path]:
        frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if frame is None:
            raise OSError("Không đọc được ảnh: {}".format(path))
        images.append(preprocess_frame(frame))
    context = images[:-1]
    # shortcut: repeating one image only tests inference, use six real frames for navigation.
    if len(context) == 1:
        context *= 6
    return torch.cat(context, dim=0).unsqueeze(0), images[-1].unsqueeze(0)


def check_tensor(name, tensor, shape):
    if tuple(tensor.shape) != shape:
        raise ValueError("{}: shape {} != {}".format(name, tuple(tensor.shape), shape))
    if not torch.isfinite(tensor).all().item():
        raise ValueError("{} có NaN hoặc Inf".format(name))


def report_memory(device):
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 ** 2 if platform.system() == "Darwin" else 1024
    print("Process peak RSS since start: {:.1f} MiB".format(peak / divisor), flush=True)
    status = Path("/proc/self/status")
    if status.is_file():
        for line in status.read_text().splitlines():
            if line.startswith(("VmRSS:", "VmHWM:")):
                print("Process RAM " + line.strip(), flush=True)
    if device.type == "cuda":
        print("PyTorch CUDA allocated/reserved: {:.1f}/{:.1f} MiB; peak: {:.1f}/{:.1f} MiB".format(
            torch.cuda.memory_allocated(device) / 1024 ** 2,
            torch.cuda.memory_reserved(device) / 1024 ** 2,
            torch.cuda.max_memory_allocated(device) / 1024 ** 2,
            torch.cuda.max_memory_reserved(device) / 1024 ** 2,
        ), flush=True)


@torch.no_grad()
def benchmark(loaded, context, goal, device, warmup, runs):
    def forward():
        return {name: model(context, goal) if name == "gnm" else (model(context[:, -3:]),)
                for name, model in loaded.items()}

    def validate(outputs):
        for name, tensors in outputs.items():
            if name == "gnm":
                check_tensor("distance", tensors[0], (1, 1))
                check_tensor("waypoints", tensors[1], (1, 5, 4))
            else:
                check_tensor("descriptor", tensors[0], (1, 512))

    print("Benchmark {}: warmup={}, runs={}; models cùng nằm trong bộ nhớ.".format(
        "+".join(loaded), warmup, runs), flush=True)
    for _ in range(warmup):
        validate(forward())
    if device.type == "cuda":
        torch.cuda.synchronize(device)
        torch.cuda.reset_peak_memory_stats(device)
    elapsed = []
    for _ in range(runs):
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        start = time.perf_counter()
        outputs = forward()
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        elapsed.append((time.perf_counter() - start) * 1000)
        validate(outputs)
        del outputs
    print("Forward {}: mean={:.2f} ms, p50={:.2f} ms, min={:.2f} ms, max={:.2f} ms".format(
        "+".join(loaded), statistics.mean(elapsed), statistics.median(elapsed),
        min(elapsed), max(elapsed)), flush=True)
    report_memory(device)
    print("OK: mọi output đúng shape và hữu hạn; chưa đánh giá độ chính xác navigation.")


def main(argv=None):
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, nargs="+", required=True,
                        help="1 ảnh thử hoặc 6 ảnh từ cũ đến mới (ảnh hiện tại ở cuối).")
    parser.add_argument("--goal", type=Path, required=True, help="Ảnh subgoal cho GNM.")
    parser.add_argument("--model", choices=("gnm", "cosplace", "both"), default="both")
    parser.add_argument("--checkpoint-dir", type=Path, default=root / "checkpoints")
    parser.add_argument("--placenav-dir", type=Path, default=root.parent / "PlaceNav")
    parser.add_argument("--device", choices=("cpu", "cuda"),
                        help="Mặc định dùng CUDA nếu khả dụng, nếu không dùng CPU.")
    parser.add_argument("--benchmark", action="store_true",
                        help="Giữ các model cùng trong bộ nhớ, đo RAM và thời gian forward.")
    parser.add_argument("--warmup", type=int, default=10, help="Số lượt warm-up khi benchmark (>= 1).")
    parser.add_argument("--runs", type=int, default=30, help="Số lượt đo sau warm-up (>= 1).")
    args = parser.parse_args(argv)
    if len(args.context) not in (1, 6):
        parser.error("--context cần đúng 1 hoặc 6 ảnh.")
    if args.warmup < 1 or args.runs < 1:
        parser.error("--warmup và --runs phải >= 1.")
    source = args.placenav_dir.resolve() / "src"
    if not (source / "placenav/models").is_dir():
        parser.error("Thiếu source PlaceNav: {} (dùng --placenav-dir).".format(source))
    checkpoints = {"gnm": "gnm_large.pth", "cosplace": "efficientnet_85x85.pth"}
    selected = ("gnm", "cosplace") if args.model == "both" else (args.model,)
    for name in selected:
        if not (args.checkpoint_dir / checkpoints[name]).is_file():
            parser.error("Thiếu checkpoint: {}".format(args.checkpoint_dir / checkpoints[name]))
    sys.path.insert(0, str(source))
    device = torch.device(args.device or ("cuda" if torch.cuda.is_available() else "cpu"))
    if device.type == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA không khả dụng; kiểm tra môi trường hoặc dùng --device cpu.")
    context, goal = prepare_inputs(args.context, args.goal)
    check_tensor("context", context, (1, 18, 64, 85))
    check_tensor("goal", goal, (1, 3, 64, 85))
    context, goal = context.to(device), goal.to(device)
    print("Device: {} | context: {} | goal: {}".format(
        device, tuple(context.shape), tuple(goal.shape)), flush=True)
    if len(args.context) == 1:
        print("SMOKE TEST: lặp một ảnh 6 lần, không phải context chuyển động thực.", flush=True)
    if args.benchmark:
        loaded = {}
        for name in selected:
            print("Loading {}...".format(name), flush=True)
            path = args.checkpoint_dir / checkpoints[name]
            loaded[name] = (load_gnm(path) if name == "gnm" else load_cosplace(path)).to(device)
        benchmark(loaded, context, goal, device, args.warmup, args.runs)
        return 0
    with torch.no_grad():
        for name in selected:
            print("Loading {}...".format(name), flush=True)
            path = args.checkpoint_dir / checkpoints[name]
            model = (load_gnm(path) if name == "gnm" else load_cosplace(path)).to(device)
            if name == "gnm":
                distance, waypoints = model(context, goal)
                check_tensor("distance", distance, (1, 1))
                check_tensor("waypoints", waypoints, (1, 5, 4))
                print("GNM distance:", distance.cpu().tolist(), flush=True)
                print("GNM waypoints [1, 5, 4]:", waypoints.cpu().tolist(), flush=True)
            else:
                descriptor = model(context[:, -3:])
                check_tensor("descriptor", descriptor, (1, 512))
                print("CosPlace descriptor [1, 512] | L2 norm:",
                      descriptor.norm(dim=1).cpu().tolist(), flush=True)
            del model
    print("OK: output đúng shape và hữu hạn. Chưa đánh giá độ chính xác hoặc benchmark.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
