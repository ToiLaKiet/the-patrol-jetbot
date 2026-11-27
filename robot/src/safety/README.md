# Safety

[safety.py](safety.py) cung cấp ba kiểu:

| Kiểu | Vai trò |
| --- | --- |
| `SafetyConfig` | Timeout 1 s, giới hạn 0.30 m/s, 1.6 rad/s, ngưỡng pin 0.10 |
| `SafetyInput` | Thời điểm, lệnh gần nhất, estop, pin, định vị và camera |
| `SafetyLayer` | Trả lý do chặn và giữ `state`/`reason` gần nhất |

`SafetyConfig` kiểm tra ngay khi tạo: mọi giá trị phải hữu hạn, timeout > 0,
giới hạn vận tốc >= 0 và ngưỡng pin trong [0, 1]. Cấu hình không cho sửa
trực tiếp; tạo `SafetyConfig(...)` mới khi cần đổi giới hạn.

`check(input, moving=True)` kiểm tra theo thứ tự:
estop → nếu không chuyển động thì OK → thời gian hợp lệ → timeout →
pin hợp lệ → pin cạn → định vị nếu cần → camera nếu cần → OK.
Nó không tự đọc cảm biến hoặc gửi lệnh motor.

`filter(v, w, input)` nhận **m/s và rad/s**, kiểm tra lệnh hữu hạn, gọi `check()`
rồi chặn về 0 hoặc giới hạn vận tốc theo cấu hình. Lệnh đứng yên bỏ qua các
điều kiện chuyển động nhưng vẫn kiểm tra estop. Không truyền duty vào API này.

Teleop chỉ gọi `check()` rồi tự dừng motor khi bị chặn. Pin đang là `None`
nghĩa là chưa có nguồn đo; định vị không bắt buộc. Timeout chỉ được phát hiện
khi vòng lặp gọi lại safety, không phải watchdog độc lập.

Navigation `--live` gọi `check()`/`filter()` ở vòng chính trong khi inference
chạy nền. Timeout dùng timestamp ảnh sinh ra waypoint, không dùng thời điểm
gửi lại lệnh motor. Posterior dưới ngưỡng người chạy cung cấp gây
`LOCALIZATION_LOST`; callback camera ngừng hoặc waypoint quá hạn làm kết thúc
phiên và dừng motor. Pin vẫn là `None`; chưa có watchdog phía driver/phần cứng.

Kết quả trả về khi an toàn là `"OK"`; khi đó `state="OK"`, `reason=""`.
Khi chặn, `state="BLOCKED"` và `reason` giữ mã như `ESTOP`, `CMD_TIMEOUT`,
`BATTERY_CRITICAL` hoặc `CAMERA_LOST`.

Xem [cách teleop dùng safety](../teleop/README.md) và
[test điều kiện an toàn](../../tests/test_teleop.py).
