
import math
from jetbot import Robot


class JetMotors:
    def __init__(
        self,
        duty: float = 0.2,
        max_duty: float = 0.4,
        left_alpha: float = 1.0,
        right_alpha: float = 1.0,
    ):
        # Validate configuration
        params = (duty, max_duty, left_alpha, right_alpha)

        if not all(math.isfinite(x) for x in params):
            raise ValueError("Motor parameters must be finite")

        if not (0 <= duty <= max_duty <= 1 and max_duty > 0):
            raise ValueError("Invalid duty configuration")

        if left_alpha <= 0 or right_alpha <= 0:
            raise ValueError("Motor alpha must be positive")

        self.duty = duty
        self.max_duty = max_duty

        # Initialize NVIDIA JetBot motors
        self.robot = Robot()

        # Motor calibration
        self.robot.left_motor.alpha = left_alpha
        self.robot.right_motor.alpha = right_alpha

        # Ensure robot is stopped
        self.stop()

        print("JetBot motors initialized.")


    def go_forward(self):
        self.set_motors(self.duty, self.duty)

    def go_backward(self):
        self.set_motors(-self.duty, -self.duty)

    def go_left(self):
        self.set_motors(-self.duty, self.duty)

    def go_right(self):
        self.set_motors(self.duty, -self.duty)

    def stop(self):
        self.robot.stop()

    def set_motors(self, left: float, right: float):
        try:
            if not all(math.isfinite(x) for x in (left, right)):
                raise ValueError("Motor commands must be finite")
            scale = max(1.0, abs(left) / self.max_duty, abs(right) / self.max_duty)
            self.robot.set_motors(left / scale, right / scale)
        except Exception:
            self.stop()
            raise

    # =========================
    # Velocity Conversion
    # =========================

    @staticmethod
    def to_wheels(
        v: float,
        w: float,
        wheelbase: float,
        v_full: float,
        max_duty: float = 0.4,
    ):
        """
        Convert (v, w) to normalized wheel commands.

        v: linear velocity [m/s]
        w: angular velocity [rad/s]
        wheelbase: distance between wheels [m]
        v_full: estimated wheel speed at duty=1.0 [m/s]

        Assumes an approximately linear speed-duty mapping.
        """
        params = (v, w, wheelbase, v_full, max_duty)

        if not all(math.isfinite(x) for x in params):
            raise ValueError("Parameters must be finite")

        if wheelbase <= 0 or v_full <= 0:
            raise ValueError("Invalid robot calibration")

        if not (0 < max_duty <= 1):
            raise ValueError("Invalid max_duty")

        # Differential drive kinematics
        vl = v - w * wheelbase / 2
        vr = v + w * wheelbase / 2

        # Convert wheel velocities to commands
        left = vl / v_full
        right = vr / v_full

        # Preserve wheel command ratio when saturating
        k = max(
            1.0,
            abs(left) / max_duty,
            abs(right) / max_duty
        )

        return left / k, right / k

    # =========================
    # Velocity Control
    # =========================

    def drive(
        self,
        v: float,
        w: float,
        wheelbase: float,
        v_full: float,
    ):
        """
        Drive using desired linear and angular velocities.
        """
        left, right = self.to_wheels(
            v=v,
            w=w,
            wheelbase=wheelbase,
            v_full=v_full,
            max_duty=self.max_duty,
        )

        self.set_motors(left, right)

    # =========================
    # Cleanup
    # =========================

    def close(self):
        self.stop()
        print("JetBot motors stopped.")
