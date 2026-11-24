# Navigation

[main.py](main.py) là điểm vào của `main.py navigation`. Luồng dự kiến theo
PlaceNav: **inference/định vị → chọn subgoal → GNM predict waypoints →
PD controller đổi sang `(v, omega)` → safety → `drive()`**.

| Phần | File | Trạng thái |
| --- | --- | --- |
| Inference/định vị | [PlaceNav/inference.py](PlaceNav/inference.py) | File trống, chưa có vòng lặp runtime |
| Chọn subgoal | [PlaceNav/subgoal.py](PlaceNav/subgoal.py) | File trống |
| Predict waypoints | [PlaceNav/waypoints.py](PlaceNav/waypoints.py) | File trống |
| PD controller → `(v, omega)` | [PlaceNav/pd_controller.py](PlaceNav/pd_controller.py) | File trống |
| Safety | [safety.py](../safety/safety.py) | Đã có, chưa nối với Navigation |
| `(v, omega)` → hai bánh | [motors.py](../hardware/motors.py) | Đã có `JetMotors.drive()`, chưa nối với Navigation |

Hiện chạy `main.py navigation` sẽ báo chưa triển khai và thoát trước khi
khởi tạo camera/motor. Chưa có chế độ tự hành hoạt động.

Model đã chạy độc lập trong [infer_sample.py](../../scripts/infer_sample.py).
Preprocessing dùng chung [utils.preprocess_frame](../utils.py). Các phần này
sẽ được dùng lại khi triển khai Navigation; không sao chép ROS node vào entry point.
