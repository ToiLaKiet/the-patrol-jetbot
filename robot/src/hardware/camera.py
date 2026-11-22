import re

import cv2
from jetbot import Camera


class JetCamera:
    def __init__(self, width=224, height=224):
        self.width = width
        self.height = height
        self.camera = None

    def start(self):
        if self.camera is None:
            if not re.search(r"^\s*GStreamer:\s+YES\b", cv2.getBuildInformation(), re.MULTILINE):
                raise RuntimeError(
                    "OpenCV has no GStreamer support: {}. Remove pip OpenCV from .venv "
                    "and use JetPack system OpenCV via --system-site-packages; "
                    "see robot/README.md.".format(cv2.__file__)
                )
            self.camera = Camera.instance(
                width=self.width,
                height=self.height
            )

    def get_frame(self):
        if self.camera is None:
            raise RuntimeError("Camera not started")

        frame = self.camera.value

        if frame is None or frame.size == 0:
            raise RuntimeError("Camera frame unavailable")

        return frame.copy()

    def stop(self):
        if self.camera is not None:
            self.camera.stop()
            self.camera = None
