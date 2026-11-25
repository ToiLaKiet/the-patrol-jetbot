# Teach

[record_route.py](record_route.py) là entry point độc lập của giai đoạn Teach.

Luồng hiện tại: **Joystick + ghi JPEG/CSV khoảng 5 Hz → kết thúc phiên →
tạo TOPOMAP với khoảng lấy mẫu mặc định 2 giây**. Không cần ROS hoặc odometry.

| Phần | File | Trạng thái |
| --- | --- | --- |
| Joystick | [teleop.py](../teleop/teleop.py) | Đã có, cùng safety và motor |
| Thu dữ liệu hiện tại | [recorder.py](recorder.py) | Đã có JPEG + CSV, chưa phải ROSBag |
| Collect ROSBag | [rosbag_recorder.py](rosbag_recorder.py) | File trống, chưa triển khai |
| create TOPOMAP | [create_topomap.py](create_topomap.py) | Đọc JPEG/CSV, xuất ảnh node theo timestamp |

Chạy từ `robot/`:

```sh
uv run --no-sync python src/teach/record_route.py --teach-dir teach
```

Mặc định ghi vào `teach/`. Giai đoạn hiện tại dùng [recorder.py](recorder.py),
không phụ thuộc ROS. Sau khi kết thúc Teach, chạy bước tạo TOPOMAP riêng.

## Tạo topomap

Sau `Ctrl+C`, dùng đúng đường dẫn `Teach recording: ...` đã in khi bắt đầu phiên.
Ví dụ chạy từ `robot/` (thay `run_...` bằng thư mục phiên thực tế):

```sh
uv run --no-sync python src/teach/create_topomap.py teach/run_... topomaps/route_a
```

Script đọc `image` và `frame_read_s` trong `samples.csv`, chọn ảnh đầu rồi
ảnh đầu tiên cách ảnh đã chọn ít nhất **2 giây**, sau đó thêm ảnh cuối phiên
nếu chưa được chọn. Khoảng cách tới node cuối có thể dưới 2 giây để giữ đúng
điểm kết thúc Teach. Lấy mẫu bằng timestamp,
không đếm mỗi 10 frame vì tốc độ ghi thực tế có thể thấp hơn 5 Hz.
Đổi khoảng lấy mẫu bằng `--dt 3` nếu cần điều chỉnh theo tốc độ robot.
Đây là khoảng thời gian trong phiên Teach, không phụ thuộc tốc độ phát lại.
Script không tự bỏ ảnh đứng yên. Phiên ngắn hơn 2 giây vẫn giữ ảnh đầu và cuối;
nếu phiên chỉ có một ảnh thì chỉ xuất một node, không nhân đôi.

```text
topomaps/route_a/
  0.jpg
  1.jpg
  2.jpg
  ...
```

Ảnh được kiểm tra đọc được rồi sao chép nguyên JPEG, không resize hoặc đổi màu.
Map mới có tên ảnh số liên tiếp phù hợp loader của PlaceNav; navigation JetBot
vẫn chưa triển khai. Không xuất pose giả hoặc `traj_data.pkl`.
Script từ chối thư mục đích đã tồn tại, CSV rỗng hoặc timestamp không hợp lệ;
nếu lỗi ảnh/ghi đĩa thì xóa map đang tạo dở. Dữ liệu Teach gốc được giữ nguyên.

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
