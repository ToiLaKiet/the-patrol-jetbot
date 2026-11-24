# Checklist triển khai PlaceNav trên JetBot

Mục tiêu: giữ thư viện JetBot cho camera/motor, port phần tính toán PlaceNav.
Checklist dành cho một người: làm lần lượt từ bước 1 đến bước 6.
Đã chạy inference mẫu hai checkpoint trên CUDA của Nano; chưa benchmark.

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

## 1. Chạy hai model trên Nano

- [x] Ghi lại JetPack, Python, PyTorch, torchvision và CUDA thực tế.
- [x] Tải checkpoint `gnm_large.pth` và `efficientnet_85x85.pth` từ nguồn PlaceNav.
- [x] Tạo script inference độc lập dùng ảnh mẫu, chưa điều khiển motor: [infer_sample.py](robot/infer_sample.py), [cách chạy](robot/README.md#inference-độc-lập-với-ảnh-mẫu).
- [x] Kiểm tra tương thích torchvision: `ConvNormActivation`, `InvertedResidual`, `_make_divisible` và `Resize(..., antialias=True)` đã được dùng thành công trong inference mẫu trên Nano.
- [x] Điều chỉnh API không tương thích, giữ kiến trúc và preprocessing tương đương bản gốc: không cần đổi bốn API torchvision trên trong luồng inference mẫu.
- [x] Nạp GNM: xử lý đường dẫn class cũ `gnm_train.models.gnm.GNM` và nạp weights strict từ `checkpoint["model"]`; đã chạy trên CUDA của Nano.
- [x] Nạp CosPlace với EfficientNet-B0, descriptor 512 chiều; đã chạy trên CUDA của Nano.
- [ ] Chạy từng model rồi cả hai trong cùng tiến trình; kiểm tra shape, giá trị hữu hạn, RAM và thời gian inference sau warm-up.
- [ ] Dựa vào số đo để quyết định có cần tối ưu hoặc chuyển TensorRT.

Kết quả CLI do người dùng cung cấp trên `nano-4gb-jp45` (2026-11-24):
L4T `32.5.0`, gói `nvidia-l4t-core` phiên bản `32.5.0-20210115145440`,
kiến trúc `aarch64` theo `/etc/nv_tegra_release`. Nền tảng tương ứng JetPack
`4.5` theo [đối chiếu NVIDIA](https://developer.nvidia.com/embedded/linux-tegra-r325);
không có gói `nvidia-jetpack` trong kết quả truy vấn. CUDA toolkit `10.2.89`
được xác nhận bằng `/usr/local/cuda/bin/nvcc --version` (release `10.2`).

Môi trường robot được kiểm tra bằng
`/home/jetbot/the-patrol-jetbot/robot/.venv/bin/python`, với
`OPENBLAS_CORETYPE=ARMV8`:

| Thành phần | Kết quả CLI |
| --- | --- |
| Python | `3.6.9` (GCC `8.4.0`) |
| PyTorch | `1.10.0` |
| torchvision | `0.11.1` |
| CUDA dùng để build PyTorch | `10.2` |
| `torch.cuda.is_available()` | `True` |

Phép thử CLI riêng trên Nano do người dùng cung cấp (2026-11-24), với
PyTorch `1.10.0` / torchvision `0.11.1`: cả `ConvNormActivation`,
`InvertedResidual`, `_make_divisible` và `Resize(..., antialias=True)` trên
tensor đều báo `OK`; kết quả cuối `PASS`. Không cần đổi bốn API này cho
luồng inference mẫu hiện tại.

Script `robot/infer_sample.py` đã chạy trên máy phát triển bằng CPU
(Python `3.10.16`, Torch `2.12.1`, torchvision `0.27.1`) với hai checkpoint
Drive ở trên và ảnh `PlaceNav/doc/githeader_hor.png` lặp làm context.
GNM trả distance `[1, 1]`, waypoint `[1, 5, 4]`; CosPlace trả descriptor
`[1, 512]`, L2 norm `1.0`; các output hữu hạn. Cả 42 test tự động đều qua,
gồm 6 test cho script.

Kết quả inference trên Nano do người dùng cung cấp (2026-11-24): chạy
`infer_sample.py --device cuda` với cùng ảnh mẫu lặp làm context, lần lượt
GNM rồi CosPlace trong cùng tiến trình. Context `[1, 18, 64, 85]`, ảnh goal
`[1, 3, 64, 85]`; GNM trả distance `[1, 1]` (giá trị `-0.08656612038612366`)
và waypoint `[1, 5, 4]`; CosPlace trả descriptor `[1, 512]`, L2 norm `1.0`.
Script kết thúc thành công, các output hữu hạn. Đây là smoke test với một
ảnh lặp, chưa đánh giá độ chính xác trên context chuyển động thực, RAM,
thời gian inference sau warm-up hoặc khả năng giữ cả hai model cùng lúc trong RAM.

Điều kiện hoàn thành: cả hai model chạy được trên Nano và có số đo tài nguyên,
độ trễ. Chỉ import thư viện hoặc nạp một model chưa đủ.

## 2. Chuẩn hóa ảnh và context

- [ ] Xác nhận frame JetCamera là BGR hay RGB.
- [ ] Đưa ảnh về RGB và áp dụng preprocessing gốc: tensor, resize rộng 85 × cao 64; normalize mean `[0.485, 0.456, 0.406]`, std `[0.229, 0.224, 0.225]`.
- [ ] Giữ 5 ảnh trước + ảnh hiện tại theo đúng thứ tự với cấu hình GNM mặc định.
- [ ] Kiểm tra context `[1, 18, 64, 85]`, ảnh subgoal `[1, 3, 64, 85]`, output waypoint `[1, 5, 4]`.
- [ ] Kiểm soát nhịp lấy context và timestamp; không coi frame lặp/quá hạn là ảnh mới. Code gốc thêm ảnh theo callback camera.
- [ ] Dùng cùng preprocessing cho ảnh topomap và ảnh Repeat.

## 3. Tạo topomap từ phiên teach

- [ ] Thu tuyến ngắn khoảng 2–3 m, có ảnh đầu/cuối và timestamp.
- [ ] Chọn ảnh theo `frame_read_s` trong CSV; chỉnh khoảng lấy mẫu theo tốc độ JetBot, tránh nhiều node trùng lúc đứng yên.
- [ ] Xuất thư mục ảnh node `0.jpg`, `1.jpg`, …, `N.jpg`; kiểm tra ảnh đọc được và đúng thứ tự tuyến.
- [ ] Sau khi có ảnh topomap và CosPlace chạy được: trích xuất descriptor cho từng node và lưu/cache database HDF5.
- [ ] Kiểm tra descriptor khớp thứ tự node; tính lại cache khi đổi ảnh, model hoặc preprocessing.

`navigate.py` đọc ảnh topomap và descriptor, không đọc CSV lệnh motor hay
`traj_data.pkl`. Script tạo map gốc phụ thuộc odometry, nhưng có thể thay bằng
bộ xuất map từ JPEG. Không cần làm odometry trước cho luồng navigation dựa
trên ảnh này; không tạo pose giả.

## 4. Port localization và dự đoán waypoint

- [ ] Tách tính toán khỏi ROS: thay subscriber/publisher bằng lời gọi Python; tách các import ROS trong `utils.py` và phụ thuộc liên quan.
- [ ] Port CosPlace FeatureExtractor và một bộ lọc: Bayesian hoặc Sliding Window.
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
