import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import torch
from torchvision import models

import infer_sample


SOURCE = Path(__file__).resolve().parents[2] / "PlaceNav/src"


class SampleInferenceTests(unittest.TestCase):
    def test_preprocessing_preserves_rgb_normalization_and_context_order(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for index in range(6):
                path = Path(directory) / "{}.png".format(index)
                Image.new("RGB", (100, 80), (index * 40, 128, 255)).save(str(path))
                paths.append(path)
            context, goal = infer_sample.prepare_inputs(paths, paths[-1])
            self.assertEqual(tuple(context.shape), (1, 18, 64, 85))
            self.assertEqual(tuple(goal.shape), (1, 3, 64, 85))
            for index in range(6):
                expected = torch.tensor([
                    (index * 40 / 255.0 - 0.485) / 0.229,
                    (128 / 255.0 - 0.456) / 0.224,
                    (1.0 - 0.406) / 0.225,
                ])
                torch.testing.assert_allclose(context[0, index * 3:index * 3 + 3, 0, 0], expected)
            torch.testing.assert_allclose(context[:, -3:], goal)
            repeated, _ = infer_sample.prepare_inputs(paths[:1], paths[-1])
            for index in range(6):
                torch.testing.assert_allclose(repeated[:, index * 3:index * 3 + 3], context[:, :3])

    def test_bad_context_count_and_unreadable_image_fail(self):
        with self.assertRaises(ValueError):
            infer_sample.prepare_inputs(["a", "b"], "goal")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.jpg"
            path.write_text("not an image")
            with self.assertRaises(OSError):
                infer_sample.prepare_inputs([path], path)

    def test_invalid_outputs_fail_instead_of_reporting_success(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                infer_sample.check_tensor("descriptor", torch.full((1, 512), value), (1, 512))
        with self.assertRaises(ValueError):
            infer_sample.check_tensor("descriptor", torch.zeros(512), (1, 512))
        infer_sample.check_tensor("descriptor", torch.zeros(1, 512), (1, 512))

    def test_cli_rejects_incomplete_context(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            infer_sample.main(["--context", "a", "b", "--goal", "c"])
        self.assertEqual(error.exception.code, 2)

    def test_cli_rejects_empty_benchmark(self):
        for option in ("--runs", "--warmup"):
            with self.subTest(option=option), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as error:
                infer_sample.main(["--context", "a", "--goal", "b", "--benchmark", option, "0"])
            self.assertEqual(error.exception.code, 2)

    def test_benchmark_excludes_warmup_and_validation_from_cuda_timing(self):
        events = []
        loaded = {
            "gnm": Mock(side_effect=lambda *_: events.append("gnm") or
                        (torch.zeros(1, 1), torch.zeros(1, 5, 4))),
            "cosplace": Mock(side_effect=lambda *_: events.append("cosplace") or
                             torch.ones(1, 512)),
        }
        ticks = iter((1.0, 1.01, 2.0, 2.02))

        def clock():
            events.append("clock")
            return next(ticks)

        def check(*_):
            events.append("validate")

        output = io.StringIO()
        with patch.object(infer_sample.time, "perf_counter", side_effect=clock), \
                patch.object(infer_sample.torch.cuda, "synchronize",
                             side_effect=lambda *_: events.append("sync")), \
                patch.object(infer_sample.torch.cuda, "reset_peak_memory_stats"), \
                patch.object(infer_sample, "check_tensor", side_effect=check), \
                patch.object(infer_sample, "report_memory"), contextlib.redirect_stdout(output):
            infer_sample.benchmark(loaded, torch.zeros(1, 18, 64, 85),
                                   torch.zeros(1, 3, 64, 85), torch.device("cuda"), 2, 2)
        self.assertEqual(loaded["gnm"].call_count, 4)
        self.assertEqual(loaded["cosplace"].call_count, 4)
        first_clock = events.index("clock")
        self.assertEqual(events[:first_clock].count("gnm"), 2)
        self.assertEqual(events[first_clock:first_clock + 8],
                         ["clock", "gnm", "cosplace", "sync", "clock", "validate", "validate", "validate"])
        self.assertIn("mean=15.00 ms", output.getvalue())

    def test_benchmark_rejects_nonfinite_measured_output(self):
        model = Mock(side_effect=[torch.ones(1, 512), torch.full((1, 512), float("nan"))])
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(ValueError):
            infer_sample.benchmark({"cosplace": model}, torch.zeros(1, 18, 64, 85),
                                   torch.zeros(1, 3, 64, 85), torch.device("cpu"), 1, 1)
        self.assertNotIn("OK:", output.getvalue())

    def test_benchmark_main_keeps_both_models_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src/placenav/models").mkdir(parents=True)
            for name in ("gnm_large.pth", "efficientnet_85x85.pth"):
                (root / name).touch()
            image = root / "sample.png"
            Image.new("RGB", (85, 64)).save(str(image))
            gnm, cosplace = torch.nn.Identity(), torch.nn.Identity()
            with patch.object(infer_sample, "load_gnm", return_value=gnm), \
                    patch.object(infer_sample, "load_cosplace", return_value=cosplace), \
                    patch.object(infer_sample, "benchmark") as run, \
                    patch.object(sys, "path", list(sys.path)), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(infer_sample.main([
                    "--context", str(image), "--goal", str(image), "--benchmark",
                    "--placenav-dir", str(root), "--checkpoint-dir", str(root), "--device", "cpu",
                ]), 0)
            self.assertEqual(run.call_args[0][0], {"gnm": gnm, "cosplace": cosplace})

    @unittest.skipUnless((SOURCE / "placenav/models").is_dir(), "Cần source PlaceNav")
    def test_original_checkpoint_class_path_is_resolved(self):
        with patch.object(sys, "path", [str(SOURCE)] + sys.path):
            from placenav.models.wp_models.gnm.gnm import GNM
            original_class = b"cgnm_train.models.gnm\nGNM\n."
            self.assertIs(infer_sample.GNMUnpickler(io.BytesIO(original_class)).load(), GNM)

    @unittest.skipUnless((SOURCE / "placenav/models").is_dir(), "Cần source PlaceNav")
    def test_cosplace_matches_upstream_weights_and_forward_without_download(self):
        with patch.object(sys, "path", [str(SOURCE)] + sys.path):
            from placenav.models.pr_models.cosplace_model import cosplace_network
            with patch.object(cosplace_network, "get_pretrained_torchvision_model",
                              return_value=models.efficientnet_b0(pretrained=False)):
                reference = cosplace_network.GeoLocalizationNet("EfficientNet_B0", 512).eval()
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "cosplace.pth"
                torch.save(reference.state_dict(), str(path))
                with patch("torch.hub.load_state_dict_from_url", side_effect=AssertionError("network")):
                    loaded = infer_sample.load_cosplace(path)
                self.assertFalse(loaded.training)
                image = torch.rand(1, 3, 64, 85)
                with torch.no_grad():
                    expected, actual = reference(image), loaded(image)
                torch.testing.assert_allclose(actual, expected)
                torch.testing.assert_allclose(actual.norm(dim=1), torch.ones(1))
                infer_sample.check_tensor("descriptor", actual, (1, 512))
                torch.save({}, str(path))
                with self.assertRaises(RuntimeError):
                    infer_sample.load_cosplace(path)


if __name__ == "__main__":
    unittest.main()
