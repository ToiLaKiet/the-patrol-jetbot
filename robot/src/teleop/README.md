# Teleop bằng tay cầm USB

Tài liệu này mô tả cách dùng và thiết kế `teleop.py` đã triển khai.
Mục tiêu là đọc TGZ Controller cắm trực tiếp vào Jetson bằng Pygame,
điều khiển hai bánh qua `jetbot.Robot`, không cần Jupyter.
Pygame được quản lý bằng uv trong thư mục `robot/`.

## Phân chia trách nhiệm

| Thành phần | Trách nhiệm |
| --- | --- |
| `Teleop` trong `teleop.py` | Kết nối tay cầm, đọc cần/L1, xử lý vùng chết, trộn và làm mượt lệnh |
| `JetMotors` | Kiểm tra lệnh, áp dụng giới hạn công suất và gọi `jetbot.Robot.set_motors()` |
| `SafetyLayer` | Kiểm tra điều kiện cho phép chạy, ghi đè lệnh khi cần dừng |
| `PatrolJet` | Sở hữu các thành phần, tạo phiên teleop và quản lý vòng đời robot |
| `main.py` | Tạo robot, bắt đầu teleop và luôn đóng robot khi thoát |

Tách `Teleop` thành class vì nó giữ thiết bị đang kết nối, lệnh hai bánh
trước đó và thời điểm cập nhật để làm mượt. Dùng lại motor của `PatrolJet`,
không tạo thêm đối tượng JetBot điều khiển cùng phần cứng.

API:

```python
class Teleop:
    def __init__(self, motors, safety, max_speed=0.25, deadzone=0.08, slew_rate=0.5):
        ...

    def run(self):
        ...
```

`PatrolJet.run_teleop(max_speed=...)` tạo `Teleop` với `self.motors` và
`self.safety`, rồi gọi `run()`. `PatrolJet` khởi tạo `SafetyLayer` khi tạo robot.
Tạo `PatrolJet(...)` chưa bắt đầu vòng lặp điều khiển.
Vòng lặp teleop chạy trên luồng chính, chưa cần thêm thread.

Ví dụ sử dụng trong `main.py`:

```python
from hardware.patroljet import PatrolJet

robot = PatrolJet("Patrol-01")
try:
    robot.run_teleop(max_speed=0.25)
finally:
    robot.close()
```

Teleop không yêu cầu bật camera. `Teleop.run()` phải dừng motor và dọn Pygame
trong `finally`, kể cả khi kết nối hoặc vòng lặp gặp lỗi.

Từ thư mục `robot/` trên Jetson, sau khi đồng bộ dependency bằng uv:

```sh
uv run --no-sync python src/main.py
```

Thay `max_speed` trong `src/main.py` để đổi giới hạn công suất. Khi cần chỉnh
`deadzone` hoặc `slew_rate`, truyền chúng lúc tạo `Teleop` trong
`PatrolJet.run_teleop()`. Chưa có tùy chọn dòng lệnh cho các giá trị này.

## Kết nối và mapping đã xác nhận

Jetson đã nhận TGZ trong môi trường uv: Python 3.8.20, Pygame 2.6.1,
SDL 2.28.4, 6 axes và 15 buttons. Đặt các biến sau trước khi khởi tạo SDL:

```python
import os

os.environ["SDL_LINUX_JOYSTICK_CLASSIC"] = "1"
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
```

| Đầu vào | Ý nghĩa |
| --- | --- |
| Axis 1 âm | Đẩy cần trái lên, tiến |
| Axis 0 dương | Đẩy cần trái sang phải, rẽ phải |
| Button 6 | L1: giữ để chạy, thả để dừng |
| Axis 0 và 1 về 0 | Cần trái ở giữa |

Khi mở thiết bị, kiểm tra đủ axes/buttons và theo dõi đúng instance ID.
Ban đầu phải đưa cần về giữa và thả L1, rồi nhấn L1 mới cho phép chạy.
Mất thiết bị thì kết thúc phiên; không tự kết nối lại và chạy tiếp lệnh cũ.

## Từ joystick đến lệnh motor

Luồng xử lý ở khoảng 50 Hz:

```text
Đọc sự kiện và trạng thái cần/L1
    → kiểm tra dữ liệu và điều kiện cho phép chạy
    → vùng chết và quy đổi lại biên độ
    → trộn tiến/rẽ, giới hạn theo max_speed
    → làm mượt bằng slew_rate
    → kiểm tra an toàn lần cuối
    → JetMotors → jetbot.Robot
```

### Vùng chết

Với `deadzone=0.08`, giá trị trục có độ lớn không quá 0.08 được coi là 0.
Ngoài khoảng đó, quy đổi liên tục về toàn thang:

```text
|axis| <= deadzone: output = 0
|axis| > deadzone:  output = sign(axis) × (|axis| - deadzone) / (1 - deadzone)
```

Như vậy vừa vượt vùng chết chỉ tạo một lệnh nhỏ, không nhảy ngay lên 8%.

### Trộn tiến và rẽ

Sau vùng chết, lấy `forward = -axis_y`, `turn = axis_x` rồi tính:

```text
left  = forward + turn
right = forward - turn
scale = max(1, |left|, |right|)
left  = max_speed × left / scale
right = max_speed × right / scale
```

