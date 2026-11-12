import csv
from pathlib import Path
import tempfile
from threading import Event
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from teach.recorder import TeachRecorder


class TeachRecorderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.camera = Mock()
        self.camera.get_frame.return_value = np.full((12, 16, 3), 100, dtype=np.uint8)
        self.motors = SimpleNamespace(last_command=(time.monotonic(), 0.1, -0.2))
        self.recorder = TeachRecorder(self.camera, self.motors, self.root)

    def test_images_match_csv_and_commands_include_stop(self):
        written = Event()
        original_write = cv2.imwrite

        def write(*args):
            result = original_write(*args)
            written.set()
            return result

        with patch("teach.recorder.cv2.imwrite", side_effect=write):
            self.recorder.start()
            try:
                self.assertTrue(written.wait(2), "First image was not written")
                written.clear()
                self.motors.last_command = (time.monotonic(), 0.0, 0.0)
                self.assertTrue(written.wait(2), "Stop image was not written")
            finally:
                self.recorder.close()

        with (self.recorder.directory / "samples.csv").open(newline="") as source:
            rows = list(csv.DictReader(source))
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual((float(rows[0]["left"]), float(rows[0]["right"])), (0.1, -0.2))
        self.assertEqual((float(rows[-1]["left"]), float(rows[-1]["right"])), (0, 0))
        self.assertEqual(len(rows), len(list((self.recorder.directory / "images").glob("*.jpg"))))
        for row in rows:
            self.assertIsNotNone(cv2.imread(str(self.recorder.directory / row["image"])))
            self.assertGreaterEqual(float(row["frame_read_s"]), 0)
            self.assertLessEqual(float(row["command_s"]), float(row["frame_read_s"]))
        self.assertLess(float(rows[0]["frame_read_s"]), float(rows[-1]["frame_read_s"]))

    def test_camera_and_image_write_failures_are_reported_without_csv_sample(self):
        for failure in ("camera", "write", "disk"):
            with self.subTest(failure=failure):
                recorder = TeachRecorder(self.camera, self.motors, self.root)
                self.camera.get_frame.side_effect = OSError("Camera lost") if failure == "camera" else None
                with patch("teach.recorder.cv2.imwrite", return_value=False,
                           side_effect=OSError("Disk full") if failure == "disk" else None):
                    recorder.start()
                    self.assertTrue(recorder._stop.wait(2), "Recording error was not detected")
                    with self.assertRaises(RuntimeError) as caught:
                        recorder.close()
                self.assertIsInstance(caught.exception.__cause__, OSError)
                with (recorder.directory / "samples.csv").open(newline="") as source:
                    self.assertEqual(list(csv.DictReader(source)), [])

    def test_sessions_never_overwrite_each_other(self):
        directories = []
        for _ in range(2):
            recorder = TeachRecorder(self.camera, self.motors, self.root)
            recorder.start()
            recorder.close()
            directories.append(recorder.directory)
        self.assertNotEqual(*directories)
        self.assertTrue(all((directory / "samples.csv").exists() for directory in directories))


if __name__ == "__main__":
    unittest.main()
