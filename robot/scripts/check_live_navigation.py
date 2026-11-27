"""Exercise live motor ownership and failure stops without JetBot hardware."""

import importlib.util
import math
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from navigation.live import run_live
from navigation.main import main
from safety.safety import SafetyConfig, SafetyLayer


class LiveNavigationTests(unittest.TestCase):
    def setUp(self):
        self.owner = threading.get_ident()
        self.motors = Mock()
        self.motors.drive.side_effect = self.check_owner
        self.motors.stop.side_effect = self.check_owner
        self.camera = SimpleNamespace(last_frame_time=None, get_observation=Mock())
        self.safety = SafetyLayer(SafetyConfig(cmd_timeout=0.06, v_max=0.1, w_max=0.6))
        self.model = SimpleNamespace(context_size=0)

    def check_owner(self, *args):
        self.assertEqual(threading.get_ident(), self.owner)

    def result(self, **changes):
        result = dict(timestamp=time.monotonic(), node=0, posterior=0.9, subgoal=1,
                      v=0.2, w=0.8, reached_goal=False, time_ms=1.0)
        result.update(changes)
        return result

    def run_live(self, predict, warmup=None, startup_timeout=0.15):
        with patch("navigation.navigate.navigate", side_effect=predict), patch("builtins.print"), \
                patch("navigation.live._warmup_models", side_effect=warmup):
            return run_live(self.camera, self.motors, self.safety, None, self.model,
                            max_v=0.2, max_w=0.8, wheelbase=0.1, v_full=0.5,
                            min_posterior=0.7, frame_rate=100, startup_timeout=startup_timeout)

    def test_slow_startup_keeps_motors_stopped_then_uses_fresh_frames(self):
        def warmup(*args):
            until = time.monotonic() + 0.12
            while time.monotonic() < until:
                self.camera.last_frame_time = time.monotonic()
                self.motors.drive.assert_not_called()
                threading.Event().wait(0.005)

        def predict(*args):
            self.camera.last_frame_time = time.monotonic()
            yield self.result()
            yield self.result(v=0, w=0, reached_goal=True)

        self.run_live(predict, warmup=warmup, startup_timeout=0.5)
        self.motors.drive.assert_called_once()

    def test_stale_first_prediction_still_stops_with_long_startup_budget(self):
        def predict(*args):
            self.camera.last_frame_time = time.monotonic()
            yield self.result(timestamp=time.monotonic() - 0.2)

        with self.assertRaisesRegex(RuntimeError, "CMD_TIMEOUT"):
            self.run_live(predict, startup_timeout=30)
        self.motors.drive.assert_not_called()

    def test_warmup_failure_stops_without_running_navigation(self):
        predict = Mock()
        with self.assertRaisesRegex(RuntimeError, "warmup failed"):
            self.run_live(predict, warmup=RuntimeError("warmup failed"))
        predict.assert_not_called()
        self.motors.drive.assert_not_called()

    def test_goal_and_clipping_motor_commands_on_main_thread(self):
        def predict(*args):
            self.camera.last_frame_time = time.monotonic()
            yield self.result()
            yield self.result(v=0, w=0, reached_goal=True)

        self.run_live(predict)
        self.motors.drive.assert_called_once_with(0.1, 0.6, 0.1, 0.5)
        self.assertGreaterEqual(self.motors.stop.call_count, 2)

    def test_bad_confidence_and_old_or_future_results_never_drive(self):
        for changes, reason in (({"posterior": 0.2}, "LOCALIZATION_LOST"),
                                ({"timestamp": lambda: time.monotonic() - 2}, "CMD_TIMEOUT"),
                                ({"timestamp": lambda: time.monotonic() + 2}, "INVALID_TIME"),
                                ({"v": math.nan}, "INVALID_COMMAND")):
            with self.subTest(reason=reason):
                def predict(*args):
                    self.camera.last_frame_time = time.monotonic()
                    yield self.result(**{k: v() if callable(v) else v for k, v in changes.items()})

                with self.assertRaisesRegex(RuntimeError, reason):
                    self.run_live(predict)
                self.motors.drive.assert_not_called()
                self.motors.stop.assert_called()

    def test_hung_inference_stops_while_camera_still_updates(self):
        release = threading.Event()
        driven = threading.Event()
        self.motors.drive.side_effect = lambda *args: (self.check_owner(), driven.set())

        def predict(*args):
            self.camera.last_frame_time = time.monotonic()
            yield self.result()
            driven.wait(1)
            while not release.wait(0.005):
                self.camera.last_frame_time = time.monotonic()

        try:
            with self.assertRaisesRegex(RuntimeError, "CMD_TIMEOUT"):
                self.run_live(predict)
            self.motors.drive.assert_called_once()
            self.motors.stop.assert_called()
        finally:
            release.set()

    def test_missing_camera_and_missing_first_prediction_time_out(self):
        for has_camera, expected in ((False, "CAMERA_LOST"), (True, "INFERENCE_TIMEOUT")):
            release = threading.Event()
            finished = threading.Event()

            def predict(*args):
                try:
                    while not release.wait(0.005):
                        if has_camera:
                            self.camera.last_frame_time = time.monotonic()
                    return
                    yield
                finally:
                    finished.set()

            try:
                with self.subTest(expected=expected), self.assertRaisesRegex(RuntimeError, expected):
                    self.run_live(predict)
                self.motors.drive.assert_not_called()
            finally:
                release.set()
                self.assertTrue(finished.wait(1))

    def test_camera_stalls_after_motor_starts(self):
        release = threading.Event()
        finished = threading.Event()

        def predict(*args):
            try:
                self.camera.last_frame_time = time.monotonic()
                yield self.result()
                release.wait(1)
            finally:
                finished.set()

        try:
            with self.assertRaisesRegex(RuntimeError, "CAMERA_LOST"):
                self.run_live(predict)
            self.motors.drive.assert_called_once()
            self.motors.stop.assert_called()
        finally:
            release.set()
            self.assertTrue(finished.wait(1))

    def test_worker_error_motor_error_and_interrupt_stop(self):
        for error in (ValueError("model failed"), KeyboardInterrupt()):
            def predict(*args):
                raise error
                yield

            with self.subTest(error=type(error)), self.assertRaises(type(error)):
                self.run_live(predict)
            self.motors.drive.assert_not_called()
            self.motors.stop.assert_called()

        def predict(*args):
            self.camera.last_frame_time = time.monotonic()
            yield self.result()

        self.motors.drive.side_effect = OSError("motor failed")
        with self.assertRaisesRegex(OSError, "motor failed"):
            self.run_live(predict)
        self.motors.stop.assert_called()

    def test_observations_keep_real_timestamps_and_skip_duplicates(self):
        seen = []
        first = time.monotonic()
        self.camera.last_frame_time = first

        def observation():
            if self.camera.get_observation.call_count < 3:
                return first, "frame1"
            self.camera.last_frame_time = time.monotonic()
            return self.camera.last_frame_time, "frame2"

        self.camera.get_observation.side_effect = observation

        def predict(observations, *args):
            seen.extend([next(observations), next(observations)])
            yield self.result(v=0, w=0, reached_goal=True)

        self.run_live(predict)
        self.assertEqual([frame for timestamp, frame in seen], ["frame1", "frame2"])
        self.assertEqual(seen[0][0], first)
        self.assertGreater(seen[1][0], first)

    def test_cli_requires_explicit_live_calibration_and_preserves_offline_mode(self):
        base = ["--topomap-dir", "map", "--max-v", "0.1", "--max-w", "0.6"]
        calibration = ["--wheelbase", "0.1", "--v-full", "0.5", "--min-posterior", "0.7"]
        with patch("navigation.main.run") as run, patch("sys.stderr"):
            for extra in (["--live"], ["--live", "--query", "images"],
                          ["--live"] + calibration + ["--max-duty", "nan"],
                          ["--live"] + calibration + ["--command-timeout", "0"],
                          ["--live"] + calibration + ["--startup-timeout", "nan"],
                          ["--live"] + calibration + ["--startup-timeout", "0"]):
                with self.subTest(extra=extra), self.assertRaises(SystemExit):
                    main(base + extra)
            run.assert_not_called()
            main(base + ["--live"] + calibration)
            self.assertTrue(run.call_args[0][0].live)
            self.assertEqual(run.call_args[0][0].startup_timeout, 30)
            main(["--topomap-dir", "map", "--query", "images"])
            self.assertFalse(run.call_args[0][0].live)

    def test_patroljet_stops_and_closes_when_start_or_navigation_fails(self):
        path = Path(__file__).resolve().parents[1] / "src/hardware/patroljet.py"
        spec = importlib.util.spec_from_file_location("hardware.patroljet_under_test", path)
        module = importlib.util.module_from_spec(spec)
        dependencies = {
            "hardware.camera": SimpleNamespace(JetCamera=Mock()),
            "hardware.motors": SimpleNamespace(JetMotors=Mock()),
        }
        with patch.dict(sys.modules, dependencies):
            spec.loader.exec_module(module)
        for fails_at_start in (False, True):
            robot = module.PatrolJet("test", max_duty=0.1)
            if fails_at_start:
                robot.camera.start.side_effect = RuntimeError("camera failed")
            with patch("navigation.live.run_live", side_effect=RuntimeError("model failed")):
                with self.subTest(start=fails_at_start), self.assertRaises(RuntimeError):
                    try:
                        robot.run_navigation(None, None)
                    finally:
                        robot.close()
            robot.motors.stop.assert_called()
            robot.camera.stop.assert_called()


