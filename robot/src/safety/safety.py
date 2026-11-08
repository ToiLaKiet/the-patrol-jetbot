"""Lớp an toàn: đứng NGAY TRƯỚC động cơ và có quyền ghi đè mọi lệnh.

Quy tắc (theo thứ tự ưu tiên): dừng khẩn cấp · watchdog (không có lệnh mới) · pin cạn · mất định vị
· mất camera khi skill cần camera · giới hạn tốc độ.
Mỗi lần chặn đều có `reason` để hiện lên dashboard và ghi log.
"""
from __future__ import annotations

from dataclasses import dataclass


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
    battery: float = 1.0
    camera_ok: bool = True
    need_camera: bool = False
    estop: bool = False


class SafetyLayer:
    def __init__(self, cfg: SafetyConfig = SafetyConfig()):
        self.cfg = cfg
        self.state, self.reason = "OK", ""

    def filter(self, v: float, w: float, s: SafetyInput):
        c = self.cfg
        if s.estop:
            return self._block(0.0, 0.0, "ESTOP")
        if v == 0.0 and w == 0.0:                       # đứng yên luôn an toàn — không báo lỗi khi robot rảnh
            self.state, self.reason = "OK", ""
            return 0.0, 0.0, "OK"
        if s.now - s.last_cmd_t > c.cmd_timeout:
            return self._block(0.0, 0.0, "CMD_TIMEOUT")
        if s.battery < c.battery_critical:
            return self._block(0.0, 0.0, "BATTERY_CRITICAL")
        if s.need_localization and not s.localized:
            return self._block(0.0, 0.0, "LOCALIZATION_LOST")
        if s.need_camera and not s.camera_ok:
            return self._block(0.0, 0.0, "CAMERA_LOST")
        self.state, self.reason = "OK", ""
        return max(-c.v_max, min(c.v_max, v)), max(-c.w_max, min(c.w_max, w)), "OK"

    def _block(self, v, w, reason):
        self.state, self.reason = "BLOCKED", reason
        return v, w, reason
