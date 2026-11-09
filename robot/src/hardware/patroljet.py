
from .camera import JetCamera
from .motors import JetMotors


class PatrolJet:
    def __init__(self, name: str):
        self.name = name

        self.camera = JetCamera()
        self.motors = JetMotors()

        print(f"PatrolJet {self.name} initialized.")

    def start(self):
        self.camera.start()
        self.motors.stop()

    def stop(self):
        self.motors.stop()

    def close(self):
        try:
            self.motors.stop()
        finally:
            self.camera.stop()
