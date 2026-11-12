# Luồng ứng dụng

[main.py](main.py) đọc và kiểm tra CLI trước khi import phần cứng.
Trên ARM64, entry point đặt mặc định `OPENBLAS_CORETYPE=ARMV8` trước các
thư viện native. Sau đó tạo một `PatrolJet`, gọi `run_teleop()` và luôn
`close()` trong `finally`.

```mermaid
sequenceDiagram
    participant Main as main.py
    participant Robot as PatrolJet
    participant Rec as TeachRecorder
    participant Pad as Teleop
    Main->>Robot: Khởi tạo motor, camera wrapper, safety
    Main->>Robot: run_teleop(..., teach_dir)
    opt Có teach_dir
        Robot->>Robot: Bật camera và dừng motor
        Robot->>Rec: start() ở thread nền
    end
    Robot->>Pad: run() trên thread chính
    Pad->>Pad: Đọc tay cầm, kiểm tra safety, gửi lệnh
    Pad-->>Robot: Kết thúc hoặc báo lỗi; dừng motor
    Main->>Robot: close() trong finally
    Robot->>Robot: Dừng motor
    Robot->>Rec: close() nếu có recorder
    Robot->>Robot: Đóng camera
```

| Module | Vai trò trong luồng hiện tại |
| --- | --- |
| [hardware](hardware/README.md) | `PatrolJet` sở hữu thiết bị và nối các module |
| [teleop](teleop/README.md) | Tạo lệnh hai bánh từ joystick |
| [safety](safety/README.md) | Cho phép chạy hoặc yêu cầu dừng |
| [teach](teach/README.md) | Lấy mẫu ảnh và lệnh motor ở nền |
| [humandetector](humandetector/README.md) | Chưa được entry point gọi |
| [mapping](mapping/README.md), [navigation](navigation/README.md) | Chưa có triển khai |

Lệnh chạy và tham số nằm trong [hướng dẫn robot](../README.md).
