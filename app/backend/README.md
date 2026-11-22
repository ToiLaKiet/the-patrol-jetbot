# The Patrol JetBot — Backend Service (v2.0)

Backend middleware viết bằng **FastAPI + SQLAlchemy 2.0 + SQLite + WebSocket**, đóng vai trò cầu nối thời gian thực giữa **JetBot (`/ws/robot`)** và **Web Dashboard (`/ws/web`)**, đồng thời lưu trữ tuyến tuần tra, lượt chạy KPI, telemetry và bằng chứng sự kiện an ninh.

---

## 1. Cấu trúc thư mục

```text
app/backend/
├── app/
│   ├── config.py                # Cấu hình Pydantic Settings ([FRONTEND_CORS], [KIET_ROBOT_NET])
│   ├── main.py                  # Khởi tạo FastAPI, CORS, /storage, background heartbeat monitor
│   ├── db/
│   │   ├── base.py              # DeclarativeBase & utc_now()
│   │   └── session.py           # Kết nối SQLite, get_db(), init_db()
│   ├── models/                  # 5 bảng SQLite: routes, checkpoints, patrol_runs, run_telemetry, events
│   │   ├── route.py
│   │   ├── patrol.py
│   │   └── event.py             # [TUANANH_EVENT_PAYLOAD]
│   ├── schemas/                 # Pydantic v2 request/response schemas
│   │   ├── route_schema.py
│   │   ├── patrol_schema.py
│   │   ├── event_schema.py
│   │   └── ws_schema.py         # [FRONTEND_WS_TOPICS]
│   ├── core/
│   │   └── fsm.py               # Máy trạng thái PatrolFSM & phát hiện lạc tuyến [TUANANH_MATCH_SCORE]
│   ├── ws/
│   │   ├── connection_manager.py# Quản lý kết nối & dead-man repeater 5Hz [KIET_DEADMAN_WATCHDOG]
│   │   └── router.py            # /ws/robot & /ws/web [KIET_BATTERY_INA219], [TUANANH_EVENT_PAYLOAD]
│   ├── api/v1/
│   │   ├── routes.py            # CRUD tuyến & upload gói ZIP [TUANANH_ROUTE_PACKAGE]
│   │   ├── patrols.py           # Start/finish/stop lượt tuần tra & KPI summary
│   │   ├── events.py            # Lọc sự kiện, lưu ảnh base64/multipart
│   │   └── telemetry.py         # Snapshot trạng thái robot, log telemetry & xuất CSV
│   └── services/
│       ├── route_service.py     # Giải nén ZIP an toàn (chống Zip-Slip), parse route.json / samples.csv
│       └── notifier.py          # Bộ đệm chống spam cảnh báo & lưu ảnh evidence
├── storage/                     # Lưu routes/ và evidences/
├── mock/
│   ├── mock_robot.py            # Giả lập JetBot 100% qua /ws/robot
│   └── sample_route/            # Tuyến mẫu (route.json + keyframes/)
├── tests/                       # Bộ kiểm thử tự động pytest
├── main.py                      # Entrypoint uvicorn
├── .env.example
└── requirements.txt
```

---

## 2. Cài đặt & Chạy nhanh

Mọi lệnh bên dưới chạy tại thư mục `app/backend/`:

```bash
cd app/backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Sau khi server chạy tại `http://localhost:8000`:
- **Swagger UI:** `http://localhost:8000/docs`
- **Health Check:** `http://localhost:8000/health`
- **WebSocket Robot:** `ws://localhost:8000/ws/robot`
- **WebSocket Web UI:** `ws://localhost:8000/ws/web`

### Chạy giả lập JetBot (không cần phần cứng thật)
Mở terminal thứ hai tại `app/backend/`:

```bash
python mock/mock_robot.py
# Hoặc chạy kịch bản giả lập cụ thể:
python mock/mock_robot.py --scenario obstacle --interval 0.5 --max-ticks 10
```

Tạo file `.zip` tuyến mẫu để test upload tại Swagger `/api/v1/routes/upload`:
```bash
python mock/sample_route/build_sample_zip.py
```

