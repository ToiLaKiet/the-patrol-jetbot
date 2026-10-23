# 🚀 TỔNG HỢP QUY TRÌNH CODE BACKEND — THE PATROL JETBOT v1.0
> **Tác giả:** Minh (Backend Engineer)  
> **Phong cách:** Ghi chép / Chat giải thích trực tiếp cho team & lưu tài liệu nội bộ.

---

## 🖐️ Chào anh em, Minh đây!

File này mình viết lại bằng ngôn ngữ chat quen thuộc để anh em trong team (**Kiệt - Robotics**, **Tuấn Anh - Vision**, và **bạn làm Frontend**) đọc là hiểu ngay Backend đã làm những gì, tại sao lại tổ chức code như thế, và sau này các ông ráp module của các ông vào Backend của tôi thế nào cho mượt nhất.

---

## 1. Xuất phát điểm: Đọc docx kế hoạch & bài toán đặt ra

Khi đọc file kế hoạch [`THE PATROL JETBOT v1.docx`](THE%20PATROL%20JETBOT%20v1.docx), mình thấy có 2 điểm mấu chốt:
1. **Phân công của mình (Minh):** Chịu trách nhiệm làm **Backend Service** (giao tiếp Robot - Server, REST API, lưu trữ hành trình route, lưu sự kiện an ninh và video).
2. **Chiến lược Phase 1 (Dòng 162):** *“Backend và Frontend có thể phát triển song song bằng dữ liệu giả lập ngay từ Phase 1.”*

👉 **Vấn đề thực tế là gì?**
- Con JetBot vật lý thì Kiệt đang setup motor/mạng.
- Model AI nhận diện người và vật cản thì Tuấn Anh đang train/test trên máy riêng.
- Frontend thì cần có API và WebSocket để làm giao diện điều khiển.

=> **Cách giải quyết:** Tôi quyết định **thiết kế Backend độc lập 100%**. Để làm được điều đó, tôi viết thêm **1 con JetBot Simulator (bộ giả lập robot ảo)** và **1 trang Web Dashboard test nhanh**. Khi chạy lên, hệ thống hoạt động như có một con robot thật đang chạy ngoài hành lang, phát video, nhận lệnh lái, tự bám tuyến và phát hiện người/vật cản.

---

## 2. Kiến trúc Backend mình chọn & Cấu trúc thư mục

Mình chọn **Python FastAPI + SQLAlchemy 2.0 + SQLite + WebSockets** vì:
- Hệ sinh thái JetBot/AI của Kiệt và Tuấn Anh đều viết bằng Python (dễ tích hợp về sau).
- FastAPI siêu nhanh, hỗ trợ async và WebSockets cực tốt cho robotics.
- Tự động sinh giao diện test API tại `/docs` (Swagger UI) mà không cần viết tài liệu chay.
- SQLite nhẹ nhàng, không bắt anh em phải cài Postgres/MySQL phức tạp.

### Cấu trúc folder chuẩn chỉ:
```text
backend/
├── app/
│   ├── api/          # Nơi chứa các router REST API (chia theo tính năng)
│   │   ├── teleop.py   # Lệnh lái xe tiến, lùi, trái, phải, dừng khẩn cấp
│   │   ├── routes.py   # Dạy đường (Teach mode), lưu checkpoint, xuất JSON
│   │   ├── patrol.py   # Tuần tra tự động (Repeat mode), cập nhật tiến độ %
│   │   ├── events.py   # Bắn sự kiện phát hiện người & vật cản, xem ảnh snapshot
│   │   ├── robot.py    # Báo cáo pin, Wi-Fi, trạng thái kết nối
│   │   └── video.py    # Stream video MJPEG trực tiếp
│   ├── db/           # Cấu hình kết nối cơ sở dữ liệu SQLite
│   ├── models/       # Bảng cơ sở dữ liệu (Route, Checkpoint, Event, Patrol, RobotState)
│   ├── schemas/      # Validate dữ liệu vào/ra bằng Pydantic v2
│   ├── services/     # Logic xử lý chính và bộ điều phối WebSocket (ConnectionManager)
│   ├── ws/           # 3 kênh WebSocket thời gian thực (/ws/robot, /ws/web, /ws/video)
│   └── main.py       # Điểm khởi động server
├── simulator/        # CON ROBOT ẢO của tôi để anh em test độc lập
│   └── jetbot_simulator.py
├── static/           # Web Dashboard điều khiển (HTML/CSS/JS Dark mode)
├── scripts/          # Script chạy server & tạo dữ liệu mẫu (seed_data.py)
└── tests/            # 12 bài test tự động (pytest)
```

---

## 3. Quy trình từng bước mình đã code (Step-by-Step)

