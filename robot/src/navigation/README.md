# Navigation

[mapping.py](mapping.py) hiện là file trống. Thư mục này chưa có vòng lặp
định vị, chọn mục tiêu hoặc điều khiển tự hành; `main.py` chưa gọi nó.

Robot hiện chạy bằng [teleop](../teleop/README.md). Bộ đổi vận tốc
`JetMotors.drive(v, w, wheelbase, v_full)` đã có trong
[hardware](../hardware/README.md), nhưng chưa nối với PlaceNav hoặc ROS Twist.
