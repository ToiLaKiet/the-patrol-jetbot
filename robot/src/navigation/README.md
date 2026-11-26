# Navigation

[main.py](main.py) hiện chạy **định vị trên ảnh bằng CosPlace + Bayesian filter**.
Luồng tự hành tiếp theo là **chọn subgoal → GNM predict waypoints → PD controller
đổi sang `(v, omega)` → safety → `drive()`**, chưa được nối.

| Phần | File | Trạng thái |
| --- | --- | --- |
| Inference/định vị | [inference.py](inference.py) | Đọc map, trích descriptor và tìm node từ frame BGR |
| Place recognition | [place_recognition/](place_recognition/) | CosPlace/EfficientNet-B0 và Bayesian filter, không phụ thuộc ROS/odometry |
| Chọn subgoal | — | Chưa triển khai |
| Predict waypoints | — | Chưa nối GNM vào Navigation |
| PD controller → `(v, omega)` | [pd_controller.py](pd_controller.py) | Đã có hàm Python và CLI thử waypoint normalized; chưa nối với predict/motor |
| Safety | [safety.py](../safety/safety.py) | Đã có, chưa nối với Navigation |
| `(v, omega)` → hai bánh | [motors.py](../hardware/motors.py) | Đã có `JetMotors.drive()`, chưa nối với Navigation |

Chạy từ `robot/`:

```sh
uv run --no-sync python src/navigation/main.py \
  --topomap-dir topomaps/route_a \
  --query teach/run_.../images
```

Thay `run_...` bằng thư mục ảnh thực tế. `--query` nhận một ảnh hoặc một thư mục
ảnh có tên số (JPEG/PNG), được đọc theo thứ tự số. Topomap phải có chỉ số node
liên tiếp từ 0, chẳng hạn `0.jpg`, `1.jpg`, …

Checkpoint mặc định là `checkpoints/efficientnet_85x85.pth`, chọn file khác bằng
`--checkpoint`. Mặc định chạy CUDA; dùng `--device cpu` để kiểm tra trên CPU.
Model được dựng từ source CosPlace đi kèm, không cần thư mục PlaceNav gốc và
không tải thêm trọng số ImageNet. Dùng PyTorch/torchvision đã cài cho JetBot.

Mỗi ảnh query in một dòng:

```text
000025.jpg -> node=1 posterior=0.9234 time_ms=50.2
```

`node` là node gần nhất theo bộ lọc, chưa phải subgoal. `posterior` là xác suất
chuẩn hóa trong các node của map, không phải ngưỡng tin cậy đã hiệu chỉnh để
cho phép chạy motor hay xác nhận đến đích. Thời gian gồm preprocessing và match,
không gồm đọc JPEG hoặc nạp model/trích descriptor map lúc khởi động.

Descriptor map giữ trong RAM theo đúng thứ tự node và được tính lại mỗi lần
khởi chạy; chưa có cache HDF5. Cả ảnh map và query dùng chung
[utils.preprocess_frame](../utils.py). CLI xử lý từng ảnh theo thứ tự, không mô
phỏng thời gian phát lại. Thử lại trên ảnh Teach chỉ là kiểm tra kết nối;
đánh giá định vị cần ảnh của một lượt đi lại độc lập.

Khi nối với camera JetBot sau này, tái sử dụng API:

```python
from navigation.inference import PlaceRecognition

localizer = PlaceRecognition("topomaps/route_a", "checkpoints/efficientnet_85x85.pth")
node, posterior = localizer.match(frame)  # frame BGR uint8, HWC
```

Tạo một localizer cho mỗi phiên và gọi `match()` một lần cho mỗi frame mới,
theo thứ tự thời gian để giữ trạng thái Bayesian. Các mặc định theo CLI PlaceNav:
`delta=10`, transition window `[-1, 2)`. Map một node/descriptor trùng được xử lý
không sinh NaN; trường hợp không phân biệt được có thể trả phân bố đều.

Lệnh này chưa khởi tạo camera hoặc motor. Chưa có chế độ tự hành hoạt động.

## Waypoint normalized → vận tốc

`waypoint_to_velocity(waypoint, max_v, max_w, frame_rate=5.0)` nhận **một**
waypoint GNM chưa scale: `[x, y]` hoặc `[x, y, cos_yaw, sin_yaw]`.
`x` hướng trước, `y` và vận tốc quay dương hướng trái. Hàm trả `(v, w)` theo
m/s và rad/s; `max_v > 0`, `max_w >= 0` là giới hạn vận tốc, không phải duty.

Theo [deployment GNM gốc](https://github.com/robodhruv/drive-any-robot/blob/main/deployment/src/navigate.py),
hàm tự scale `x, y` bằng `max_v / frame_rate` đúng một lần, giữ heading,
rồi dùng công thức controller PlaceNav với `DT = 1 / frame_rate`.
Khi `x > 0` và không sát gốc, công thức tương đương
`v = raw_x * max_v`, `w = atan(raw_y / raw_x) * frame_rate` trước giới hạn.
Scale này tạo độ dài điều khiển cho robot đích, không đo khoảng cách thực
từ ảnh. `frame_rate` là nhịp điều khiển mục tiêu, không phải thời gian inference.

Sau khi có output tensor GNM `[1, 5, 4]`, cách gọi là:

```python
from navigation.pd_controller import waypoint_to_velocity

chosen = waypoints[0, 2].detach().cpu().numpy()  # waypoint thứ ba, chưa scale
v, w = waypoint_to_velocity(chosen, max_v=0.10, max_w=0.60, frame_rate=5.0)
print(v, w)
```

Các giới hạn trên chỉ minh họa, chưa được hiệu chỉnh trên JetBot.
Thử trực tiếp từ `robot/`, không nạp model hoặc mở phần cứng:

```sh
uv run --no-sync python src/navigation/pd_controller.py \
  --waypoint 0.9002965688705444 0.03915815055370331 0.99998939037323 -0.00460240850225091 \
  --max-v 0.10 --max-w 0.60
```

Kết quả: `v=0.090030 m/s, w=0.217337 rad/s`.

Hàm xử lý quay tại chỗ khi `x` gần 0; tại gốc, waypoint 2D trả vận tốc 0,
waypoint 4D dùng heading. Dữ liệu sai shape, NaN/Inf, heading bằng vector 0,
tham số không hợp lệ hoặc waypoint phía sau (`x < 0`) gây `ValueError`.
Bên sở hữu motor phải bắt lỗi và dừng; hàm không tự dừng motor hoặc chạy watchdog.
Trước khi chạy thực tế cần nối qua `SafetyLayer.filter()` rồi `JetMotors.drive()`,
kiểm tra tuổi ảnh/waypoint và hiệu chỉnh motor.

Chạy kiểm tra độc lập, chỉ cần Python chuẩn:

```sh
uv run --no-sync python -m unittest discover -s tests -p 'test_pd_controller.py' -v
```

Source model/filter được tái sử dụng từ PlaceNav; giấy phép tại
[LICENSE.PlaceNav](place_recognition/LICENSE.PlaceNav).

Kết quả kiểm tra model đã có trong [checklist](../../../checklist.md).
