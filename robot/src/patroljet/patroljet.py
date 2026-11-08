from dataclasses import dataclass, field
from jetbot import Robot
from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Detection:
    cls: str
    bbox: tuple                 # (x1, y1, x2, y2) pixel
    conf: float
    stamp: float
    truth_id: Optional[str] = None   # chỉ có trong mô phỏng, để chấm điểm tracking — code điều khiển KHÔNG được dùng
@dataclass
class CameraFrame:
    stamp: float
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    detections: List[Detection] = field(default_factory=list)   # mô phỏng trả sẵn "ảnh đã phát hiện"
    image: object = None                                        # robot thật: ảnh numpy BGR
@dataclass
class Battery:
    voltage: float
    percent: float              # 0..1
    charging: bool

    
    
class PatrolJet:
    def __init__(self, name):
        self.robot = Robot()
        self.name = name
        self.left_motor = 1.0
        self.right_motor = 1.0
        self.duty = 0.2 
        print(f"Jetbot {self.name} initialized.") 
    '''
    Methods to control the robot's movement
    '''
    def go_backward(self):
        self.robot.backward(self.duty)
        
    def go_forward(self):
        self.robot.forward(self.duty)
        
    def go_left(self):
        self.robot.left(self.duty)
        
    def go_right(self):
        self.robot.right(self.duty)
        
    '''
    Convert linear and angular velocities to wheel speeds / duty
    '''
    def to_wheels(v: float, w: float, wheelbase: float = 0.12, v_full: float = 0.40, max_duty: float = 0.40):
        """v [m/s], w [rad/s] -> (left, right) duty trong [-1, 1].

        v_full = tốc độ thật khi duty = 1,0 (đo cho TỪNG robot). max_duty chặn cả hai bánh CÙNG tỉ lệ
        để giữ đúng hướng rẽ — JetBot trượt bánh từ duty ~0,7 nên mặc định 0,4.
        """
        vl, vr = v - w * wheelbase / 2, v + w * wheelbase / 2
        l, r = vl / v_full, vr / v_full
        k = max(1.0, abs(l) / max_duty, abs(r) / max_duty)
        return l / k, r / k
    
    


