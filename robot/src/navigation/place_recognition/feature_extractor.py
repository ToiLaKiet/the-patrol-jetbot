"""CosPlace descriptor extraction using the shared JetBot preprocessing."""

from pathlib import Path

import numpy as np
import torch

from utils import preprocess_frame
from .cosplace_model.cosplace_network import GeoLocalizationNet


class FeatureExtractor:
    def __init__(self, checkpoint, device="cuda"):
        checkpoint = Path(checkpoint)
        if not checkpoint.is_file():
            raise FileNotFoundError("Không thấy checkpoint CosPlace: " + str(checkpoint))
        if device not in ("cpu", "cuda"):
            raise ValueError("device phải là cpu hoặc cuda.")
        if device == "cuda" and not torch.cuda.is_available():
            raise ValueError("CUDA chưa khả dụng; kiểm tra môi trường hoặc chọn --device cpu.")
        self.device = torch.device(device)
        self.model = GeoLocalizationNet("EfficientNet_B0", 512)
        self.model.load_state_dict(torch.load(str(checkpoint), map_location="cpu"))
        self.model.eval().to(self.device)

    @torch.no_grad()
    def __call__(self, frame):
        image = preprocess_frame(frame).unsqueeze(0).to(self.device)
        descriptor = self.model(image)[0].cpu().numpy()
        if (descriptor.shape != (512,) or not np.isfinite(descriptor).all()
                or np.linalg.norm(descriptor) < 1e-8):
            raise ValueError("CosPlace phải trả descriptor hữu hạn, khác 0, shape [512].")
        return descriptor
