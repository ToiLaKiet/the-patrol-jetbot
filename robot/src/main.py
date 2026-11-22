import argparse
import math
import os
import platform

# NumPy 1.19.5's bundled OpenBLAS can misdetect the Jetson Nano CPU.
if platform.machine() == "aarch64":
    os.environ.setdefault("OPENBLAS_CORETYPE", "ARMV8")

def main(argv=None):
    parser = argparse.ArgumentParser(description="Điều khiển JetBot bằng tay cầm USB.")
    parser.add_argument("--max-speed", type=float, default=0.1,
                        help="Giới hạn lệnh motor (0, 1], còn bị chặn bởi max_duty (mặc định: 0.1).")
    parser.add_argument("--deadzone", type=float, default=0.08,
                        help="Vùng chết joystick [0, 1) (mặc định: 0.08).")
    parser.add_argument("--slew-rate", type=float, default=0.5,
                        help="Mức thay đổi lệnh motor mỗi giây, > 0 (mặc định: 0.5).")
    parser.add_argument("--teach-dir", help="Thư mục lưu phiên teach: ảnh và CSV ở khoảng 5 Hz.")
    args = parser.parse_args(argv)
    if not (math.isfinite(args.max_speed) and 0 < args.max_speed <= 1):
        parser.error("--max-speed phải hữu hạn và trong khoảng (0, 1].")
    if not (math.isfinite(args.deadzone) and 0 <= args.deadzone < 1):
        parser.error("--deadzone phải hữu hạn và trong khoảng [0, 1).")
    if not (math.isfinite(args.slew_rate) and args.slew_rate > 0):
        parser.error("--slew-rate phải hữu hạn và lớn hơn 0.")

    from hardware.patroljet import PatrolJet

    robot = PatrolJet("Patrol-01")
    try:
        robot.run_teleop(max_speed=args.max_speed, deadzone=args.deadzone,
                         slew_rate=args.slew_rate, teach_dir=args.teach_dir)
    finally:
        robot.close()


if __name__ == "__main__":
    main()
