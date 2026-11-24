import argparse
import math
import os
import platform

# NumPy 1.19.5's bundled OpenBLAS can misdetect the Jetson Nano CPU.
if platform.machine() == "aarch64":
    os.environ.setdefault("OPENBLAS_CORETYPE", "ARMV8")

def main(argv=None):
    parser = argparse.ArgumentParser(description="JetBot Teach & Navigation theo PlaceNav.")
    stages = parser.add_subparsers(dest="stage")
    stages.required = True
    teach = stages.add_parser("teach", help="Lái bằng joystick và thu dữ liệu teach.")
    teach.add_argument("--max-duty", "--max-speed", type=float, default=0.1,
                        help="Giới hạn duty chuẩn hóa (0, 1], không phải m/s; "
                             "còn bị chặn bởi motors.max_duty (mặc định: 0.1).")
    teach.add_argument("--deadzone", type=float, default=0.08,
                        help="Vùng chết joystick [0, 1) (mặc định: 0.08).")
    teach.add_argument("--slew-rate", type=float, default=0.5,
                        help="Mức thay đổi lệnh motor mỗi giây, > 0 (mặc định: 0.5).")
    teach.add_argument("--teach-dir", default="teach",
                       help="Thư mục lưu JPEG + CSV ở khoảng 5 Hz (mặc định: teach).")
    stages.add_parser("navigation", help="Inference → subgoal → waypoint → controller (chưa triển khai).")
    args = parser.parse_args(argv)
    if args.stage == "navigation":
        from navigation.main import run
        try:
            return run(args)
        except NotImplementedError as error:
            parser.error(str(error))

    if not (math.isfinite(args.max_duty) and 0 < args.max_duty <= 1):
        teach.error("--max-duty phải hữu hạn và trong khoảng (0, 1].")
    if not (math.isfinite(args.deadzone) and 0 <= args.deadzone < 1):
        teach.error("--deadzone phải hữu hạn và trong khoảng [0, 1).")
    if not (math.isfinite(args.slew_rate) and args.slew_rate > 0):
        teach.error("--slew-rate phải hữu hạn và lớn hơn 0.")

    from teach.main import run
    return run(args)


if __name__ == "__main__":
    main()
