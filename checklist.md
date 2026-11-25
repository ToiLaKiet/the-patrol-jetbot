# Checklist triển khai PlaceNav trên JetBot

Mục tiêu: giữ thư viện JetBot cho camera/motor, port phần tính toán PlaceNav.
Yêu cầu PlaceNav/Repeat của dự án: cập nhật waypoint ở 5 Hz (200 ms/vòng).
Checklist dành cho một người: làm lần lượt từ bước 1 đến bước 6.
Đã chạy inference mẫu và benchmark sau warm-up hai checkpoint trên CUDA của Nano.
Hai entry point chạy độc lập: `src/teach/record_route.py` và `src/navigation/main.py`;
Đã có tạo TOPOMAP từ JPEG/CSV, lấy mẫu theo timestamp mặc định 2 giây và giữ ảnh đầu/cuối.
ROSBag và các bước Navigation hiện là file trống, chưa hoàn thành luồng tự hành.

## 1. Chạy hai model trên Nano — kết quả

Môi trường: JetPack **4.5 / L4T 32.5.0**, Python **3.6.9**, PyTorch **1.10.0**,
torchvision **0.11.1**, CUDA toolkit **10.2.89** (PyTorch build CUDA **10.2**).
Các API torchvision cần dùng đều PASS.

Đã nạp `gnm_large.pth` và `efficientnet_85x85.pth`, chạy CUDA riêng từng model
và giữ cả hai cùng trong bộ nhớ bằng [scripts/infer_sample.py](robot/scripts/infer_sample.py).
GNM trả distance `[1, 1]`, waypoint `[1, 5, 4]`; CosPlace/EfficientNet-B0 trả
descriptor `[1, 512]`, L2 norm `1.0`. Mọi output đúng shape, không NaN/Inf.

Benchmark trên Nano (2026-11-24): 10 lượt warm-up, 30 lượt đo, một ảnh mẫu
lặp làm context. Thời gian chỉ gồm forward, đã synchronize CUDA.

| Model | Mean (ms) | Max quan sát (ms) | Peak RSS tiến trình (MiB) |
| --- | --- | --- | --- |
| GNM | 64.18 | 87.77 | 3028.9 |
| CosPlace | 45.98 | 59.77 | 2993.4 |
| GNM + CosPlace | 104.23 | 134.43 | 2998.7 |

**Quyết định: giữ PyTorch, chưa chuyển TensorRT.** Với yêu cầu **5 Hz / 200 ms**,
forward cả hai còn dư **95.77 ms theo mean**, **65.57 ms theo max đã đo**.
Chưa xác nhận toàn pipeline camera/preprocessing/localization đạt 5 Hz hoặc
độ chính xác navigation; cần đo lại khi tích hợp.

## 2. Chuẩn hóa ảnh và context

- [x] Frame JetCamera là **BGR**, shape `(224, 224, 3)`, dtype `uint8`; đã đối chiếu `assume_bgr.png` đúng màu vật thật.
- [x] [Preprocessing dùng chung](robot/src/utils.py): BGR → RGB → tensor → resize rộng 85 × cao 64 (antialias) → normalize mean `[0.485, 0.456, 0.406]`, std `[0.229, 0.224, 0.225]`; output `float32 [3, 64, 85]`, dùng trong script inference.
- [ ] Kiểm soát nhịp lấy context và timestamp; không coi frame lặp/quá hạn là ảnh mới. Code gốc thêm ảnh theo callback camera.
- [ ] Dùng cùng preprocessing cho ảnh topomap và ảnh Repeat.

## 3. Tạo topomap từ phiên teach

- [ ] Thu tuyến ngắn khoảng 2–3 m, có ảnh đầu/cuối và timestamp.
- [x] [create_topomap.py](robot/src/teach/create_topomap.py) chọn ảnh theo `frame_read_s`, mặc định cách nhau ít nhất 2 giây (`--dt` để đổi), luôn giữ ảnh đầu/cuối và không thêm trùng ảnh cuối đã chọn; đoạn cuối có thể dưới 2 giây. Teach vẫn ghi khoảng 5 Hz.
- [x] Xuất thư mục ảnh node `0.jpg`, `1.jpg`, …; kiểm tra ảnh JPEG đọc được, timestamp tăng dần và không ghi đè map cũ. Đã kiểm tra bằng dữ liệu mẫu, chưa thử tuyến thật.
- [ ] Chỉnh khoảng lấy mẫu theo tốc độ JetBot và kiểm tra node trùng lúc đứng yên; hiện script chỉ lấy mẫu theo thời gian.
- [ ] Sau khi có ảnh topomap và CosPlace chạy được: trích xuất descriptor cho từng node và lưu/cache database HDF5.
- [ ] Kiểm tra descriptor khớp thứ tự node; tính lại cache khi đổi ảnh, model hoặc preprocessing.

