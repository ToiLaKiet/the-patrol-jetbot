import contextlib
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import main


class MainTests(unittest.TestCase):
    def setUp(self):
        self.factory = Mock()
        modules = patch.dict("sys.modules", {"hardware.patroljet": SimpleNamespace(PatrolJet=self.factory)})
        modules.start()
        self.addCleanup(modules.stop)

    def test_default_parameters(self):
        main.main([])
        self.factory.assert_called_once_with("Patrol-01")
        self.factory.return_value.run_teleop.assert_called_once_with(
            max_speed=0.1, deadzone=0.08, slew_rate=0.5,
        )
        self.factory.return_value.close.assert_called_once()

    def test_custom_parameters(self):
        main.main(["--max-speed", "0.2", "--deadzone", "0.12", "--slew-rate", "0.25"])
        self.factory.return_value.run_teleop.assert_called_once_with(
            max_speed=0.2, deadzone=0.12, slew_rate=0.25,
        )

    def test_invalid_parameters_never_initialize_hardware(self):
        cases = [
            ["--max-speed", "0"], ["--max-speed", "1.1"], ["--max-speed", "nan"],
            ["--deadzone", "-0.1"], ["--deadzone", "1"], ["--deadzone", "inf"],
            ["--slew-rate", "0"], ["--slew-rate", "-1"], ["--slew-rate", "nan"],
            ["--max-speed", "abc"], ["--unknown"], ["--max-speed"],
        ]
        for args in cases:
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    main.main(args)
                self.assertEqual(caught.exception.code, 2)
                self.factory.assert_not_called()

    def test_help_does_not_initialize_hardware(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as caught:
            main.main(["--help"])
        self.assertEqual(caught.exception.code, 0)
        for flag in ("--max-speed", "--deadzone", "--slew-rate"):
            self.assertIn(flag, output.getvalue())
        self.factory.assert_not_called()

    def test_runtime_error_still_closes_robot(self):
        self.factory.return_value.run_teleop.side_effect = RuntimeError("Disconnected")
        with self.assertRaises(RuntimeError):
            main.main([])
        self.factory.return_value.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
