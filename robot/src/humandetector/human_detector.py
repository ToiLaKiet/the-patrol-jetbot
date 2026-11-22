import math
from typing import List, Optional

from ..patroljet import CameraFrame, Detection

BASELINE_CLASSES = ("person")
# chiều cao thật trung bình (m) — dùng cho ước lượng khoảng cách Z = fy·H/h
CLASS_HEIGHT = {"person": 1.70}


class Detector:
    def detect(self, frame: CameraFrame) -> List[Detection]:
        raise NotImplementedError


class PassThroughDetector(Detector):
    """Mô phỏng đã trả sẵn phát hiện trong frame — chỉ lọc theo ngưỡng tin cậy và lớp baseline."""
    def __init__(self, conf_min: float = 0.10, classes=BASELINE_CLASSES):
        self.conf_min, self.classes = conf_min, set(classes)

    def detect(self, frame):
        return [d for d in frame.detections if d.conf >= self.conf_min and d.cls in self.classes]


class YoloDetector(Detector):
    """Robot thật: YOLO (ultralytics). Chỉ giữ 5 lớp baseline (tên lớp COCO: dining table -> table)."""
    COCO_MAP = {"person": "person"}

    def __init__(self, weights: str = "yolov8n.pt", conf_min: float = 0.25, imgsz: int = 640, device: Optional[str] = None):
        from ultralytics import YOLO
        self.model, self.conf_min, self.imgsz, self.device = YOLO(weights), conf_min, imgsz, device

    def detect(self, frame):
        r = self.model.predict(frame.image, conf=self.conf_min, imgsz=self.imgsz, device=self.device, verbose=False)[0]
        out = []
        for b, c, k in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()):
            name = self.COCO_MAP.get(r.names[int(k)])
            if name:
                out.append(Detection(name, tuple(b), float(c), frame.stamp))
        return out


def bearing_distance(bbox, frame: CameraFrame, cls: str = "person", cam_height: float = 0.12):
    """Từ hộp phát hiện -> (theta, Z).

    theta = atan((u - cx) / fx)   dương = mục tiêu ở bên PHẢI ảnh
    Z     = fy * H / h            H = chiều cao thật của lớp, h = chiều cao hộp (pixel)
    Sai khi vật bị che nửa hoặc người ngồi — chỗ để nâng cấp bằng depth / stereo / LiDAR.
    """
    x1, y1, x2, y2 = bbox
    u = (x1 + x2) / 2
    h = max(1.0, y2 - y1)
    theta = math.atan2(u - frame.cx, frame.fx)
    if y1 <= 2 and y2 > frame.cy + 2:
        # đỉnh hộp bị mép trên ảnh cắt (người đứng gần, đầu ra khỏi khung) -> h nhỏ hơn thật -> Z bị ước lượng QUÁ XA.
        # Dùng mặt sàn: chân vật chạm sàn, camera cao cam_height  =>  Z = fy · cam_height / (y2 - cy)
        return theta, frame.fy * cam_height / (y2 - frame.cy)
    z = frame.fy * CLASS_HEIGHT.get(cls, 1.0) / h
    return theta, z


def to_map(theta_img: float, z: float, pose):
    """Đổi (theta ảnh, Z) sang toạ độ bản đồ. Ảnh: theta dương = bên phải = quay âm trong khung robot."""
    xr, yr, thr = pose
    a = thr - theta_img
    return xr + z * math.cos(a), yr + z * math.sin(a)

