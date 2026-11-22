from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cv2

with patch.dict("sys.modules", {"jetbot": SimpleNamespace(Robot=Mock(), Camera=Mock())}):
    import hardware.camera as camera_module


class CameraTests(unittest.TestCase):
    def test_missing_gstreamer_reports_cause_before_opening_camera(self):
        for build in ("    GStreamer: NO\n", "Video I/O:\n    FFMPEG: YES\n"):
            with self.subTest(build=build), \
                    patch.object(cv2, "getBuildInformation", return_value=build), \
                    patch.object(camera_module, "Camera") as backend:
                camera = camera_module.JetCamera()
                with self.assertRaisesRegex(RuntimeError, "OpenCV has no GStreamer support"):
                    camera.start()
                backend.instance.assert_not_called()
                self.assertIsNone(camera.camera)

    def test_gstreamer_build_opens_once_and_closes_camera(self):
        with patch.object(cv2, "getBuildInformation",
                   return_value="    GStreamer: YES (1.14.5)\n"), \
                patch.object(camera_module, "Camera") as backend:
            camera = camera_module.JetCamera(width=320, height=240)
            camera.start()
            camera.start()
            backend.instance.assert_called_once_with(width=320, height=240)
            camera.stop()
            backend.instance.return_value.stop.assert_called_once()
            self.assertIsNone(camera.camera)


if __name__ == "__main__":
    unittest.main()
