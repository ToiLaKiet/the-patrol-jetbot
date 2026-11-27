import re
import threading
import time

import cv2
from jetbot import Camera


class JetCamera:
    def __init__(self, width=224, height=224):
        self.width = width
        self.height = height
        self.camera = None
        self._lock = threading.Lock()
        self._observation = None

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
            self.camera.observe(self._on_frame, names="value")

    def _on_frame(self, change):
        frame = change["new"]
        if frame is not None and frame.size:
            with self._lock:
                self._observation = (time.monotonic(), frame)

    @property
    def last_frame_time(self):
        with self._lock:
            return None if self._observation is None else self._observation[0]

    def get_observation(self):
        """Return (callback monotonic time, BGR copy), or None before a new frame."""
        if self.camera is None:
            raise RuntimeError("Camera not started")
        with self._lock:
            if self._observation is None:
                return None
            timestamp, frame = self._observation
            return timestamp, frame.copy()

    def get_frame(self):
        if self.camera is None:
            raise RuntimeError("Camera not started")

        frame = self.camera.value

        if frame is None or frame.size == 0:
            raise RuntimeError("Camera frame unavailable")

        return frame.copy()

    def stop(self):
        if self.camera is not None:
            try:
                self.camera.unobserve(self._on_frame, names="value")
            finally:
                try:
                    self.camera.stop()
                finally:
                    self.camera = None
                    with self._lock:
                        self._observation = None
