"""Offline Bayesian localization or GNM navigation to (v, w), without motors."""

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
    parser = argparse.ArgumentParser(description="CosPlace + Bayesian, tùy chọn GNM → (v, w); không mở motor.")
    parser.add_argument("--topomap-dir", type=Path, required=True,
                        help="Thư mục topomap chứa 0.jpg, 1.jpg, ...")
    parser.add_argument("--query", type=Path, required=True,
                        help="Một ảnh hoặc thư mục ảnh tên số, xử lý theo thứ tự thời gian.")
    parser.add_argument("--checkpoint", type=Path, default=Path("checkpoints/efficientnet_85x85.pth"))
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--navigate", action="store_true", help="Chạy thêm GNM và tính (v, w).")
    parser.add_argument("--gnm-checkpoint", type=Path, default=Path("checkpoints/gnm_large.pth"))
    parser.add_argument("--max-v", type=float, help="Giới hạn m/s, bắt buộc khi --navigate.")
    parser.add_argument("--max-w", type=float, help="Giới hạn rad/s, bắt buộc khi --navigate.")
    parser.add_argument("--frame-rate", type=float, default=5.0)
    parser.add_argument("--goal-node-idx", type=int, default=-1, help="-1: node cuối topomap.")
    parser.add_argument("--lookahead", type=int, default=1)
    parser.add_argument("--target-waypoint-idx", type=int, default=2)
    args = parser.parse_args(argv)
    if args.navigate and (args.max_v is None or args.max_w is None):
        parser.error("--navigate cần --max-v và --max-w.")
    try:
        return run(args)
    except (OSError, ValueError, RuntimeError, ImportError) as error:
        parser.error(str(error))


def run(args):
    from navigation.inference import PlaceRecognition, image_paths, read_frame

    queries = image_paths(args.query) if args.query.is_dir() else [args.query]
    if not args.query.exists():
        raise ValueError("Không thấy ảnh query: " + str(args.query))
    if args.navigate:
        from navigation.gnm import load_gnm
        from navigation.navigate import navigate
        from navigation.pd_controller import waypoint_to_velocity

        waypoint_to_velocity([0, 0], args.max_v, args.max_w, args.frame_rate)
        if len(queries) < 6:
            raise ValueError("--navigate cần ít nhất 6 ảnh query theo thứ tự thời gian.")
        localizer = PlaceRecognition(args.topomap_dir, args.checkpoint, args.device)
        model = load_gnm(args.gnm_checkpoint, args.device)
        print("Bayesian + GNM → (v, w); không mở camera/motor. Timestamp giả định theo --frame-rate.",
              flush=True)
        # shortcut: image-only replay assumes fixed cadence; use recorded timestamps for timing evaluation.
        observations = ((index / args.frame_rate, read_frame(path))
                        for index, path in enumerate(queries))
        for result in navigate(
                observations, localizer, model, args.max_v, args.max_w, args.frame_rate,
                args.goal_node_idx, args.lookahead, args.target_waypoint_idx):
            chosen = result["chosen_waypoint"]
            print("t={timestamp:.3f} node={node} posterior={posterior:.4f} subgoal={subgoal} "
                  "v={v:.6f} w={w:.6f} goal={reached_goal} time_ms={time_ms:.1f} waypoint={}".format(
                      None if chosen is None else chosen.tolist(), **result), flush=True)
        return

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
