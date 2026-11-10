"""Lớp an toàn: đứng NGAY TRƯỚC động cơ và có quyền ghi đè mọi lệnh.

Quy tắc (theo thứ tự ưu tiên): dừng khẩn cấp · watchdog (không có lệnh mới) · pin cạn · mất định vị
· mất camera khi skill cần camera · giới hạn tốc độ.
Mỗi lần chặn đều có `reason` để hiện lên dashboard và ghi log.
"""
from dataclasses import dataclass
import math
from typing import Optional


@dataclass
class SafetyConfig:
    cmd_timeout: float = 1.0       # s — watchdog
    v_max: float = 0.30            # m/s
    w_max: float = 1.6             # rad/s
    battery_critical: float = 0.10


@dataclass
class SafetyInput:
    now: float
    last_cmd_t: float
    localized: bool = True
    need_localization: bool = True
    battery: Optional[float] = 1.0  # None khi chưa có nguồn đo pin
    camera_ok: bool = True
    need_camera: bool = False
    estop: bool = False


class SafetyLayer:
    def __init__(self, cfg: Optional[SafetyConfig] = None):
        self.cfg = cfg if cfg is not None else SafetyConfig()
        self.state, self.reason = "OK", ""

    def check(self, s: SafetyInput, moving: bool = True):
        """Kiểm tra điều kiện chung, không áp dụng giới hạn theo đơn vị vận tốc."""
        c = self.cfg
        if s.estop:
            reason = "ESTOP"
        elif not moving:                              # đứng yên không cần các điều kiện chuyển động
            reason = "OK"
        elif not all(math.isfinite(x) for x in (s.now, s.last_cmd_t)) or s.now < s.last_cmd_t:
            reason = "INVALID_TIME"
        elif s.now - s.last_cmd_t > c.cmd_timeout:
            reason = "CMD_TIMEOUT"
        elif s.battery is not None and (not math.isfinite(s.battery) or not 0 <= s.battery <= 1):
            reason = "INVALID_BATTERY"
        elif s.battery is not None and s.battery < c.battery_critical:
            reason = "BATTERY_CRITICAL"
        elif s.need_localization and not s.localized:
            reason = "LOCALIZATION_LOST"
        elif s.need_camera and not s.camera_ok:
            reason = "CAMERA_LOST"
        else:
            reason = "OK"
        self.state = "OK" if reason == "OK" else "BLOCKED"
        self.reason = "" if reason == "OK" else reason
        return reason

    def filter(self, v: float, w: float, s: SafetyInput):
        if not all(math.isfinite(x) for x in (v, w)):
            return self._block(0.0, 0.0, "INVALID_COMMAND")
        reason = self.check(s, moving=(v != 0.0 or w != 0.0))
        if reason != "OK":
            return 0.0, 0.0, reason
        c = self.cfg
        return max(-c.v_max, min(c.v_max, v)), max(-c.w_max, min(c.w_max, w)), "OK"

    def _block(self, v, w, reason):
        self.state, self.reason = "BLOCKED", reason
        return v, w, reason
