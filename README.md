# THE PATROL JETBOT v1.0

> **Hệ thống robot tuần tra an ninh trong nhà sử dụng Computer Vision và "Teach & Repeat" Navigation.**

## 1. Thành viên nhóm & Phân công nhiệm vụ

Theo kế hoạch tại file tài liệu [`THE PATROL JETBOT v1.docx`](THE%20PATROL%20JETBOT%20v1.docx):

- **Kiệt — Robotics:** Motor control, manual teleoperation, route replay controller, robot state machine (`Robot Control Module`).
- **Tuấn Anh — Computer Vision:** Visual matching, obstacle detection (Stop & Resume), person detection (`Vision Module`).
- **Minh — Backend:** Robot-server communication, REST API, Route & Event storage, Video streaming relay, Hardware Simulator (`Backend Service`).
- **Frontend — Web App:** Control panel, live video, route visualization, monitoring dashboard (`Web Application`).

---

## 2. Cấu trúc thư mục dự án

```text
the-patrol-jetbot/
├── THE PATROL JETBOT v1.docx    # Bản kế hoạch chi tiết đề tài v1.0
├── backend/                     # Backend Service (Phụ trách: Minh)
│   ├── app/                     # Mã nguồn chính FastAPI
│   │   ├── api/                 # REST API endpoints (teleop, routes, patrol, events, robot, video)
│   │   ├── db/                  # Database session & Base (SQLite + SQLAlchemy 2.0)
│   │   ├── models/              # ORM models (Route, Checkpoint, PatrolSession, SecurityEvent, RobotState)
│   │   ├── schemas/             # Pydantic v2 validation schemas
│   │   ├── services/            # Business logic & WebSocket connection manager
│   │   ├── ws/                  # WebSocket endpoints (/ws/robot, /ws/web, /ws/video)
│   │   ├── config.py            # Cấu hình hệ thống & biến môi trường
│   │   └── main.py              # FastAPI app entrypoint & middleware
│   ├── simulator/               # NVIDIA JetBot Simulator (phát triển độc lập)
│   │   └── jetbot_simulator.py  # Giả lập robot, video stream, Teach & Repeat, Obstacle, Person detection
│   ├── static/                  # Built-in Web Monitoring Dashboard (HTML5, Vanilla CSS, JS)
│   ├── scripts/                 # Runner scripts & seed data generator
│   │   ├── run_server.py        # Khởi chạy backend server
│   │   └── seed_data.py         # Khởi tạo tuyến tuần tra mẫu & sự kiện an ninh
│   ├── tests/                   # Bộ kiểm thử tự động 12 tests (pytest)
│   ├── requirements.txt         # Danh mục thư viện Python
│   └── README.md                # Tài liệu kỹ thuật chi tiết phân hệ Backend
└── .gitignore
```

---

## 3. Khởi chạy nhanh Backend (Minh)

Xem chi tiết tại [backend/README.md](backend/README.md).

```bash
# 1. Cài đặt thư viện
cd backend
pip install -r requirements.txt

# 2. Khởi tạo dữ liệu tuần tra mẫu
python scripts/seed_data.py

# 3. Chạy Backend server
python scripts/run_server.py
# -> Web Dashboard: http://localhost:8000/
# -> Swagger API:   http://localhost:8000/docs

# 4. Chạy Robot Simulator (Terminal riêng)
python simulator/jetbot_simulator.py

# 5. Chạy bộ kiểm thử tự động
pytest tests -v
```
