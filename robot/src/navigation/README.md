# Navigation

[main.py](main.py) là entry point độc lập của Navigation. Luồng dự kiến theo
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

Chạy từ `robot/`:

```sh
uv run --no-sync python src/navigation/main.py
```

Hiện lệnh này sẽ báo chưa triển khai và thoát trước khi
khởi tạo camera/motor. Chưa có chế độ tự hành hoạt động.

Kết quả kiểm tra model đã có trong [checklist](../../../checklist.md).
Preprocessing dùng chung [utils.preprocess_frame](../utils.py).
