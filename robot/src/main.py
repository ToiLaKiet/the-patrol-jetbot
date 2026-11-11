import os
import platform

# NumPy 1.19.5's bundled OpenBLAS can misdetect the Jetson Nano CPU.
if platform.machine() == "aarch64":
    os.environ.setdefault("OPENBLAS_CORETYPE", "ARMV8")

from hardware.patroljet import PatrolJet


def main():
    robot = PatrolJet("Patrol-01")
    try:
        robot.run_teleop(max_speed=0.25)
    finally:
        robot.close()


if __name__ == "__main__":
    main()