class CameraObservationTests(unittest.TestCase):
    def test_camera_callback_timestamps_copies_and_cleanup(self):
        path = Path(__file__).resolve().parents[1] / "src/hardware/camera.py"
        spec = importlib.util.spec_from_file_location("camera_under_test", path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"jetbot": SimpleNamespace(Camera=Mock()),
                                      "cv2": SimpleNamespace(getBuildInformation=Mock())}):
            spec.loader.exec_module(module)
        source = Mock()
        module.Camera.instance.return_value = source
        with patch.object(module.cv2, "getBuildInformation", return_value="GStreamer: YES"):
            camera = module.JetCamera()
            camera.start()
        self.assertIsNone(camera.get_observation())
        frame = Mock(size=1)
        with patch.object(module.time, "monotonic", return_value=12.5):
            camera._on_frame({"new": frame})
        self.assertEqual(camera.get_observation(), (12.5, frame.copy.return_value))
        self.assertEqual(camera.last_frame_time, 12.5)
        self.assertEqual(camera.get_observation()[0], 12.5)
        camera.stop()
        source.unobserve.assert_called_once_with(camera._on_frame, names="value")
        source.stop.assert_called_once()
        self.assertIsNone(camera.last_frame_time)
        with self.assertRaises(RuntimeError):
            camera.get_observation()


if __name__ == "__main__":
    unittest.main(verbosity=2)
