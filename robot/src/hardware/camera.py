
from jetbot import Camera


class JetCamera:
    def __init__(self, width=224, height=224):
        self.width = width
        self.height = height
        self.camera = None

    def start(self):
        if self.camera is None:
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
