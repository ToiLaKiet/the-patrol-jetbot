"""Record camera frames and the latest motor command without blocking teleop."""

import csv
from datetime import datetime
from pathlib import Path
import tempfile
from threading import Event, Thread
import time

import cv2


class TeachRecorder:
    def __init__(self, camera, motors, directory):
        self.camera = camera
        self.motors = motors
        self.directory = Path(directory)
        self._stop = Event()
        self._thread = None
        self._error = None

    def start(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(
            prefix=datetime.now().strftime("run_%Y%m%d_%H%M%S_"),
            dir=str(self.directory),
        ))
        (self.directory / "images").mkdir()
        self._started = time.monotonic()
        self._thread = Thread(target=self._run, name="teach-recorder", daemon=True)
        self._thread.start()
        print("Teach recording:", self.directory)

    def _run(self):
        try:
            with (self.directory / "samples.csv").open("x", newline="") as output:
                writer = csv.writer(output)
                writer.writerow(["image", "frame_read_s", "command_s", "left", "right"])
                index = 0
                while not self._stop.is_set():
                    command_t, left, right = self.motors.last_command
                    # shortcut: read time approximates capture time; use sensor timestamps for precise alignment.
                    frame_t = time.monotonic()
                    frame = self.camera.get_frame()
                    filename = "images/{:06d}.jpg".format(index)
                    if not cv2.imwrite(str(self.directory / filename), frame):
                        raise OSError("Cannot write teach image: " + filename)
                    writer.writerow([
                        filename, frame_t - self._started,
                        command_t - self._started, left, right,
                    ])
                    output.flush()
                    index += 1
                    self._stop.wait(max(0.0, 0.2 - (time.monotonic() - frame_t)))
        except Exception as error:
            self._error = error
            self._stop.set()

    def check(self):
        if self._error is not None:
            raise RuntimeError("Teach recording failed") from self._error

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self.check()
