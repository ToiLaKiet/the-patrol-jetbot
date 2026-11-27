"""Check camera callbacks for five seconds, without models or motor imports."""

import os
from pathlib import Path
import platform
import sys
import time

if platform.machine() == "aarch64":
    os.environ.setdefault("OPENBLAS_CORETYPE", "ARMV8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    from hardware.camera import JetCamera

    camera = JetCamera()
    try:
        camera.start()
        started = time.monotonic()
        previous = None
        updates = 0
        while time.monotonic() - started < 5.0:
            observation = camera.get_observation()
            if observation is not None and observation[0] != previous:
                timestamp, frame = observation
                if updates == 0:
                    print("First callback: shape={} dtype={}".format(frame.shape, frame.dtype), flush=True)
                previous = timestamp
                updates += 1
            time.sleep(0.02)
        timestamp = camera.last_frame_time
        age = None if timestamp is None else time.monotonic() - timestamp
        capture_thread = getattr(camera.camera, "thread", None)
        print("Camera: observed_updates={} last_frame_age_s={} capture_thread_alive={}".format(
            updates, age, None if capture_thread is None else capture_thread.is_alive()), flush=True)
        if updates < 2 or age is None or not 0 <= age <= 1.0:
            raise RuntimeError("Camera không cập nhật callback liên tục; kiểm tra stream/camera trước khi chạy motor.")
        print("PASS: nhận nhiều callback và frame cuối còn mới sau phép thử 5 giây.", flush=True)
    finally:
        camera.stop()


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ImportError) as error:
        print("FAIL:", error, file=sys.stderr)
        sys.exit(1)