---

## 3. Danh sách API chính (`/api/v1`)

| Nhóm | Endpoint | Chức năng |
| :--- | :--- | :--- |
| **Routes** | `GET /api/v1/routes/` | Danh sách tuyến tuần tra |
| | `POST /api/v1/routes/` | Tạo tuyến mới bằng JSON |
| | `POST /api/v1/routes/upload` | Upload gói `.zip` (`route.json` + `keyframes/` hoặc `samples.csv` từ `TeachRecorder`) |
| | `GET /api/v1/routes/{route_id}` | Chi tiết tuyến kèm danh sách checkpoints |
| | `GET /api/v1/routes/{route_id}/checkpoints` | Danh sách checkpoints theo thứ tự |
| | `DELETE /api/v1/routes/{route_id}` | Xóa tuyến và thư mục lưu trữ |
| **Patrols** | `GET /api/v1/patrols/` | Danh sách lượt tuần tra (lọc theo `route_id`, `result`) |
| | `POST /api/v1/patrols/start` | Bắt đầu lượt tuần tra & gửi lệnh xuống JetBot nếu đang online |
| | `POST /api/v1/patrols/{run_id}/finish` | Chốt kết quả lượt chạy (`COMPLETED` / `ABORTED` / `LOST`) |
| | `POST /api/v1/patrols/{run_id}/stop` | Dừng khẩn lượt tuần tra và báo xuống JetBot |
| | `GET /api/v1/patrols/kpi/summary` | Thống kê tỷ lệ hoàn thành, stop/resume vật cản, số lần phát hiện người |
| **Events** | `GET /api/v1/events/` | Tra cứu sự kiện (lọc `event_type`, `run_id`, `start_time`, `end_time`, phân trang) |
| | `POST /api/v1/events/` | Ghi nhận sự kiện qua JSON (hỗ trợ `image_base64`) |
| | `POST /api/v1/events/upload` | Ghi nhận sự kiện kèm file ảnh multipart |
| | `DELETE /api/v1/events/{event_id}` | Xóa sự kiện và ảnh bằng chứng |
| **Telemetry** | `GET /api/v1/telemetry/robot/status` | Lấy snapshot trạng thái hiện tại của robot (`PatrolFSM`) |
| | `GET /api/v1/telemetry/{run_id}` | Log telemetry theo từng lượt chạy |
| | `GET /api/v1/telemetry/{run_id}/export.csv` | Xuất báo cáo telemetry dạng CSV |

---

## 4. Kiểm thử tự động

Tại `app/backend/`:
```bash
python -m pytest tests -v
```

---

## 5. Tra cứu tích hợp phần cứng & CV (`PENDING_INTEGRATION`)

Tìm toàn bộ vị trí cần khớp nối trong code bằng:
```bash
grep -rn "PENDING_INTEGRATION" app/
```

| Mã Thẻ (`Tag ID`) | Người phối hợp | Vị trí chính trong code |
| :--- | :--- | :--- |
| `FRONTEND_CORS` | Frontend | `app/config.py` |
| `KIET_ROBOT_NET` | Kiệt (Phần cứng) | `app/config.py` |
| `KIET_DEADMAN_WATCHDOG` | Kiệt (Điều khiển) | `app/ws/connection_manager.py` |
| `KIET_BATTERY_INA219` | Kiệt (Cảm biến) | `app/ws/router.py` |
| `TUANANH_ROUTE_PACKAGE` | Tuấn Anh (CV/T&R) | `app/api/v1/routes.py`, `app/services/route_service.py` |
| `TUANANH_EVENT_PAYLOAD` | Tuấn Anh (YOLO/CV) | `app/models/event.py`, `app/ws/router.py`, `app/api/v1/events.py` |
| `TUANANH_MATCH_SCORE` | Tuấn Anh (Visual Match) | `app/core/fsm.py`, `app/ws/router.py` |
| `FRONTEND_WS_TOPICS` | Frontend | `app/schemas/ws_schema.py`, `app/ws/connection_manager.py`, `app/ws/router.py` |
