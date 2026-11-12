
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
        self.recorder = None

        print(f"PatrolJet {self.name} initialized.")

    def start(self):
        self.camera.start()
        self.motors.stop()

    def stop(self):
        if self.teleop is not None:
            self.teleop.stop()
        else:
            self.motors.stop()

    def run_teleop(self, max_speed=0.25, deadzone=0.08, slew_rate=0.5, teach_dir=None):
        if teach_dir is not None:
            from teach.recorder import TeachRecorder

            self.start()
            self.recorder = TeachRecorder(self.camera, self.motors, teach_dir)
            self.recorder.start()
        self.teleop = Teleop(
            self.motors, self.safety, max_speed=max_speed, deadzone=deadzone, slew_rate=slew_rate,
            recorder=self.recorder,
        )
        self.teleop.run()

    def close(self):
        try:
            self.stop()
        finally:
            try:
                if self.recorder is not None:
                    self.recorder.close()
            finally:
                self.camera.stop()
