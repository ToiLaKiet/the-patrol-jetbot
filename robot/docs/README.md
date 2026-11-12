# Cài đặt môi trường Jetson

The robot targets **Jetson Nano, JetPack 4.5 / L4T R32.5, CPython 3.6.9**.
The uv project requires Python `>=3.6.9,<3.7`; `.python-version` selects 3.6.
The lockfile targets Linux ARM64 (`aarch64`). It is not an environment for
running the original PlaceNav stack unchanged on a desktop.

JetBot is NVIDIA's **unmodified v0.4.3**, installed from its official Git tag.
There is no vendored package or import patch. Upstream imports its camera,
heartbeat, JPEG encoder and ObjectDetector when importing `jetbot`, so all of
those import dependencies, including TensorRT and PyTorch, must be present.

## Compatible versions

| Component | Version / source |
| --- | --- |
| Python | System CPython 3.6.9, `/usr/bin/python3` on this Jetson |
| JetBot | NVIDIA v0.4.3, Git commit pinned in `uv.lock` |
| CUDA / TensorRT | JetPack 4.5 system libraries; Python 3.6 TensorRT bindings from apt |
| PyTorch | NVIDIA `torch-1.10.0-cp36-cp36m-linux_aarch64.whl` for JetPack 4.x |
| NumPy | 1.19.5 |
| PyYAML / rospkg | 6.0.1 / 1.5.1 |
| Pygame | 2.6.1 |
| traitlets / ipywidgets | 4.3.3 / 7.7.2 |
| ZeroMQ / Pillow | 22.3.0 / 8.4.0 |
| OpenCV headless | 4.5.5.64 |
| PyGObject | 3.42.2, supports the system GLib 2.56 / GI 1.56 |
| setuptools | 59.6.0, provides upstream's `pkg_resources` |
| Python backports | dataclasses 0.8, importlib-metadata 4.8.3 |

The versions in TOML and the lockfile are resolved for Python 3.6. Changing
`requires-python` alone does not convert an existing Python 3.8 environment.
The code and tests also avoid newer Python APIs, and use the dataclasses and
importlib metadata backports.

## Prepare the Jetson

