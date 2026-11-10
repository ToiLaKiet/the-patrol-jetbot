import contextlib
import io
import math
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from safety.safety import SafetyConfig, SafetyInput, SafetyLayer
from teleop.teleop import Teleop

with patch.dict("sys.modules", {"jetbot": SimpleNamespace(Robot=Mock(), Camera=Mock())}):
    from hardware.motors import JetMotors
    import hardware.patroljet as patroljet


class TeleopTests(unittest.TestCase):
    def setUp(self):
        self.motors = Mock(max_duty=0.4)
        self.teleop = Teleop(self.motors, SafetyLayer())

    def arm(self):
        self.teleop._command(0, 0, False, 0.02)

    def test_requires_neutral_and_released_l1(self):
        self.assertEqual(self.teleop._command(0, -1, True, 0.02), (0, 0))
        self.teleop._command(0, -1, False, 0.02)
        self.assertEqual(self.teleop._command(0, -1, True, 0.02), (0, 0))
        self.arm()
        self.assertEqual(self.teleop._command(0, -1, True, 0.02), (0.01, 0.01))

    def test_mapping_and_saturation(self):
        cases = [(0, -1, (0.25, 0.25)), (0, 1, (-0.25, -0.25)),
                 (1, 0, (0.25, -0.25)), (-1, 0, (-0.25, 0.25)),
                 (1, -1, (0.25, 0)), (0.5, -1, None)]
        for x, y, expected in cases:
            with self.subTest(x=x, y=y):
                self.arm()
                left, right = self.teleop._command(x, y, True, 1.0)
                if expected is not None:
                    self.assertEqual((left, right), expected)
                else:
                    self.assertGreater(left, right)
                    self.assertGreater(right, 0)
                    self.assertLessEqual(left, 0.25)

    def test_deadzone_continuity(self):
        for value in (-0.08, 0, 0.08):
            self.assertEqual(self.teleop._axis(value), 0)
        self.assertAlmostEqual(self.teleop._axis(0.54), 0.5)
        self.assertAlmostEqual(self.teleop._axis(-0.54), -0.5)
        self.assertLess(self.teleop._axis(0.080001), 0.00001)

    def test_slew_reversal_and_immediate_release(self):
        self.arm()
        self.assertEqual(self.teleop._command(0, -1, True, 0.1), (0.05, 0.05))
        self.assertEqual(self.teleop._command(0, 1, True, 0.1), (0, 0))
        self.assertEqual(self.teleop._command(0, 1, True, 0.1), (-0.05, -0.05))
        self.assertEqual(self.teleop._command(0, 1, False, 0.001), (0, 0))
        self.assertEqual(self.teleop._command(0, 1, True, 0.1), (0, 0))

    def test_timeout_requires_rearming(self):
        self.arm()
        self.teleop._command(0, -1, True, 0.1)
        self.assertEqual(self.teleop._command(0, -1, True, 1.1), (0, 0))
        self.assertEqual(self.teleop._command(0, -1, True, 0.02), (0, 0))

    def test_invalid_inputs_and_configuration(self):
        for params in ({"max_speed": 0}, {"max_speed": 1.1}, {"deadzone": 1},
                       {"deadzone": -0.1}, {"slew_rate": 0}, {"slew_rate": math.inf},
                       {"max_speed": math.nan}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                Teleop(self.motors, SafetyLayer(), **params)
        for values in ((math.nan, 0, 0.02), (0, math.inf, 0.02),
                       (1.1, 0, 0.02), (0, -1.1, 0.02), (0, 0, -1)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.teleop._command(values[0], values[1], True, values[2])
            self.assertFalse(self.teleop._armed)
        self.assertEqual(Teleop(self.motors, SafetyLayer(), max_speed=1).max_speed, 0.4)

    def run_frames(self, frames, count=1, axes=6, buttons=15):
        pygame = Mock()
        for i, name in enumerate(("QUIT", "JOYDEVICEREMOVED", "JOYBUTTONUP")):
            setattr(pygame, name, i)
        controller = pygame.joystick.Joystick.return_value
        pygame.joystick.get_count.return_value = count
        controller.get_numaxes.return_value = axes
        controller.get_numbuttons.return_value = buttons
        controller.get_instance_id.return_value = 42
        controller.get_name.return_value = "TGZ Controller"
        controller.get_attached.return_value = True
        self.fake_pygame = pygame
        self.now = 10.0
        frames = iter(frames)

        def get_events():
            try:
                frame = next(frames)
            except StopIteration:
                raise KeyboardInterrupt
            self.now += frame.get("dt", 0.02)
            controller.get_axis.side_effect = lambda axis: frame.get("x" if axis == 0 else "y", 0)
            controller.get_button.return_value = frame.get("enabled", False)
            controller.get_attached.return_value = frame.get("attached", True)
            self.teleop.safety_input.estop = frame.get("estop", False)
            return frame.get("events", [])

        pygame.event.get.side_effect = get_events
        with patch.dict("sys.modules", {"pygame": pygame}), \
                patch("teleop.teleop.time.monotonic", side_effect=lambda: self.now), \
                contextlib.redirect_stdout(io.StringIO()):
            self.teleop.run()

    def test_run_holds_command_without_axis_events_and_stops_on_release(self):
        self.run_frames([{}, {"y": -1, "enabled": True},
                         {"y": -1, "enabled": True}, {"y": -1}])
        writes = self.motors.set_motors.call_args_list
        self.assertEqual(len(writes), 2)
        self.assertAlmostEqual(writes[0].args[0], 0.01)
        self.assertAlmostEqual(writes[1].args[0], 0.02)
        self.assertEqual(self.motors.mock_calls[-1][0], "stop")
        self.fake_pygame.quit.assert_called_once()

    def test_release_event_is_not_lost_when_repressed_within_same_poll(self):
        release = SimpleNamespace(type=2, instance_id=42, button=6)
        self.run_frames([{}, {"y": -1, "enabled": True},
                         {"y": -1, "enabled": True, "events": [release]},
                         {"y": -1, "enabled": True}])
        self.assertEqual(self.motors.set_motors.call_count, 1)

    def test_safety_stop_and_delayed_loop_require_rearming(self):
        for fault in ({"estop": True}, {"dt": 1.1}):
            with self.subTest(fault=fault):
                self.motors.reset_mock()
                self.run_frames([{}, {"y": -1, "enabled": True},
                                 {"y": -1, "enabled": True, **fault},
                                 {"y": -1, "enabled": True}])
                self.assertEqual(self.motors.set_motors.call_count, 1)

    def test_connection_and_input_failures_stop_and_cleanup(self):
        for frames, kwargs in (([], {"count": 0}), ([], {"buttons": 6}),
                               ([{"attached": False}], {}),
                               ([{"x": math.nan}], {}),
                               ([{"events": [SimpleNamespace(type=1, instance_id=42)]}], {})):
            with self.subTest(frames=frames, kwargs=kwargs):
                self.motors.reset_mock()
                with self.assertRaises((ValueError, RuntimeError)):
                    self.run_frames(frames, **kwargs)
                self.motors.set_motors.assert_not_called()
                self.assertEqual(self.motors.mock_calls[-1][0], "stop")
                self.fake_pygame.quit.assert_called_once()


class SafetyAndMotorTests(unittest.TestCase):
    def test_safety_priority_and_velocity_limits(self):
        safety = SafetyLayer()
        self.assertEqual(safety.filter(1, -2, SafetyInput(0, 0)), (0.3, -1.6, "OK"))
        cases = [(dict(estop=True, battery=0), "ESTOP"),
                 (dict(last_cmd_t=-2, battery=0), "CMD_TIMEOUT"),
                 (dict(battery=0, localized=False), "BATTERY_CRITICAL"),
                 (dict(localized=False), "LOCALIZATION_LOST"),
                 (dict(need_camera=True, camera_ok=False), "CAMERA_LOST"),
                 (dict(battery=math.nan), "INVALID_BATTERY")]
        for values, reason in cases:
            params = dict(now=0, last_cmd_t=0)
            params.update(values)
            with self.subTest(reason=reason):
                self.assertEqual(safety.filter(1, 1, SafetyInput(**params)), (0, 0, reason))
        self.assertEqual(safety.filter(0, 0, SafetyInput(2, 0)), (0, 0, "OK"))
        self.assertEqual(safety.filter(0, 0, SafetyInput(0, 0, estop=True)), (0, 0, "ESTOP"))
        self.assertEqual(safety.check(SafetyInput(0, 0, battery=None)), "OK")
        self.assertEqual(safety.filter(math.nan, 0, SafetyInput(0, 0))[2], "INVALID_COMMAND")

    def test_motor_ratio_limit_validation_and_write_failure(self):
        motors = JetMotors.__new__(JetMotors)
        motors.max_duty = 0.4
        motors.robot = Mock()
        motors.set_motors(0.8, -0.4)
        motors.robot.set_motors.assert_called_once_with(0.4, -0.2)
        motors.robot.reset_mock()
        with self.assertRaises(ValueError):
            motors.set_motors(math.nan, 0)
        motors.robot.set_motors.assert_not_called()
        motors.robot.stop.assert_called_once()
        motors.robot.set_motors.side_effect = OSError("I2C failure")
        with self.assertRaises(OSError):
            motors.set_motors(0.1, 0.1)
        self.assertEqual(motors.robot.stop.call_count, 2)

    def test_patroljet_reuses_motors_and_stops_without_starting_camera(self):
        with patch.object(patroljet, "JetMotors") as motors, \
                patch.object(patroljet, "JetCamera") as camera, \
                patch.object(patroljet, "Teleop") as teleop, \
                contextlib.redirect_stdout(io.StringIO()):
            robot = patroljet.PatrolJet("test")
            teleop.assert_not_called()
            robot.run_teleop(max_speed=0.2)
            teleop.assert_called_once_with(motors.return_value, robot.safety, max_speed=0.2)
            teleop.return_value.run.assert_called_once()
            camera.return_value.start.assert_not_called()
            robot.close()
            teleop.return_value.stop.assert_called_once()
            camera.return_value.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
