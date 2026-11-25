"""Offline place recognition; waypoint control is not connected yet."""

import argparse
import os
from pathlib import Path
import platform
import sys
import time

if platform.machine() == "aarch64":
    os.environ.setdefault("OPENBLAS_CORETYPE", "ARMV8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Thử CosPlace + Bayesian trên ảnh, chưa điều khiển motor.")
    parser.add_argument("--topomap-dir", type=Path, required=True,
                        help="Thư mục topomap chứa 0.jpg, 1.jpg, ...")
    parser.add_argument("--query", type=Path, required=True,
                        help="Một ảnh hoặc thư mục ảnh tên số, xử lý theo thứ tự thời gian.")
    parser.add_argument("--checkpoint", type=Path, default=Path("checkpoints/efficientnet_85x85.pth"))
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (OSError, ValueError, RuntimeError, ImportError) as error:
        parser.error(str(error))


def run(args):
    from navigation.inference import PlaceRecognition, image_paths, read_frame

    queries = image_paths(args.query) if args.query.is_dir() else [args.query]
    if not args.query.exists():
        raise ValueError("Không thấy ảnh query: " + str(args.query))
    localizer = PlaceRecognition(args.topomap_dir, args.checkpoint, args.device)
    print("Đã nạp {} node. Chỉ định vị trên ảnh; chưa điều khiển motor.".format(len(localizer.map_paths)), flush=True)
    for path in queries:
        frame = read_frame(path)
        started = time.perf_counter()
        node, probability = localizer.match(frame)
        elapsed_ms = (time.perf_counter() - started) * 1000
        print("{} -> node={} posterior={:.4f} time_ms={:.1f}".format(
            path.name, node, probability, elapsed_ms), flush=True)


if __name__ == "__main__":
    main()
