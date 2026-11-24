import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

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
