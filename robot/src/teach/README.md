# Teach recorder

[recorder.py](recorder.py) ghi ảnh và lệnh motor trong khi người dùng lái.
Bật bằng `--teach-dir teach` từ [entry point](../main.py).
Không phụ thuộc ROS hoặc PlaceNav.

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

[Test recorder](../../tests/test_teach_recorder.py) kiểm tra ảnh khớp CSV,
lệnh chạy/dừng, lỗi ghi và các thư mục phiên không ghi đè nhau.
