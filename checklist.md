# Checklist triển khai PlaceNav trên JetBot

Mục tiêu: giữ thư viện JetBot cho camera/motor, port phần tính toán PlaceNav.
Hai người có thể bắt đầu song song theo phân công A/B bên dưới.
Chưa có kết quả nạp checkpoint hay benchmark trên Nano.

## Phân công cho hai người

A/B là vai trò; thay bằng tên thành viên khi nhận việc. Mỗi mục chưa có nhãn
riêng thuộc người phụ trách ghi ở tiêu đề giai đoạn.

| Người | Phụ trách | Có thể bắt đầu ngay | Bàn giao |
| --- | --- | --- | --- |
| A — Model và navigation | Runtime, preprocessing, GNM, CosPlace, descriptor, localization, subgoal | Bước 1, preprocessing ở bước 2, tách logic khỏi ROS ở bước 4 | Hai model chạy được, API inference, số đo độ trễ/RAM, database descriptor |
| B — Dữ liệu và robot | Camera/context, xuất ảnh topomap, controller, safety, tích hợp robot | Kiểm tra camera/context ở bước 2, xuất ảnh ở bước 3, controller với waypoint mẫu ở bước 5 | Phiên teach, topomap ảnh, context có timestamp, controller và cơ chế dừng |

### Thống nhất trước khi viết code

- [ ] A + B: chốt API Python và nơi đặt file; A phụ trách module mới cho model/localization, B phụ trách module xuất map/controller và các file phần cứng hiện có.
- [ ] A + B: dùng một bộ ảnh mẫu chung và cùng cấu hình model; ghi rõ phiên bản checkpoint/preprocessing.
- [ ] A: cung cấp duy nhất một hàm preprocessing dùng chung cho ảnh map và ảnh Repeat. B bàn giao ảnh camera thô kèm thứ tự màu đã xác nhận.
- [ ] B: bàn giao context gồm 6 ảnh theo thứ tự cũ → mới, có timestamp tăng dần với cấu hình mặc định. A chuyển chúng thành tensor cho GNM.
- [ ] A: bàn giao waypoint `[x, y, hx, hy]`, timestamp ảnh nguồn, node/subgoal và trạng thái đến goal. A + B xác nhận scale và hệ trục trước khi nối motor.
- [ ] B: đầu vào bộ điều khiển là waypoint và tuổi dữ liệu; đầu ra là `(v, w)` qua safety rồi xuống motor.

### Những phần cần chờ nhau

- B xuất ảnh topomap độc lập; A chỉ trích xuất descriptor sau khi có ảnh và CosPlace chạy được.
- B phát triển controller bằng waypoint mẫu; chỉ nối waypoint thật sau khi A + B xác nhận scale/hệ trục.
- Replay đầy đủ cần model của A và dữ liệu/context của B. Chạy tự hành cần replay đạt yêu cầu, controller được hiệu chỉnh và cơ chế dừng hoạt động.
- Nếu chỉ có một Nano: B thu dữ liệu trước để A làm offline; chia ca benchmark model và hiệu chỉnh motor, tránh hai tiến trình cùng chiếm camera/motor hoặc làm sai số đo hiệu năng.

### Cách phối hợp trong Git

- Mỗi người dùng branch và checkout/worktree riêng; không cùng sửa một working directory.
- A chịu trách nhiệm dependency/model config; B chịu trách nhiệm `main.py`, `PatrolJet`, camera, motor, teleop và safety. Thay đổi chạm phần người kia cần thống nhất trước.
- Ghép thay đổi theo từng phần nhỏ: API → model/ảnh map → replay → controller → tự hành.
- Chỉ đánh dấu hoàn thành khi có đầu ra bàn giao; B cập nhật checklist chung sau khi nhận kết quả từ A để tránh xung đột file này.

## Nền tảng đã có

Các dấu hoàn thành bên dưới được giữ từ checklist trước, chưa kiểm chứng lại
trên phần cứng trong lần rà source này.

- [x] Khởi tạo class PatrolJet với Robot()
- [x] Thiết lập duty và hiệu chỉnh để hạn chế trượt bánh
- [x] Kiểm thử tiến, lùi, rẽ trái, rẽ phải và stop()
- [x] Hoàn thiện class JetCamera: start(), get_frame(), stop()
- [x] Kiểm tra camera: ảnh, FPS, độ trễ và thứ tự màu BGR/RGB
- [x] Có teleop bằng tay cầm USB.
- [x] Có TeachRecorder lưu JPEG, timestamp và lệnh motor khoảng 5 Hz.

## 1. Chạy hai model trên Nano — A, bắt đầu ngay

