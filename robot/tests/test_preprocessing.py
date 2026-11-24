from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np
import torch
from torchvision.transforms import functional as F

from scripts import infer_sample
from utils import preprocess_frame


class PreprocessingTests(unittest.TestCase):
    def test_bgr_to_rgb_normalization_and_input_unchanged(self):
        frame = np.empty((224, 224, 3), dtype=np.uint8)
        frame[:] = (0, 128, 255)
        original = frame.copy()
        result = preprocess_frame(frame)
        self.assertEqual(tuple(result.shape), (3, 64, 85))
        self.assertEqual(result.dtype, torch.float32)
        expected = torch.tensor([
            (1.0 - 0.485) / 0.229,
            (128 / 255.0 - 0.456) / 0.224,
            (0.0 - 0.406) / 0.225,
        ])
        torch.testing.assert_allclose(result, expected[:, None, None].expand_as(result))
        np.testing.assert_array_equal(frame, original)

    def test_matches_tensor_resize_then_normalize_on_nonuniform_image(self):
        frame = np.random.RandomState(0).randint(0, 256, (123, 191, 3), dtype=np.uint8)
        rgb = frame[:, :, ::-1].copy()
        expected = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
        expected = F.resize(expected, [64, 85], antialias=True)
        mean = torch.tensor([0.485, 0.456, 0.406])[:, None, None]
        std = torch.tensor([0.229, 0.224, 0.225])[:, None, None]
        torch.testing.assert_allclose(preprocess_frame(frame), (expected - mean) / std)

    def test_rejects_missing_empty_wrong_shape_and_wrong_dtype(self):
        for frame in (None, [], np.zeros((0, 10, 3), dtype=np.uint8),
                      np.zeros((10, 0, 3), dtype=np.uint8),
                      np.zeros((10, 10), dtype=np.uint8),
                      np.zeros((10, 10, 4), dtype=np.uint8),
                      np.zeros((3, 10, 10), dtype=np.uint8),
                      np.zeros((10, 10, 3), dtype=np.float32),
                      np.zeros((10, 10, 3), dtype=np.uint16)):
            with self.subTest(shape=getattr(frame, "shape", None), dtype=getattr(frame, "dtype", None)), \
                    self.assertRaises(ValueError):
                preprocess_frame(frame)

    def test_saved_bgr_image_and_live_frame_use_same_preprocessing(self):
        frame = np.random.RandomState(1).randint(0, 256, (95, 150, 3), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.png"
            self.assertTrue(cv2.imwrite(str(path), frame))
            context, goal = infer_sample.prepare_inputs([path], path)
        expected = preprocess_frame(frame).unsqueeze(0)
        torch.testing.assert_allclose(goal, expected)
        for index in range(6):
            torch.testing.assert_allclose(context[:, index * 3:index * 3 + 3], expected)


if __name__ == "__main__":
    unittest.main()