Vừa tiến vừa đẩy phải tạo đường cong; chỉ đẩy ngang tạo xoay tại chỗ.
Chuẩn hóa cả hai bánh theo cùng tỷ lệ để giữ hướng rẽ khi bão hòa.

`max_speed` là mức lệnh motor chuẩn hóa, không phải m/s. Ví dụ `0.25`
giới hạn độ lớn lệnh mỗi bánh ở 0.25, trước hiệu chỉnh motor.
Giới hạn hiệu dụng không được vượt `JetMotors.max_duty` hiện có.
Kiểm tra tham số hữu hạn: `0 < max_speed <= 1`, `0 <= deadzone < 1`,
`slew_rate > 0`; kiểm tra dữ liệu axes hữu hạn và trong khoảng [-1, 1].
Dữ liệu không hợp lệ phải dẫn tới dừng, không giữ lệnh cũ.

### Slew rate là gì?

`slew_rate` là mức thay đổi lệnh motor tối đa trong một giây, giúp tránh
nhảy công suất khi người lái giật cần. Đơn vị là mức lệnh/giây, không phải m/s².

Ví dụ `slew_rate=0.5`, chu kỳ 0.02 giây:

```text
Mức thay đổi tối đa mỗi chu kỳ = 0.5 × 0.02 = 0.01
Từ lệnh 0 lên 0.25 cần ít nhất 0.5 giây.
Từ +0.25 xuống -0.25 cần ít nhất 1 giây, đi qua 0.
```

Đo thời gian thực tế bằng `time.monotonic()`, không giả định mọi vòng đều
đúng 0.02 giây. Mỗi bánh tiến về lệnh mục tiêu với mức thay đổi không quá
`slew_rate × dt`. Lệnh đầu và trạng thái làm mượt sau khi dừng đều là 0.
Nếu vòng lặp bị gián đoạn quá thời hạn điều khiển, dừng và yêu cầu thả L1,
đưa cần về giữa rồi nhấn lại; không dùng khoảng `dt` lớn để nhảy công suất.

Slew rate nhỏ hơn cho thay đổi chậm hơn; lớn hơn cho phản hồi nhanh hơn.
Thả cần thông thường giảm lệnh từ từ. Các thông số ban đầu `max_speed=0.25`,
`deadzone=0.08`, `slew_rate=0.5` phải được chỉnh sau khi thử phần cứng.

## Dừng và lớp an toàn

Thả L1, mất tay cầm, dữ liệu lỗi, yêu cầu dừng an toàn, Ctrl+C hoặc exception
phải bỏ qua slew rate, gửi lệnh dừng ngay và xóa lệnh làm mượt cũ.
Lệnh 0 không có nghĩa bánh xe dừng cơ học tức thì.

`SafetyLayer.filter()` nhận m/s và rad/s, không được truyền công suất
chuẩn hóa vào các tham số đó. Teleop dùng `SafetyLayer.check()` để kiểm tra
điều kiện chung trước khi gửi lệnh công suất; API vận tốc vẫn có giới hạn riêng.
Teleop thủ công không yêu cầu định vị hoặc camera. Chỉ báo trạng thái pin khi
có nguồn đo thật; không coi giá trị mặc định là đã giám sát được pin.

`SafetyLayer` chỉ kiểm tra khi được gọi; nó không phải watchdog độc lập.
Không dùng thời điểm thay đổi axis làm thời điểm lệnh mới: giữ nguyên cần
vẫn là thao tác hợp lệ. Kiểm tra kết nối và tạo lệnh ở mỗi chu kỳ.
Nếu tiến trình hoặc hệ điều hành treo, vòng lặp phần mềm không thể bảo đảm
dừng motor; muốn bảo đảm trường hợp đó cần watchdog ở phần cứng/driver.

`JetMotors.set_motors()` kiểm tra đầu vào hữu hạn, giữ tỷ lệ hai bánh khi
giới hạn theo `max_duty` và gọi `self.robot.set_motors(left, right)`.
Nếu đầu vào lỗi hoặc ghi motor thất bại, nó gọi dừng trước khi báo lỗi.
Giữ hiệu chỉnh hai bánh hiện có, không cần dùng `to_wheels()` vì teleop
này điều khiển trực tiếp công suất, chưa điều khiển vận tốc vật lý.

## Kiểm tra

Kiểm tra tự động từ `robot/`, không truy cập phần cứng và không cần cài JetBot:

```sh
PYTHONPATH=src uv run --no-sync python -m unittest discover -s tests -v
```

Các test kiểm tra vùng chết, dấu tiến/rẽ, bão hòa, slew rate theo thời gian,
L1, chặn an toàn, ngắt kết nối, dữ liệu lỗi và dọn tài nguyên khi exception.

Kiểm tra phần cứng còn phải thực hiện trên Jetson:

1. Chạy từ `robot/` bằng `uv run --no-sync python src/main.py`.
   Kê bánh khỏi đất để xác nhận chiều quay, thả L1 và rút USB đều gửi lệnh dừng.
2. Thử dưới đất ở công suất thấp, chỉnh độ tăng công suất và cân hai bánh.

Chưa bổ sung PID, đo tốc độ bánh, giao diện hoặc điều khiển qua mạng.
Độ mượt thực tế còn phụ thuộc ngưỡng khởi động motor, tải, pin và mặt sàn.
