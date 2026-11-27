"""Offline localization/navigation, or live camera -> safety -> motor Repeat."""

import argparse
import math
import os
from pathlib import Path
import platform
import sys
import time

if platform.machine() == "aarch64":
    os.environ.setdefault("OPENBLAS_CORETYPE", "ARMV8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None):
    parser = argparse.ArgumentParser(description="PlaceNav: --query trên ảnh hoặc --live điều khiển motor.")
    parser.add_argument("--topomap-dir", type=Path, required=True,
                        help="Thư mục topomap chứa 0.jpg, 1.jpg, ...")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--query", type=Path,
                        help="Một ảnh hoặc thư mục ảnh tên số, không mở motor.")
    source.add_argument("--live", action="store_true", help="Camera trực tiếp → GNM → safety → motor.")
    parser.add_argument("--checkpoint", type=Path, default=Path("checkpoints/efficientnet_85x85.pth"))
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--navigate", action="store_true", help="Chạy thêm GNM và tính (v, w).")
    parser.add_argument("--gnm-checkpoint", type=Path, default=Path("checkpoints/gnm_large.pth"))
    parser.add_argument("--max-v", type=float, help="Giới hạn m/s, bắt buộc khi --navigate/--live.")
    parser.add_argument("--max-w", type=float, help="Giới hạn rad/s, bắt buộc khi --navigate/--live.")
    parser.add_argument("--frame-rate", type=float, default=5.0)
    parser.add_argument("--goal-node-idx", type=int, default=-1, help="-1: node cuối topomap.")
    parser.add_argument("--lookahead", type=int, default=1)
    parser.add_argument("--target-waypoint-idx", type=int, default=2)
    parser.add_argument("--wheelbase", type=float, help="Khoảng cách hai bánh (m), bắt buộc khi --live.")
    parser.add_argument("--v-full", type=float, help="Vận tốc bánh ước lượng ở duty=1 (m/s), bắt buộc khi --live.")
    parser.add_argument("--max-duty", type=float, default=0.1, help="Giới hạn duty khi --live (mặc định 0.1).")
    parser.add_argument("--min-posterior", type=float, help="Ngưỡng posterior đã thử trên tuyến, bắt buộc khi --live.")
    parser.add_argument("--command-timeout", type=float, default=1.0, help="Tuổi ảnh/waypoint tối đa khi --live (giây).")
    parser.add_argument("--startup-timeout", type=float, default=30.0,
                        help="Ngân sách warm-up và ngân sách chờ waypoint đầu sau khi mở camera (giây, mặc định 30).")
    args = parser.parse_args(argv)
    if (args.navigate or args.live) and (args.max_v is None or args.max_w is None):
        parser.error("--navigate/--live cần --max-v và --max-w.")
    if args.live:
        for name in ("wheelbase", "v_full", "min_posterior"):
            if getattr(args, name) is None:
                parser.error("--live cần --" + name.replace("_", "-"))
        if (not all(math.isfinite(x) and x > 0 for x in (
                args.wheelbase, args.v_full, args.command_timeout, args.startup_timeout,
                args.max_duty, args.min_posterior))
                or args.max_duty > 1 or args.min_posterior > 1):
            parser.error("Hiệu chỉnh/timeout phải hữu hạn và > 0; duty/posterior <= 1.")
    try:
        return run(args)
    except KeyboardInterrupt:
        print("Đã dừng navigation.", flush=True)
    except (OSError, ValueError, RuntimeError, ImportError) as error:
        parser.error(str(error))


def run(args):
    from navigation.inference import PlaceRecognition, image_paths, read_frame

    if args.live:
        from navigation.gnm import load_gnm
        from navigation.pd_controller import waypoint_to_velocity
        from safety.safety import SafetyConfig, SafetyLayer

        waypoint_to_velocity([0, 0], args.max_v, args.max_w, args.frame_rate)
        localizer = PlaceRecognition(args.topomap_dir, args.checkpoint, args.device)
        model = load_gnm(args.gnm_checkpoint, args.device)
        from hardware.patroljet import PatrolJet

        robot = PatrolJet("Patrol-01", max_duty=args.max_duty)
        try:
            robot.safety = SafetyLayer(SafetyConfig(cmd_timeout=args.command_timeout,
                                                   v_max=args.max_v, w_max=args.max_w))
            print("LIVE: motor sẽ chạy sau khi đủ 6 ảnh và định vị đạt ngưỡng. Ctrl+C để dừng.", flush=True)
            robot.run_navigation(
                localizer, model, max_v=args.max_v, max_w=args.max_w,
                wheelbase=args.wheelbase, v_full=args.v_full, min_posterior=args.min_posterior,
                frame_rate=args.frame_rate, goal_node_idx=args.goal_node_idx,
                lookahead=args.lookahead, target_waypoint_idx=args.target_waypoint_idx,
                startup_timeout=args.startup_timeout,
            )
        finally:
            robot.close()
        return

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
                  "v={v:.6f} w={w:.6f} goal={reached_goal} time_ms={time_ms:.1f} "
                  "timings_ms={timings_ms} waypoint={}".format(
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
