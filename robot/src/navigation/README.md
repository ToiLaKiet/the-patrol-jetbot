# Navigation

[main.py](main.py) chạy **định vị bằng CosPlace + Bayesian filter**. Thêm
`--navigate` để nối **chọn subgoal → GNM predict waypoints → controller → `(v, w)`**
trên chuỗi ảnh. `--live` chạy camera trực tiếp → navigation → safety → motor.

| Phần | File | Trạng thái |
| --- | --- | --- |
| Inference/định vị | [inference.py](inference.py) | Đọc map, trích descriptor và tìm node từ frame BGR |
| Place recognition | [place_recognition/](place_recognition/) | CosPlace/EfficientNet-B0 và Bayesian filter, không phụ thuộc ROS/odometry |
| Lõi điều hướng Bayesian | [navigate.py](navigate.py) | Context 6 ảnh → node → subgoal → GNM → `(v, w)` |
| Predict waypoints | [gnm.py](gnm.py) | Nạp GNM Large và chạy inference; không cần checkout PlaceNav hoặc gnm_train |
| PD controller → `(v, omega)` | [pd_controller.py](pd_controller.py) | Đã nối với predict và motor qua `--live` |
| Repeat trực tiếp | [live.py](live.py) | Inference nền; vòng chính kiểm tra timeout và gửi motor |
| Safety | [safety.py](../safety/safety.py) | `--live` kiểm tra tuổi ảnh/waypoint, posterior và giới hạn vận tốc |
| `(v, omega)` → hai bánh | [motors.py](../hardware/motors.py) | `--live` gọi `JetMotors.drive()` với hiệu chỉnh bắt buộc |

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

API định vị dùng lại cho camera JetBot:

```python
from navigation.inference import PlaceRecognition

localizer = PlaceRecognition("topomaps/route_a", "checkpoints/efficientnet_85x85.pth")
node, posterior = localizer.match(frame)  # frame BGR uint8, HWC
```

Tạo một localizer cho mỗi phiên và gọi `match()` một lần cho mỗi frame mới,
theo thứ tự thời gian để giữ trạng thái Bayesian. Các mặc định theo CLI PlaceNav:
`delta=10`, transition window `[-1, 2)`. Map một node/descriptor trùng được xử lý
không sinh NaN; trường hợp không phân biệt được có thể trả phân bố đều.

Lệnh dùng `--query` không khởi tạo camera hoặc motor.

## Repeat trực tiếp → motor

Chạy từ `robot/`, dùng `--live` thay `--query`. Không cần thêm `--navigate`.
Thay các giá trị `<...>` bằng số đã đo/kiểm tra, không gõ nguyên dấu ngoặc:

```sh
uv run --no-sync python src/navigation/main.py \
  --live --topomap-dir topomaps/route_a \
  --max-v 0.10 --max-w 0.60 --max-duty 0.10 \
  --wheelbase <khoang_cach_hai_banh_m> \
  --v-full <van_toc_banh_o_duty_1_m_s> \
  --min-posterior <nguong_da_kiem_tra_tren_tuyen>
```

`wheelbase` tính bằng mét; `v_full` là vận tốc bánh ước lượng ở duty=1 theo
mô hình tuyến tính của motor, có thể suy ra từ phép đo ở duty thấp.
Không cần chạy bánh ở duty=1 để đo. `min_posterior` thuộc (0, 1], phải chọn bằng
lượt đi lại độc lập; posterior cao vẫn có thể định vị sai. Các giới hạn vận tốc
trên chỉ minh họa. Kê bánh kiểm tra chiều quay trước khi chạy dưới đất.

Model và descriptor map được nạp trước khi mở phần cứng. `PatrolJet` quản lý
camera/motor; motor đứng yên khi gom context 6 ảnh. Camera lấy timestamp monotonic
từ callback frame mới, không làm mới timestamp khi đọc lại cùng frame. Timestamp
này là lúc callback tới CPU, không phải lúc phơi sáng của cảm biến.

Inference chạy ở thread nền, kết quả đi qua hàng đợi tối đa một phần tử.
Chỉ vòng chính được ghi motor: kiểm tra an toàn → `SafetyLayer.filter()` →
`JetMotors.drive()`. Vòng chính kiểm tra khoảng 20 ms một lần khi chờ inference.
`--command-timeout` mặc định 1 giây, tính từ timestamp ảnh tạo waypoint;
không gia hạn bằng việc gửi lại vận tốc cũ. Chưa có waypoint đầu tiên sau thời gian
gom context cộng timeout cũng kết thúc phiên. Đây là ngưỡng dừng lỗi, không phải
cam kết đạt 5 Hz; cần đo timing thực tế trên Nano.

