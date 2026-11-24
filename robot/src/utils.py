"""Shared JetBot helpers."""

import cv2
import numpy as np
from torchvision import transforms


_TRANSFORM = transforms.Compose([
    transforms.ToTensor(),
    transforms.Resize((64, 85), antialias=True),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])


def preprocess_frame(frame):
    """Convert a BGR uint8 HWC image to a normalized RGB float32 [3, 64, 85] tensor."""
    if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
            or frame.ndim != 3 or frame.shape[2] != 3
            or frame.shape[0] == 0 or frame.shape[1] == 0):
        raise ValueError("Cần ảnh BGR uint8 không rỗng, shape [H, W, 3].")
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return _TRANSFORM(rgb)
