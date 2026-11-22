# Hardware

Đây là nơi truy cập thiết bị qua thư viện NVIDIA JetBot và quản lý vòng đời.

| File | Trách nhiệm |
| --- | --- |
| [patroljet.py](patroljet.py) | `PatrolJet` sở hữu camera, motor, safety, teleop và recorder |
| [motors.py](motors.py) | `JetMotors` kiểm tra, giới hạn và gửi lệnh hai bánh |
| [camera.py](camera.py) | `JetCamera` mở camera và trả bản sao frame mới nhất |

## Motor

`set_motors(left, right)` nhận lệnh chuẩn hóa, kiểm tra hữu hạn rồi chia cả
hai bánh cho cùng một hệ số nếu vượt `max_duty` (mặc định 0.4).
Cách này giữ tỷ lệ hai bánh. Driver áp dụng `left_alpha`/`right_alpha`
để hiệu chỉnh từng motor.

Sau lần gửi thành công, `last_command = (monotonic_time, left, right)`
lưu lệnh sau giới hạn, trước hiệu chỉnh driver. `stop()` gửi dừng và cập nhật
hai lệnh về 0. Đầu vào lỗi hoặc ghi motor thất bại sẽ gọi dừng trước khi báo lỗi.

`drive(v, w, wheelbase, v_full)` là API riêng cho m/s và rad/s:

```text
v_left  = v - w * wheelbase / 2
v_right = v + w * wheelbase / 2
left, right = v_left / v_full, v_right / v_full
```

`to_wheels()` áp dụng phép đổi và giới hạn duty. `wheelbase` và `v_full`
cần hiệu chỉnh theo robot thật; mô hình tốc độ–duty là xấp xỉ tuyến tính.
Teleop hiện tại gọi `set_motors()` trực tiếp.

## Camera và vòng đời

`JetCamera.start()` kiểm tra OpenCV có GStreamer rồi gọi `Camera.instance()`
ở 224 × 224 mặc định. Nếu thiếu backend, báo lỗi kèm đường dẫn OpenCV
để phân biệt bản `.venv` với bản hệ thống; không thay backend tự động.
`get_frame()` kiểm tra camera đã mở, frame không rỗng, rồi trả `frame.copy()`.
Không có timestamp từ cảm biến hoặc kiểm tra frame bị đóng băng.
Camera CSI cần backend GStreamer; xem [cài đặt](../../README.md#khởi-tạo-trên-jetbot).

Tạo `PatrolJet` khởi tạo và dừng motor, chưa mở camera.
`run_teleop()` dùng lại motor/safety hiện có. Nếu có `teach_dir`, nó gọi
`start()` để mở camera, dừng motor rồi khởi động recorder trước teleop.
`close()` dừng motor trước, chờ recorder đóng rồi đóng camera, kể cả khi
đóng recorder báo lỗi.
