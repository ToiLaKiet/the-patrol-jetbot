
from .camera import JetCamera
from .motors import JetMotors
from safety.safety import SafetyLayer
from teleop.teleop import Teleop


class PatrolJet:
    def __init__(self, name: str, max_duty=0.4):
        self.name = name

        self.camera = JetCamera()
        self.motors = JetMotors(duty=min(0.2, max_duty), max_duty=max_duty)
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

    def run_teleop(self, max_duty=0.1, deadzone=0.08, slew_rate=0.5, teach_dir=None, l1_button=4):
        if teach_dir is not None:
            from teach.recorder import TeachRecorder

            self.start()
            self.recorder = TeachRecorder(self.camera, self.motors, teach_dir)
            self.recorder.start()
        self.teleop = Teleop(
            self.motors, self.safety, max_duty=max_duty, deadzone=deadzone, slew_rate=slew_rate,
            recorder=self.recorder, l1_button=l1_button,
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

    def run_navigation(self, localizer, model, **options):
        from navigation.live import run_live

        try:
            return run_live(self.camera, self.motors, self.safety, localizer, model, **options)
        finally:
            self.stop()
