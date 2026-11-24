# Teach

[main.py](main.py) là entry point độc lập của giai đoạn Teach.

Luồng dự kiến: **Joystick → Collect ROSBag → create TOPOMAP**. Joystick chạy
đồng thời với việc thu dữ liệu; tạo TOPOMAP sau khi kết thúc phiên.

| Phần | File | Trạng thái |
| --- | --- | --- |
| Joystick | [teleop.py](../teleop/teleop.py) | Đã có, cùng safety và motor |
| Thu dữ liệu hiện tại | [recorder.py](recorder.py) | Đã có JPEG + CSV, chưa phải ROSBag |
| Collect ROSBag | [rosbag_recorder.py](rosbag_recorder.py) | File trống, chưa triển khai |
| create TOPOMAP | [create_topomap.py](create_topomap.py) | File trống, chưa triển khai |

Chạy từ `robot/`:

```sh
uv run --no-sync python src/teach/main.py --teach-dir teach
```

Mặc định ghi vào `teach/`. Giai đoạn hiện tại dùng [recorder.py](recorder.py),
không phụ thuộc ROS và chưa tự tạo TOPOMAP.

## Luồng ghi

`start()` tạo thư mục phiên riêng bằng ngày giờ và hậu tố ngẫu nhiên,
ghi mốc `time.monotonic()` rồi khởi động một thread nền.
Mỗi chu kỳ lấy `motors.last_command`, ghi thời điểm đọc frame, lấy ảnh qua
`camera.get_frame()`, lưu JPEG rồi thêm dòng CSV và flush.
Mục tiêu khoảng 5 Hz; ghi đĩa chậm làm giảm tốc độ lấy mẫu.

```text
teach/run_YYYYMMDD_HHMMSS_.../
  images/
    000000.jpg
    000001.jpg
  samples.csv
```

| Cột CSV | Ý nghĩa |
| --- | --- |
| `image` | Đường dẫn JPEG tương đối trong thư mục phiên |
| `frame_read_s` | Thời điểm ngay trước đọc frame, giây từ lúc bắt đầu |
| `command_s` | Thời điểm lệnh motor gần nhất, cùng mốc thời gian |
| `left`, `right` | Lệnh sau giới hạn duty, trước hiệu chỉnh driver |

`command_s` có thể âm nhẹ vì lệnh dừng ban đầu được gửi trước lúc bắt đầu ghi.
Lệnh dừng là `(0, 0)`. Chỉ lấy trạng thái lệnh tại mỗi mẫu, không ghi mọi
thay đổi motor giữa hai mẫu; đây không phải vận tốc bánh đo được.

## Lỗi và kết thúc

Thread lưu lỗi camera/ghi đĩa. Teleop gọi `check()` trước khi gửi lệnh motor;
nếu có lỗi, exception kết thúc vòng lặp và motor được dừng.
`PatrolJet.close()` dừng motor trước, rồi `close()` recorder để chờ thread
và đóng CSV, sau đó mới đóng camera.

Timestamp là lúc đọc, không phải lúc phơi sáng. Camera trả frame mới nhất,
chưa phát hiện stream đóng băng. Flush CSV không bảo đảm dữ liệu sống qua mất
điện đột ngột; có thể còn ảnh không có dòng CSV nếu lỗi sau bước ghi ảnh.