For clone, uv installation and first-run commands, start with the
[root guide](../../README.md#khởi-tạo-dự-án-trên-jetbot). Install uv with its
[standalone installer](https://docs.astral.sh/uv/getting-started/installation/)
if it is not already available.
Run these checks in the same host/container where the robot program will run:

```sh
cat /etc/nv_tegra_release
/usr/bin/python3 --version
uname -m
```

The intended combination is L4T R32.5, Python 3.6.9 and `aarch64`. An existing
Jupyter container and an SSH host can have different installed packages even
if both report `/usr/bin/python3`.

Native build tools, Python headers, GStreamer and TensorRT bindings are system
packages, installed outside uv:

```sh
sudo apt update
sudo apt install git curl ca-certificates cmake build-essential pkg-config python3-dev libgirepository1.0-dev libcairo2-dev libglib2.0-dev libffi-dev libfreetype6-dev libpng-dev libjpeg-dev zlib1g-dev libopenblas-dev liblapack-dev gfortran libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libportmidi-dev gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good python3-libnvinfer
```

Use the NVIDIA apt repositories matching the installed JetPack, not a newer
TensorRT/CUDA repository. CUDA/TensorRT development libraries and NVIDIA's
`nvjpegenc` GStreamer plugin must be available in this host/container too.
The JetBot installer builds its TensorRT plugin with CMake/Make. Pygame 2.6.1
has a CPython 3.6 ARM64 wheel containing SDL 2.28.4, including the classic
joystick interface used by the TGZ Controller. Prefer that wheel; a fallback
source build links the system SDL, whose version/features must be checked.

## Recreate the uv environment

From `robot/`, keep an existing working Python 3.6 environment. If replacing
an old or incompatible `.venv`, move it outside the repository first so it
can be restored. Run this only when replacing an existing environment:

```sh
mv .venv "$HOME/patrol-jetbot-venv-backup-$(date +%Y%m%d-%H%M%S)"
```

For a fresh clone or after moving the old environment:

```sh
uv venv --python /usr/bin/python3 --system-site-packages
OPENBLAS_CORETYPE=ARMV8 uv sync --locked --inexact
```

`--system-site-packages` exposes the matching Python 3.6 TensorRT bindings from
JetPack. `--inexact` preserves packages installed separately, such as NVIDIA's
PyTorch wheel. Neither option exposes packages located inside another Docker
container. uv still manages the project's ordinary Python dependencies.

NumPy 1.19.5's bundled OpenBLAS can select an incompatible CPU kernel on
Jetson Nano and terminate with SIGILL (illegal instruction). Export this
setting before installation and ad hoc Python commands in the current shell:

```sh
export OPENBLAS_CORETYPE=ARMV8
```

`src/main.py` and `check_jetbot_env.py` set this default on ARM64 before loading
native dependencies, preserving an explicit user setting. For `uv sync` and
other commands use the export above or prefix the command with
`OPENBLAS_CORETYPE=ARMV8`. See NumPy's issue:
https://github.com/numpy/numpy/issues/18131

Matplotlib is not a runtime dependency: no current robot code imports it.
This avoids building an unused plotting library during teleop setup.

If individual PyTorch imports pass but `import jetbot` fails with
`libgomp.so.1: cannot allocate memory in static TLS block`, preload the system
OpenMP runtime before starting uv/Python:

```sh
export LD_PRELOAD="/usr/lib/aarch64-linux-gnu/libgomp.so.1${LD_PRELOAD:+:$LD_PRELOAD}"
uv run --no-sync python check_jetbot_env.py
```

Keep this export in the shell used to launch teleop too. Setting `LD_PRELOAD`
inside an already-running Python process is too late for startup preloading.
The command preserves other existing preloads. This ARM64 workaround is
documented by NVIDIA:
https://docs.nvidia.com/metropolis/deepstream/7.1/text/DS_FAQ.html#how-to-fix-cannot-allocate-memory-in-static-tls-block-error

## Install NVIDIA PyTorch in uv

First test whether a compatible PyTorch installation is already visible:

```sh
uv run --no-sync python -c "import torch; print(torch.__version__); print(torch.version.cuda)"
```

If missing, download the NVIDIA wheel with its proper filename and install it
into the project environment:

```sh
curl -fL https://nvidia.box.com/shared/static/fjtbno0vpo676a25cgvuqc1wty0fkkg6.whl -o /tmp/torch-1.10.0-cp36-cp36m-linux_aarch64.whl
uv pip install /tmp/torch-1.10.0-cp36-cp36m-linux_aarch64.whl
uv run --no-sync python -c "import torch; print(torch.__version__); print('CUDA:', torch.cuda.is_available())"
```

This ARM64/CUDA wheel is installed separately, not replaced with a generic
PyPI `torch`. Keep using `uv sync --inexact`. NVIDIA lists this Python 3.6
wheel for JetPack 4.4 through 4.6:
https://forums.developer.nvidia.com/t/pytorch-for-jetson/72048/1276

TensorRT comes from `python3-libnvinfer` for this JetPack. Verify it with:

```sh
uv run --no-sync python -c "import tensorrt; print(tensorrt.__version__)"
```

## Verify the environment

Run all commands in this guide from `robot/`, including when reading this file
from `docs/`. The checker tests imports in child processes without constructing
`Robot` or sending motor commands:

```sh
uv run --no-sync python check_jetbot_env.py
```

Only after individual prerequisites pass does it test the full JetBot import.
Upstream import starts a JPEG encoder. This check does not open the camera or
verify motor behavior. Upstream can ignore native CMake/Make failures, so a
successful dependency sync is insufficient.

For teleop and teach commands, return to the [robot guide](../README.md).

## Limits


The OpenCV wheel provides `cv2` for imports and CPU image processing; it does
not provide the CSI camera's GStreamer backend. Camera use needs a matching
GStreamer-enabled OpenCV build and an updated dependency/source declaration.
Do not install multiple OpenCV packages into the same environment.

The original PlaceNav requirements use PyTorch 1.11 / CUDA 11.3 and a newer
Python environment. This legacy robot environment does not claim to run that
stack unchanged. Porting models/dependencies or running navigation in another
environment still requires separate validation. Model-conversion tools such
as TensorFlow/UFF/GraphSurgeon are not needed for teleop and are not installed.

Python 3.6 is an end-of-life runtime chosen for this legacy JetPack. Native
imports and motor behavior still require validation on the actual Jetson;
resolution and mock-based tests on a development machine do not prove those.
