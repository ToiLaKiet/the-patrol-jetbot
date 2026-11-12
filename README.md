# the-patrol-jetbot

JetBot tuần tra trong nhà theo hướng Teach & Repeat. Hiện đã có điều khiển
bằng tay cầm USB và ghi hành trình; phần tự hành chưa hoàn chỉnh.

## Khởi tạo dự án trên JetBot

Các bước dưới dành cho **Jetson Nano, JetPack 4.5 / L4T R32.5,
Python 3.6.9, ARM64**, đã có hệ điều hành và CUDA/TensorRT đúng JetPack.
Chạy trong terminal trên JetBot hoặc qua SSH (`ssh jetbot@<IP_JETBOT>`,
thay `<IP_JETBOT>` bằng địa chỉ máy). Dùng cùng một host/container cho mọi bước.

### 1. Kiểm tra máy và tải repo

```sh
cat /etc/nv_tegra_release
/usr/bin/python3 --version
uname -m

sudo apt update
sudo apt install git curl ca-certificates
cd ~
git clone https://github.com/ToiLaKiet/the-patrol-jetbot.git
cd the-patrol-jetbot/robot
```

Kết quả cần là L4T R32.5, Python 3.6.9 và `aarch64`.
Nếu đã clone repo, chỉ cần vào `~/the-patrol-jetbot/robot`, bỏ qua lệnh clone.
Các bước tiếp theo đều chạy từ thư mục `robot/` này.

### 2. Cài công cụ và thư viện hệ thống

Nếu chưa có `uv`, cài bằng [installer chính thức](https://docs.astral.sh/uv/getting-started/installation/):

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
. "$HOME/.local/bin/env"
uv --version
```

Cài các gói native để build JetBot, Pygame và dùng thư viện JetPack:

```sh
sudo apt install cmake build-essential pkg-config python3-dev \
  libgirepository1.0-dev libcairo2-dev libglib2.0-dev libffi-dev \
  libfreetype6-dev libpng-dev libjpeg-dev zlib1g-dev \
  libopenblas-dev liblapack-dev gfortran \
  libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libportmidi-dev \
  gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  python3-libnvinfer
```

### 3. Tạo môi trường Python

Repo đã có `pyproject.toml` và `uv.lock`, không cần chạy `uv init`.
Nếu đã có `.venv` chạy tốt thì giữ lại và bỏ qua lệnh tạo môi trường.
Nếu cần thay môi trường cũ, xem [cách giữ bản sao trước khi tạo lại](robot/docs/README.md#recreate-the-uv-environment).

```sh
export OPENBLAS_CORETYPE=ARMV8
uv venv --python /usr/bin/python3 --system-site-packages
uv sync --locked --inexact
```

`--system-site-packages` cho phép dùng TensorRT của JetPack;
`--inexact` giữ lại PyTorch được cài riêng. Không đổi Python hệ thống.

### 4. Kiểm tra và cài PyTorch NVIDIA nếu thiếu

```sh
uv run --no-sync python -c "import torch; print(torch.__version__); print(torch.version.cuda)"
```

Mục tiêu là Torch 1.10.0 / CUDA 10.2. Nếu chưa có Torch, cài wheel ARM64
của NVIDIA, không dùng bộ requirements gốc của PlaceNav:

```sh
curl -fL https://nvidia.box.com/shared/static/fjtbno0vpo676a25cgvuqc1wty0fkkg6.whl -o /tmp/torch-1.10.0-cp36-cp36m-linux_aarch64.whl
uv pip install /tmp/torch-1.10.0-cp36-cp36m-linux_aarch64.whl
```

Nếu gặp lỗi `libgomp.so.1: cannot allocate memory in static TLS block`,
đặt biến này trước khi chạy lại Python trong cùng terminal:

```sh
export LD_PRELOAD="/usr/lib/aarch64-linux-gnu/libgomp.so.1${LD_PRELOAD:+:$LD_PRELOAD}"
```

### 5. Kiểm tra rồi chạy main

```sh
uv run --no-sync python check_jetbot_env.py
uv run --no-sync python -c "import torch; print('CUDA:', torch.cuda.is_available())"
uv run --no-sync python src/main.py
```

Chỉ chạy main sau khi checker đạt và đã cắm tay cầm. Kê bánh để kiểm tra
chiều quay: đưa cần trái về giữa, thả L1 rồi giữ L1 để lái. Thả L1 để dừng;
Ctrl+C để thoát. Checker chỉ kiểm tra dependency, không thử motor/camera thật.

Để ghi ảnh, timestamp và lệnh motor, vẫn chạy từ `robot/`:

```sh
uv run --no-sync python src/main.py --teach-dir teach
```

Teach cần camera hoạt động; OpenCV headless hiện tại chưa cung cấp backend
GStreamer cho camera CSI. Xem [cài đặt và giới hạn](robot/docs/README.md).

Những lần sau, vào `~/the-patrol-jetbot/robot` rồi chạy lệnh main bằng `uv run
--no-sync`; không cần kích hoạt `.venv`. Đặt lại các biến môi trường cần thiết
nếu chưa lưu trong cấu hình shell.

[Sơ đồ và hướng dẫn các module](robot/README.md) ·
[Định dạng dữ liệu teach](robot/src/teach/README.md)
