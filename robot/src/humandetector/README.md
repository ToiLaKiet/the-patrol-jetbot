# Nhận diện người

[human_detector.py](human_detector.py) có code nhận diện và ước lượng vị trí,
**chưa được nối vào `main.py` hoặc teleop**.

| Thành phần | Cách hoạt động |
| --- | --- |
| `Detector` | Giao diện `detect(frame)` |
| `PassThroughDetector` | Lọc detection có sẵn theo lớp và độ tin cậy |
| `YoloDetector` | Gọi Ultralytics YOLO, giữ lớp `person`, trả bounding box |
| `bearing_distance()` | Dùng intrinsics và chiều cao người để ước lượng góc/khoảng cách |
| `to_map()` | Kết hợp góc/khoảng cách với pose robot để đổi sang tọa độ bản đồ |

Khoảng cách dùng `Z = fy * H / h`, với chiều cao người mặc định 1.70 m.
Nếu đầu bị cắt ở mép trên, hàm dùng vị trí chân và chiều cao camera để ước lượng.
Người ngồi, bị che hoặc hiệu chỉnh camera sai sẽ làm kết quả sai.

Module hiện import `CameraFrame`/`Detection` từ `..patroljet`, nhưng module đó
không tồn tại trong cây code hiện tại. `JetCamera` chỉ trả ảnh NumPy, chưa cung
cấp kiểu frame này. Ultralytics cũng chưa được khai báo trong môi trường robot.
`BASELINE_CLASSES` hiện là chuỗi `"person"`, nên bộ lọc mặc định của
`PassThroughDetector` chưa tạo đúng tập tên lớp. Cần sửa và kiểm tra các phần
này trước khi dùng; chưa có test riêng cho detector.
