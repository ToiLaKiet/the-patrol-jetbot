# Tests

Chạy từ `robot/`:

```sh
PYTHONPATH=src uv run --no-sync python -m unittest discover -s tests -v
```

Dùng `unittest` và mock để thay JetBot, Pygame và phần cứng.
Test recorder ghi JPEG/CSV thật vào thư mục tạm bằng NumPy/OpenCV.

| File | Kiểm tra |
| --- | --- |
| [test_camera.py](test_camera.py) | Chặn backend thiếu GStreamer trước khi mở camera, mở/đóng camera giả |
| [test_main.py](test_main.py) | Tham số CLI, truyền teach_dir, dọn robot khi lỗi |
| [test_teleop.py](test_teleop.py) | Mapping, vùng chết, slew rate, safety, motor và vòng đời teach |
| [test_teach_recorder.py](test_teach_recorder.py) | Ảnh khớp CSV, lệnh dừng, lỗi camera/ghi đĩa, phiên riêng |
| [test_jetbot_env.py](test_jetbot_env.py) | Checker môi trường, subprocess và workaround OpenBLAS |

Các test không truy cập motor thật, không xác nhận được GStreamer, chiều quay,
tốc độ cơ học, độ trễ joystick hoặc độ chính xác timestamp camera trên Nano.
Chưa có test riêng cho nhận diện người; mapping/navigation chưa triển khai.