### Bước 1: Thiết kế Cơ sở dữ liệu (Models)
Mình bám sát các tính năng F1 đến F5 trong kế hoạch:
- **`routes` & `checkpoints`:** Khi người dùng lái xe dạy đường (Teach mode), mỗi khi JetBot đi qua một điểm, hệ thống ghi lại tọa độ $(x, y, \theta)$, tốc độ, thời gian và **ảnh keyframe tham chiếu** từ camera để sau này so sánh thị giác.
- **`patrol_sessions`:** Mỗi lần bấm "Bắt đầu tuần tra" (Repeat mode), tạo ra 1 phiên tuần tra để theo dõi robot đang ở checkpoint số mấy, hoàn thành bao nhiêu % tuyến.
- **`security_events`:** Bất cứ khi nào Tuấn Anh phát hiện người (`PERSON_DETECTED`) hoặc gặp vật cản (`OBSTACLE_BLOCKED`), event này được lưu vào DB kèm tọa độ bounding box và ảnh chụp bằng chứng snapshot trong thư mục `data/uploads/`.
- **`robot_states` & `robot_logs`:** Quản lý pin, sóng Wi-Fi và nhật ký hoạt động.

### Bước 2: Xây dựng REST API chuẩn hóa
Mình chia API rất rõ ràng theo version `/api/v1`:
- Muốn lái xe? Gửi `POST /api/v1/teleop/command` với `{"command": "FORWARD", "linear_speed": 0.4}`.
- Muốn phanh gấp? Gửi `POST /api/v1/teleop/emergency-stop`.
- Muốn tạo tuyến, lấy tuyến, xóa tuyến? Dùng cụm `/api/v1/routes`.
- Muốn bắt đầu tuần tra, tạm dừng, chạy tiếp? Dùng cụm `/api/v1/patrol`.
- Muốn báo phát hiện người hoặc vật cản? Bắn vào `/api/v1/events`.

### Bước 3: Làm bộ điều phối thời gian thực (WebSocket Hub)
Robot di chuyển và cảnh báo an ninh thì không thể đợi Web polling (F5 liên tục) được, phải dùng **WebSocket**:
- Kênh `/ws/robot`: Con JetBot (hoặc Simulator) cắm vào đây. Robot gửi telemetry (pin, vị trí) lên, server bắn lệnh motor và lệnh tuần tra xuống.
- Kênh `/ws/web`: Trình duyệt web của người điều khiển cắm vào đây. Khi có sự kiện người lạ hay vật cản, server đẩy ngay lập tức (push notification) lên màn hình mà không có độ trễ.
- Kênh `/ws/video`: Nhận binary stream từ camera và phát lại qua endpoint `/api/v1/video/stream` theo chuẩn **MJPEG**, Frontend chỉ cần nhét thẻ `<img src="/api/v1/video/stream">` là xem được video mượt mà.

