import contextlib
import io
import subprocess
import unittest
from unittest.mock import Mock, patch

import check_jetbot_env


class EnvironmentCheckTests(unittest.TestCase):
    def test_reports_all_failures_without_importing_jetbot(self):
        result = Mock(returncode=1, stderr="ModuleNotFoundError: missing", stdout="")
        output = io.StringIO()
        with patch.object(check_jetbot_env.subprocess, "run", return_value=result) as run, \
                contextlib.redirect_stdout(output):
            self.assertEqual(check_jetbot_env.main(), 1)
        self.assertEqual(run.call_count, len(check_jetbot_env.CHECKS))
        for name, _ in check_jetbot_env.CHECKS:
            self.assertIn("FAIL " + name, output.getvalue())
        self.assertTrue(all(call[0][0][0] == check_jetbot_env.sys.executable
                            for call in run.call_args_list))

    def test_checks_full_import_after_prerequisites_pass(self):
        result = Mock(returncode=0, stdout="", stderr="")
        with patch.object(check_jetbot_env.subprocess, "run", return_value=result) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(check_jetbot_env.main(), 0)
        self.assertEqual(run.call_count, len(check_jetbot_env.CHECKS) + 1)
        self.assertIn("import jetbot", run.call_args[0][0][-1])

    def test_timeout_and_native_import_errors_are_failures(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with patch.object(check_jetbot_env.subprocess, "run",
                              side_effect=subprocess.TimeoutExpired("python", 30)):
                self.assertFalse(check_jetbot_env.check("TensorRT", "import tensorrt"))
            with patch.object(check_jetbot_env.subprocess, "run",
                              return_value=Mock(returncode=-11, stderr="native crash", stdout="")):
                self.assertFalse(check_jetbot_env.check("TensorRT", "import tensorrt"))

    def test_inference_is_required_by_original_jetbot(self):
        result = Mock(returncode=0, stdout="", stderr="")
        with patch.object(check_jetbot_env.subprocess, "run", return_value=result) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(check_jetbot_env.main(), 0)
        commands = [call[0][0][-1] for call in run.call_args_list]
        self.assertIn("import torch", commands)
        self.assertIn("import tensorrt", commands)


if __name__ == "__main__":
    unittest.main()