- [ ] Ghi lại JetPack, Python, PyTorch, torchvision và CUDA thực tế.
- [ ] Tải checkpoint `gnm_large.pth` và `efficientnet_85x85.pth` từ nguồn PlaceNav.
- [ ] Tạo script inference độc lập dùng ảnh mẫu, chưa điều khiển motor.
- [ ] Kiểm tra tương thích torchvision: `ConvNormActivation`, `InvertedResidual`, `_make_divisible` và `Resize(..., antialias=True)`.
- [ ] Điều chỉnh API không tương thích, giữ kiến trúc và preprocessing tương đương bản gốc.
- [ ] Nạp GNM: loader gốc đọc đối tượng model qua `checkpoint["model"]`, có thể phụ thuộc class/module lúc lưu.
- [ ] Nạp CosPlace với EfficientNet-B0, descriptor 512 chiều.
- [ ] Chạy từng model rồi cả hai trong cùng tiến trình; kiểm tra shape, giá trị hữu hạn, RAM và thời gian inference sau warm-up.
- [ ] Dựa vào số đo để quyết định có cần tối ưu hoặc chuyển TensorRT.

Điều kiện hoàn thành: cả hai model chạy được trên Nano và có số đo tài nguyên,
độ trễ. Chỉ import thư viện hoặc nạp một model chưa đủ.

## 2. Chuẩn hóa ảnh và context — A/B theo từng mục

- [ ] B: xác nhận frame JetCamera là BGR hay RGB; bàn giao ảnh kèm thông tin màu.
- [ ] A: đưa ảnh về RGB và áp dụng preprocessing gốc: tensor, resize rộng 85 × cao 64; normalize mean `[0.485, 0.456, 0.406]`, std `[0.229, 0.224, 0.225]`.
- [ ] B: giữ 5 ảnh trước + ảnh hiện tại theo đúng thứ tự với cấu hình GNM mặc định.
- [ ] A: kiểm tra context `[1, 18, 64, 85]`, ảnh subgoal `[1, 3, 64, 85]`, output waypoint `[1, 5, 4]`.
- [ ] B: kiểm soát nhịp lấy context và timestamp; không coi frame lặp/quá hạn là ảnh mới. Code gốc thêm ảnh theo callback camera.
- [ ] A + B: dùng cùng preprocessing cho ảnh topomap và ảnh Repeat.

## 3. Tạo topomap từ phiên teach — B xuất ảnh, A tính descriptor

- [ ] Thu tuyến ngắn khoảng 2–3 m, có ảnh đầu/cuối và timestamp.
- [ ] Chọn ảnh theo `frame_read_s` trong CSV; chỉnh khoảng lấy mẫu theo tốc độ JetBot, tránh nhiều node trùng lúc đứng yên.
- [ ] Xuất thư mục ảnh node `0.jpg`, `1.jpg`, …, `N.jpg`; kiểm tra ảnh đọc được và đúng thứ tự tuyến.
- [ ] A, sau khi nhận ảnh từ B và CosPlace chạy được: trích xuất descriptor cho từng node và lưu/cache database HDF5.
- [ ] A: kiểm tra descriptor khớp thứ tự node; tính lại cache khi đổi ảnh, model hoặc preprocessing.

`navigate.py` đọc ảnh topomap và descriptor, không đọc CSV lệnh motor hay
`traj_data.pkl`. Script tạo map gốc phụ thuộc odometry, nhưng có thể thay bằng
bộ xuất map từ JPEG. Không cần làm odometry trước cho luồng navigation dựa
trên ảnh này; không tạo pose giả.

## 4. Port localization và dự đoán waypoint — A, B cung cấp dữ liệu replay

- [ ] Tách tính toán khỏi ROS: thay subscriber/publisher bằng lời gọi Python; tách các import ROS trong `utils.py` và phụ thuộc liên quan.
- [ ] Port CosPlace FeatureExtractor và một bộ lọc: Bayesian hoặc Sliding Window.
- [ ] Thực hiện ảnh hiện tại → descriptor → node gần nhất.
- [ ] Chọn subgoal phía trước và chặn ở goal; mặc định gốc `lookahead=1`.
- [ ] Gọi GNM với context và ảnh subgoal để lấy chuỗi waypoint.
- [ ] Chọn waypoint điều khiển; mặc định gốc `target_waypoint_idx=2`.
- [ ] Replay dữ liệu độc lập, hiển thị query/node/subgoal/waypoint và độ trễ trước khi bật motor.
- [ ] Đánh giá node dự đoán khi lái lại tuyến thủ công; xử lý map rỗng, dữ liệu lỗi và kết quả không hữu hạn.

## 5. Nối waypoint với motor — B, A cùng xác nhận scale

- [ ] Port phép đổi waypoint → `(v, w)` từ controller PlaceNav làm cơ sở.
- [ ] Đối chiếu cách diễn giải/scale waypoint; không tự mặc định output là mét đã hiệu chỉnh cho JetBot.
- [ ] Hiệu chỉnh `wheelbase`, `v_full`, chiều quay và giới hạn vận tốc.
- [ ] Nối `(v, w)` → `SafetyLayer.filter()` → `JetMotors.drive()`.
- [ ] Kiểm tra chiều quay và dừng khi kê bánh trước khi chạy dưới đất.

## 6. Tích hợp Repeat và dừng an toàn — B chủ trì, A hỗ trợ inference

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
