"""USB teleoperation using normalized motor commands, not physical velocities."""

import math
import os
import time

from safety.safety import SafetyInput


class Teleop:
    L1_BUTTON = 4

    def __init__(self, motors, safety, max_speed=0.25, deadzone=0.08, slew_rate=0.5):
        if not all(math.isfinite(x) for x in (max_speed, deadzone, slew_rate)):
            raise ValueError("Teleop parameters must be finite")
        if not (0 < max_speed <= 1 and 0 <= deadzone < 1 and slew_rate > 0):
            raise ValueError("Invalid teleop parameters")
        if not math.isfinite(safety.cfg.cmd_timeout) or safety.cfg.cmd_timeout <= 0:
            raise ValueError("Command timeout must be finite and positive")
        self.motors = motors
        self.safety = safety
        self.max_speed = min(max_speed, motors.max_duty)
        self.deadzone = deadzone
        self.slew_rate = slew_rate
        self.safety_input = SafetyInput(
            now=0.0, last_cmd_t=0.0, need_localization=False, battery=None,
        )
        self._running = False
        self._reset()

    def _reset(self):
        self._armed = False
        self._left = self._right = 0.0

    def _axis(self, value):
        magnitude = max(0.0, (abs(value) - self.deadzone) / (1 - self.deadzone))
        return math.copysign(magnitude, value)

    def _command(self, x, y, enabled, dt):
        if not all(math.isfinite(v) for v in (x, y, dt)) or not (
            -1 <= x <= 1 and -1 <= y <= 1 and dt >= 0
        ):
            self._reset()
            raise ValueError("Invalid controller input or elapsed time")
        if dt > self.safety.cfg.cmd_timeout:
            self._reset()
            return 0.0, 0.0
        if not enabled:
            self._armed = abs(x) <= self.deadzone and abs(y) <= self.deadzone
            self._left = self._right = 0.0
            return 0.0, 0.0
        if not self._armed:
            return 0.0, 0.0

        forward, turn = -self._axis(y), self._axis(x)
        # Reduce steering sensitivity near center while retaining full-scale turns.
        turn *= abs(turn)
        left, right = forward + turn, forward - turn
        scale = max(1.0, abs(left), abs(right))
        left, right = self.max_speed * left / scale, self.max_speed * right / scale
        step = self.slew_rate * dt
        self._left += max(-step, min(step, left - self._left))
        self._right += max(-step, min(step, right - self._right))
        return self._left, self._right

    def stop(self):
        self._running = False
        self._reset()
        self.motors.stop()

    def run(self):
        pygame = None
        try:
            self.stop()
            os.environ["SDL_LINUX_JOYSTICK_CLASSIC"] = "1"
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
            import pygame

            pygame.display.init()
            pygame.joystick.init()
            if pygame.joystick.get_count() == 0:
                raise RuntimeError("Không tìm thấy tay cầm USB")
            controller = pygame.joystick.Joystick(0)
            controller.init()
            if controller.get_numaxes() < 2 or controller.get_numbuttons() <= self.L1_BUTTON:
                raise RuntimeError(f"Tay cầm không đủ axis 0/1 và button {self.L1_BUTTON}")
            instance_id = controller.get_instance_id()
            print(f"Teleop: {controller.get_name()}, max_speed={self.max_speed:g}")
            print(f"Đưa cần về giữa, thả L1/button {self.L1_BUTTON} rồi giữ L1 để chạy. Ctrl+C để thoát.")
            print("Chưa giám sát pin. Thả L1 để dừng ngay.")
            clock = pygame.time.Clock()
            last_cmd_t = time.monotonic()
            self._running = True
            while self._running:
                released = False
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        print(f"SDL yêu cầu thoát; dừng teleop. Sự kiện: {event}")
                        return
                    if getattr(event, "instance_id", None) != instance_id:
                        continue
                    if event.type == pygame.JOYDEVICEREMOVED:
                        raise RuntimeError("Tay cầm đã ngắt kết nối")
                    if event.type == pygame.JOYBUTTONUP and event.button == self.L1_BUTTON:
                        released = True
                if pygame.joystick.get_count() == 0:
                    raise RuntimeError("Tay cầm đã ngắt kết nối")
                x, y = controller.get_axis(0), controller.get_axis(1)
                enabled = bool(controller.get_button(self.L1_BUTTON)) and not released
                now = time.monotonic()
                left, right = self._command(x, y, enabled, now - last_cmd_t)
                self.safety_input.last_cmd_t = last_cmd_t
                self.safety_input.now = time.monotonic()
                previous_reason = self.safety.reason
                reason = self.safety.check(self.safety_input)
                if reason != "OK":
                    self._reset()
                    self.motors.stop()
                    if reason != previous_reason:
                        print("Dừng an toàn:", reason)
                elif not self._running or (left == 0.0 and right == 0.0):
                    self.motors.stop()
                else:
                    self.motors.set_motors(left, right)
                last_cmd_t = now
                clock.tick(50)
        except KeyboardInterrupt:
            print("Đã dừng teleop.")
        finally:
            try:
                self.stop()
            finally:
                if pygame is not None:
                    pygame.quit()