Phiên dừng khi callback camera ngừng, ảnh/waypoint quá hạn, context gián đoạn,
posterior dưới ngưỡng, model/controller/motor báo lỗi, tới goal hoặc `Ctrl+C`.
Motor được dừng trước khi đóng camera. Điều kiện goal hiện vẫn là `node == goal`
ở một quan sát, có thể dừng sớm do định vị sai.

Chưa giám sát pin, tránh vật cản hoặc tiếp quản joystick trong chế độ này.
Watchdog Python không bảo vệ được khi toàn tiến trình/GIL/driver bị treo hoặc
tiến trình bị kill cứng; cần watchdog phía motor cho trường hợp đó. Callback vẫn
chạy nhưng lặp nội dung ảnh cũng chưa được phát hiện. Chưa kiểm chứng trên JetBot thật.

Kiểm tra motor giả, camera giả và timeout:

```sh
uv run --no-sync python scripts/check_live_navigation.py
```

## Bayesian + GNM → `(v, w)`

Chạy từ `robot/`, với ít nhất 6 ảnh Teach theo thứ tự cũ → mới:

```sh
uv run --no-sync python src/navigation/main.py \
  --navigate --topomap-dir topomaps/route_a --query teach/run_.../images \
  --gnm-checkpoint checkpoints/gnm_large.pth --max-v 0.10 --max-w 0.60
```

Giới hạn trên chỉ minh họa, chưa hiệu chỉnh cho JetBot. `--checkpoint` vẫn là
checkpoint CosPlace; `--gnm-checkpoint` là checkpoint GNM Large tải từ README
PlaceNav. Loader GNM đọc model/optimizer pickled trên CPU rồi nạp trọng số vào
kiến trúc GNM cục bộ và chuyển sang device. Chỉ dùng checkpoint từ nguồn tin cậy.
Không cần cài `gnm_train`, ROS hoặc tải thêm trọng số ImageNet.

Sau 6 ảnh đầu, mỗi ảnh mới cho một kết quả:

```text
t=1.000 node=0 posterior=0.9234 subgoal=1 v=0.090030 w=0.217337 goal=False time_ms=... waypoint=[...]
```

Các giá trị trên minh họa định dạng. Lõi dùng lại Bayesian đã có, khởi tạo belief
từ query đầu tiên sau khi đủ context, không dùng sliding window hoặc start node.
`--lookahead` mặc định 1, `--target-waypoint-idx` mặc định 2 (waypoint thứ ba),
`--goal-node-idx` mặc định -1 (node cuối), `--frame-rate` mặc định 5 Hz.
Ảnh topomap được tiền xử lý và giữ trên CPU; chỉ ảnh subgoal được chuyển tới device
ở mỗi lần predict. Waypoint normalized đi thẳng vào controller, scale một lần bên trong.

CLI đọc ảnh nhanh nhất có thể, dùng timestamp giả định `index / frame_rate`;
không phát lại theo thời gian thực và không đọc `samples.csv`. Để đánh giá timing
hoặc nối camera, cần cung cấp timestamp thu ảnh thực và kiểm tra độ mới của ảnh.
Không dùng ảnh topomap đã lấy mẫu 2 giây làm context thay cho ảnh quan sát liên tiếp.

API của lõi nhận iterable `(timestamp_seconds, frame_BGR)`:

```python
from navigation.gnm import load_gnm
from navigation.navigate import navigate

model = load_gnm("checkpoints/gnm_large.pth", device="cuda")
# localizer là PlaceRecognition được tạo một lần cho phiên; observations là ảnh mới có timestamp.
for result in navigate(observations, localizer, model, max_v=0.10, max_w=0.60):
    print(result["node"], result["subgoal"], result["v"], result["w"])
```

Context giữ 6 ảnh, bỏ qua timestamp trùng và từ chối timestamp lùi/NaN/Inf.
Kết quả gồm node, posterior, subgoal, distance, toàn bộ waypoint, waypoint được chọn,
`v`, `w`, `reached_goal` và thời gian xử lý. Tới đích theo điều kiện `node == goal`
thì trả `(0, 0)` và kết thúc, không phát thêm dự đoán chuyển động.
Đây chưa phải tiêu chí dừng đã kiểm chứng trên robot; posterior chưa có ngưỡng tin cậy.
Lỗi ảnh/model/controller được báo lên bên gọi; bên điều khiển motor phải dừng khi lỗi.
Lõi không mở camera/motor, không chạy watchdog và không tự đảm bảo nhịp 5 Hz.

Kiểm tra CPU, không mở phần cứng:

```sh
uv run --no-sync python scripts/check_navigation.py
```

Script kiểm tra loader/checkpoint, thứ tự context, Bayesian, subgoal, scale,
điều kiện goal và dữ liệu lỗi. Bài kiểm tra forward checkpoint thật được bỏ qua
nếu chưa có `checkpoints/gnm_large.pth`.

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
