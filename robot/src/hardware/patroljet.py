
from .camera import JetCamera
from .motors import JetMotors
from safety.safety import SafetyLayer
from teleop.teleop import Teleop


class PatrolJet:
    def __init__(self, name: str):
        self.name = name

        self.camera = JetCamera()
        self.motors = JetMotors()
        self.safety = SafetyLayer()
        self.teleop = None

        print(f"PatrolJet {self.name} initialized.")

    def start(self):
        self.camera.start()
        self.motors.stop()

    def stop(self):
        if self.teleop is not None:
            self.teleop.stop()
        else:
            self.motors.stop()

    def run_teleop(self, max_speed=0.25):
        self.teleop = Teleop(self.motors, self.safety, max_speed=max_speed)
        self.teleop.run()

    def close(self):
        try:
            self.stop()
        finally:
            self.camera.stop()