`navigate.py` đọc ảnh topomap và descriptor, không đọc CSV lệnh motor hay
`traj_data.pkl`. Script tạo map gốc phụ thuộc odometry, nhưng có thể thay bằng
bộ xuất map từ JPEG. Không cần làm odometry trước cho luồng navigation dựa
trên ảnh này; không tạo pose giả.

## 4. Port localization và dự đoán waypoint

- [ ] Tách tính toán khỏi ROS: thay subscriber/publisher bằng lời gọi Python; tách các import ROS trong `utils.py` và phụ thuộc liên quan.
- [ ] Port CosPlace FeatureExtractor và một bộ lọc: Bayesian Filter
- [ ] Thực hiện ảnh hiện tại → descriptor → node gần nhất.
- [ ] Chọn subgoal phía trước và chặn ở goal; mặc định gốc `lookahead=1`.
- [ ] Gọi GNM với context và ảnh subgoal để lấy chuỗi waypoint.
- [ ] Chọn waypoint điều khiển; mặc định gốc `target_waypoint_idx=2`.
- [ ] Replay dữ liệu độc lập, hiển thị query/node/subgoal/waypoint và độ trễ trước khi bật motor.
- [ ] Đánh giá node dự đoán khi lái lại tuyến thủ công; xử lý map rỗng, dữ liệu lỗi và kết quả không hữu hạn.

## 5. Nối waypoint với motor

- [ ] Port phép đổi waypoint → `(v, w)` từ controller PlaceNav làm cơ sở.
- [ ] Đối chiếu cách diễn giải/scale waypoint; không tự mặc định output là mét đã hiệu chỉnh cho JetBot.
- [ ] Hiệu chỉnh `wheelbase`, `v_full`, chiều quay và giới hạn vận tốc.
- [ ] Nối `(v, w)` → `SafetyLayer.filter()` → `JetMotors.drive()`.
- [ ] Kiểm tra chiều quay và dừng khi kê bánh trước khi chạy dưới đất.

## 6. Tích hợp Repeat và dừng an toàn

- [ ] Bổ sung chế độ tự hành trong entry point và vòng đời PatrolJet.
- [ ] Có một nơi quyết định lệnh motor giữa teleop và tự hành; joystick có thể tiếp quản hoặc dừng.
- [ ] Watchdog theo tuổi ảnh/waypoint mới, không làm mới timeout bằng kết quả cũ. Controller gốc giữ vận tốc gần nhất nên cần bổ sung.
- [ ] Dừng khi camera lỗi/đóng băng, inference lỗi/quá hạn hoặc mất định vị theo tiêu chí đã kiểm chứng.
- [ ] Xác nhận đến goal qua nhiều quan sát; dừng motor và đóng tài nguyên khi kết thúc hoặc exception.
- [ ] Thử A → B ở tốc độ thấp có giám sát, ghi lỗi và độ trễ.

## Sau khi chạy được tuyến cơ bản

- [ ] Bổ sung phát hiện vật cản và kiểm chứng khả năng dừng.
- [ ] Lưu cấu hình, timestamp, Teach/Repeat và nhãn tham chiếu.
- [ ] Đánh giá localization, tỷ lệ hoàn thành tuyến, độ trễ và lỗi dừng.
- [ ] So sánh phương pháp khác trên cùng dataset khi có nhu cầu nghiên cứu.

## Source tham chiếu

- [Model config](https://github.com/lasuomela/PlaceNav/blob/main/src/config/models.yaml)
- [GNM](https://github.com/lasuomela/PlaceNav/blob/main/src/placenav/models/wp_models/gnm/gnm.py)
- [MobileNet của GNM](https://github.com/lasuomela/PlaceNav/blob/main/src/placenav/models/wp_models/gnm/modified_mobilenetv2.py)
- [Loader và preprocessing](https://github.com/lasuomela/PlaceNav/blob/main/src/placenav/utils.py)
- [Navigation](https://github.com/lasuomela/PlaceNav/blob/main/src/placenav/navigate.py)
- [Tạo topomap](https://github.com/lasuomela/PlaceNav/blob/main/src/placenav/create_topomap.py)
- [Controller](https://github.com/lasuomela/PlaceNav/blob/main/src/placenav/pd_controller.py)
- [Tham số navigation](https://github.com/lasuomela/PlaceNav/blob/main/src/placenav/parser.py)
