"""Match JetBot camera frames against a topomap using CosPlace and Bayesian filtering."""

from pathlib import Path

import numpy as np

from .place_recognition.bayesian_querier import PlaceRecognitionTopologicalFilter


def image_paths(directory):
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError("Không thấy thư mục ảnh: " + str(directory))
    paths = [path for path in directory.iterdir()
             if path.is_file() and path.suffix.lower() in (".jpg", ".jpeg", ".png")]
    if not paths:
        raise ValueError("Thư mục không có ảnh: " + str(directory))
    try:
        paths.sort(key=lambda path: int(path.stem))
    except ValueError:
        raise ValueError("Tên ảnh phải là số để giữ đúng thứ tự tuyến.")
    indices = [int(path.stem) for path in paths]
    if indices[0] < 0 or len(set(indices)) != len(indices):
        raise ValueError("Chỉ số ảnh phải không âm và không trùng nhau.")
    return paths


def read_frame(path):
    import cv2

    frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Không đọc được ảnh: " + str(path))
    return frame


class PlaceRecognition:
    def __init__(self, topomap, checkpoint, device="cuda"):
        from .place_recognition.feature_extractor import FeatureExtractor

        self.map_paths = image_paths(topomap)
        if [int(path.stem) for path in self.map_paths] != list(range(len(self.map_paths))):
            raise ValueError("Ảnh topomap phải đánh số liên tiếp từ 0.")
        self.extractor = FeatureExtractor(checkpoint, device)
        # shortcut: rebuild descriptors each run; add a validated cache if startup becomes too slow.
        descriptors = np.stack([self.extractor(read_frame(path)) for path in self.map_paths])
        self.querier = PlaceRecognitionTopologicalFilter(descriptors)

    def match(self, frame):
        """Return (closest_node_idx, posterior); call once per new frame in time order."""
        return self.querier.match(self.extractor(frame))