### Bước 4: Viết "Vũ khí bí mật" — JetBot Simulator
Đây là phần quan trọng nhất giúp team làm việc độc lập:
- File [`simulator/jetbot_simulator.py`](file:///c:/Users/Tran%20Hoai%20Minh/the-patrol-jetbot/backend/simulator/jetbot_simulator.py) đóng giả làm con JetBot thật.
- Nó tự vẽ khung hình camera hành lang giả lập kèm HUD hiển thị tọa độ X, Y, tốc độ, pin, thời gian thực và đẩy 12 khung hình/giây về server.
- Nó lắng nghe lệnh từ Web: bấm W xe chạy tiến, bấm S xe lùi.
- Khi bấm **Teach Mode**: nó tự sinh các checkpoint và ảnh keyframe mẫu.
- Khi bấm **Repeat Mode**: nó tự lái từ checkpoint 1 đến checkpoint cuối, tính toán góc lái và bắn tiến độ % về Web.
- Có sẵn 2 nút kích hoạt nhanh trên Web:
  - **Trigger Obstacle (Thử vật cản):** Xe đang đi bỗng dừng khựng lại, đổi trạng thái sang `BLOCKED`, báo động lên Web, sau 3.5 giây vật cản biến mất thì xe tự động đi tiếp! (Đúng theo yêu cầu F4 Stop/Resume).
  - **Trigger Person (Thử người lạ):** Xe phát hiện người, vẽ khung đỏ bounding box, gửi ảnh chụp snapshot và hú còi báo động trên Web! (Đúng theo F5).

### Bước 5: Làm Dashboard điều khiển trực quan (Static UI)
Để anh em không phải nhìn màn hình terminal đen trắng khô khan, tôi dựng luôn 1 giao diện Dark Mode xịn sò trong `backend/static/`:
- Bên trái: Màn hình camera trực tiếp + Cụm phím điều khiển D-Pad và thanh kéo tốc độ.
- Bên phải: Quản lý danh sách các hành trình tuần tra + Bảng tiến độ tuần tra lặp lại + Bảng nhật ký sự kiện kèm nút xem ảnh chụp phóng to.

### Bước 6: Viết bộ Test tự động (Pytest)
Viết code xong là phải test cho chắc chắn:
- Tôi tạo 12 bài test tự động trong `backend/tests/` bao phủ toàn bộ: tạo tuyến, ghi checkpoint, xóa tuyến, chạy tuần tra, tạm dừng, phát hiện người, vật cản, dừng khẩn cấp và kết nối WebSocket.
- Chạy lệnh `pytest tests -v` -> **12/12 bài test PASSED 100% trong 0.62 giây**, không có lỗi hay warning nào.

### Bước 7: Git Workflow & Đẩy code
- Tạo branch riêng đúng chuẩn: `backend_minh`.
- Tạo `.gitignore` để không bị rác file database `.db`, ảnh test và thư mục cache.
- Commit sạch sẽ và push lên GitHub:
  `git push -u origin backend_minh` thành công!

---

## 4. Hướng dẫn anh em trong team cách dùng & kết nối

### 🚀 Cách chạy thử toàn bộ hệ thống ngay bây giờ (mất đúng 30 giây):

1. **Mở Terminal 1 (Chạy Backend):**
   ```bash
   cd backend
   pip install -r requirements.txt
   python scripts/seed_data.py     # Tạo sẵn 1 tuyến tuần tra mẫu 6 checkpoint
   python scripts/run_server.py    # Bật server cổng 8000
   ```
   👉 Mở trình duyệt vào xem ngay:
   - Giao diện điều khiển Web: **`http://localhost:8000/`**
   - Tài liệu API tương tác: **`http://localhost:8000/docs`**

2. **Mở Terminal 2 (Chạy Robot Simulator):**
   ```bash
   python backend/simulator/jetbot_simulator.py
   ```
   👉 Nhìn sang Web: Đèn chuyển sang **Online (Xanh lá)**, video camera bắt đầu chạy trực tiếp, có thể bấm W/A/S/D để lái xe ảo, bấm "Tuần tra" để xe tự chạy, bấm thử "Trigger Person" và "Trigger Obstacle"!

3. **Chạy kiểm thử:**
   ```bash
   pytest backend/tests -v
   ```

---

## 5. Hướng dẫn ráp nối cho từng anh em

### 🤖 Cho Kiệt (Robotics — Motor & Teach & Repeat):
- Sau này trên con JetBot thật, Kiệt chỉ cần cho code Python trên robot mở WebSocket kết nối tới:  
  `ws://<IP_MAY_CHU>:8000/ws/robot`
- Khi người dùng ấn nút lái trên Web, server sẽ gửi message dạng:
  ```json
  {"action": "TELEOP", "command": "FORWARD", "linear_speed": 0.4, "angular_speed": 0.0}
  ```
  Kiệt chỉ cần đọc `command` và truyền xung PWM vào motor 2 bánh xe.
- Khi người dùng chọn tuyến và bấm "Start Patrol", server sẽ gửi:
  ```json
  {"action": "START_PATROL", "session_id": "...", "checkpoints": [{"sequence_idx": 0, "x": 0.0, "y": 0.0}, ...]}
  ```
  Kiệt lấy mảng `checkpoints` này cho bộ điều khiển Replay chạy lặp lại tuyến.

### 👁️ Cho Tuấn Anh (Computer Vision — Person & Obstacle):
- Khi camera phát hiện người: Tuấn Anh encode ảnh thành base64 hoặc gửi multipart form tới:  
  `POST /api/v1/events`  
  Payload:
  ```json
  {
    "event_type": "PERSON_DETECTED",
    "severity": "CRITICAL",
    "confidence": 0.95,
    "bounding_box": "[ymin, xmin, ymax, xmax]",
    "description": "Phát hiện 1 người ở hành lang",
    "image_base64": "<chuỗi ảnh JPEG>"
  }
  ```
  Hệ thống sẽ tự động lưu DB, lưu file ảnh và báo động đỏ ngay lập tức lên Web!
- Khi gặp vật cản phía trước: Gửi `event_type = "OBSTACLE_BLOCKED"`. Khi vật cản dời đi: Gửi `event_type = "OBSTACLE_CLEARED"`.

### 💻 Cho bạn làm Frontend (Web Application):
- Toàn bộ API đã có sẵn tại `http://localhost:8000/docs`, cứ nhìn vào schema Pydantic là biết request/response trả về trường gì.
- Live stream video: Chỉ cần nhét `<img src="http://localhost:8000/api/v1/video/stream" />`.
- Nhận thông báo realtime: Kết nối vào `ws://localhost:8000/ws/web`.

---

Anh em có thắc mắc chỗ nào cứ ping tôi (Minh) nhé, code backend đã sẵn sàng và test kỹ càng rồi! Chúc team mình làm đồ án suôn sẻ! 🚀
