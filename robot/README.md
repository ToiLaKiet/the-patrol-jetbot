# Robot Python environment

The Python dependencies are managed with uv. The target Jetson Nano reports Jetson Linux R32.5 and Python 3.6.9.
The original Conda file specifies Python 3.8.5 and CUDA 11. This uv
configuration targets Python 3.8, but is not a complete replacement for the
Conda environment and has not been validated on the device. JetPack 4.5
provides CUDA 10.2, so CUDA 11 compatibility needs separate investigation.

1. Install JetPack, ROS, and uv on the Jetson. Check the JetPack and Python
   versions with `cat /etc/nv_tegra_release` and `python3 --version`.
2. From this directory, create an environment using a separately installed Python 3.8 interpreter, and make system ROS packages
   available to it:

   ```sh
   uv venv --python /path/to/python3.8 --system-site-packages
   uv sync --inexact
   ```

   Replace the path with the Python 3.8 interpreter. The system ROS packages
   were installed for Python 3.6 and may not work in this environment, even
   with `--system-site-packages`; verify compatibility separately.
3. Find a JetPack 4.5-compatible PyTorch wheel for Python 3.8, if available,
   then a compatible torchvision build. Follow NVIDIA's Jetson installation
   instructions: https://docs.nvidia.com/deeplearning/frameworks/install-pytorch-jetson-platform/
   PyTorch and torchvision are intentionally not installed automatically by
   this project: generic wheels may not support Jetson GPU acceleration. Check
   the installation instructions for the matching torchvision build, and avoid
   replacing the NVIDIA PyTorch wheel when installing it.
4. Install the remaining Python libraries without letting the package resolver
   replace NVIDIA's PyTorch wheel:

   ```sh
   uv pip install --no-deps efficientnet-pytorch warmup-scheduler
   ```

   These packages and the Jetson-specific PyTorch and torchvision builds are
   outside the uv lockfile. Use `uv sync --inexact` to preserve them when syncing.
   Use `uv run --no-sync` to run code without syncing.
5. Verify GPU access:

   ```sh
   uv run --no-sync python -c "import torch; print(torch.__version__); print('CUDA:', torch.cuda.is_available())"
   ```

JetPack supplies CUDA and other system libraries; uv does not install or
replace them. Keep the Conda configuration until the uv environment has been
verified on the target device.

## JetBot hardware library

The project installs NVIDIA's official `jetbot` v0.4.3 from Git on Linux
ARM64 (`aarch64`), including its Adafruit motor/display dependencies.
`uv.lock` pins the Git commit. Other platforms skip the hardware package so
development and mock-based tests can run there.

The v0.4.3 source was audited beyond its incomplete `setup.py`. The project
also declares the runtime dependencies used by the following components:

| JetBot component | Python dependency managed by uv |
| --- | --- |
| Motor and camera configuration | `traitlets` |
| Heartbeat, imported even for motor-only use | `ipywidgets` and its widget/IPython dependencies |
| Camera/image functions | `numpy`, `opencv-python-headless` |
| JPEG encoder | `PyGObject==3.42.2` (`gi`), transitively `pycairo` and `cffi` |
| ZMQ camera | `pyzmq>=22,<26` |
| OLED stats images | `pillow` |
| Service helpers using `pkg_resources` | `setuptools<81` |
| I2C motor/display drivers | `Adafruit-MotorHAT`, `Adafruit-SSD1306`, transitively `Adafruit-GPIO`, `Adafruit-PureIO` |

PyGObject is pinned to a release supporting GLib 2.56 and GI 1.56 from Ubuntu
18.04. ZeroMQ is constrained to a series providing Python 3.8/ARM64 wheels for
the older glibc on this Jetson.

Install native build prerequisites once, before syncing on JetPack 4.5:

```sh
sudo apt update
sudo apt install git cmake build-essential pkg-config libgirepository1.0-dev libcairo2-dev libglib2.0-dev libffi-dev gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good
```

These are native system libraries/tools, not Python packages. C extension
builds also need headers matching the environment's Python 3.8; Python 3.6
development headers do not substitute for them. NVIDIA's `nvjpegenc` plugin,
CUDA and TensorRT libraries must come from the compatible JetPack installation
in the same host/container where uv runs.

After pulling the updated repository, run from `robot/` on the Jetson:

```sh
uv sync --locked --inexact
uv run --no-sync python check_jetbot_env.py
```

The checker reports every failing prerequisite in one run, including native
imports, the NVIDIA JPEG plugin, and JetBot's compiled TensorRT plugin. Only
when all prerequisites pass does it try the full JetBot import, in a child
process. Upstream `import jetbot` creates a JPEG encoder/GStreamer pipeline;
the checker never instantiates `Robot` or sends motor commands.
It exits nonzero on failures. Only after it succeeds, test teleop with the
wheels raised:

```sh
uv run --no-sync python src/main.py
```

JetBot's upstream installer invokes CMake and Make to build a CUDA/TensorRT
plugin, even when only using motors.

CUDA and TensorRT development libraries must be available in the environment
where uv runs. JetBot also imports OpenCV, TensorRT and PyTorch through its
package initialization; those must work with the project's Python 3.8.
OpenCV is installed through uv as `opencv-python-headless` 4.11.0.86, providing
`cv2` without GUI dependencies for SSH teleop. This version has an ARM64 wheel
compatible with the older glibc used by JetPack 4.5. Verify the import with:

```sh
uv run --no-sync python -c "import cv2; print(cv2.__version__)"
```

The PyPI OpenCV wheel is CPU-only and does not provide the Jetson camera's
GStreamer backend. Before using the CSI camera, replace it with a Python
3.8-compatible OpenCV build with GStreamer and update the uv dependency/source
accordingly. Do not install multiple OpenCV distributions exposing `cv2` in
the same environment.

TensorRT and the Jetson-specific PyTorch build are not installed automatically
from PyPI. Their wheels must match Python 3.8, ARM64, CUDA 10.2 and the installed
JetPack/TensorRT version. A generic current `tensorrt` or `torch` dependency
does not select that combination. No compatible wheel URLs have been verified
for this device, so the TOML deliberately does not claim to provision them.
For the older TensorRT 7.1.3 Jetson stack, NVIDIA supplied Python 3.6 bindings;
other Python versions require a compatible custom build:
https://forums.developer.nvidia.com/t/using-tensorrt-7-1-3-jetpack4-4-with-python3-7-instead-of-3-6-how/179717/5

Installing these wheels after obtaining compatible builds uses the project
environment too:

```sh
uv pip install /path/to/compatible-tensorrt-wheel.whl /path/to/compatible-torch-wheel.whl
```

These paths are placeholders, not downloadable artifacts. Preserve externally
installed builds with `uv sync --inexact`. Once verified wheel locations are
available, they can be recorded as explicit uv sources. Until then, the checker
may still report TensorRT/PyTorch as blockers; syncing alone is not a complete
working JetBot environment. Check just these imports with:

```sh
uv run --no-sync python -c "import cv2, tensorrt, torch; print('Native imports OK')"
```

An existing JetBot installation in a Python 3.6 notebook, including one in a
Docker container, is separate from this Python 3.8 environment. Making system
packages visible does not make Python 3.6 binary extensions compatible with
Python 3.8, or expose libraries from a different container.

Static dependency metadata in `pyproject.toml` mirrors the v0.4.3 `setup.py`
so generating the lockfile does not run the native build on a development
machine. It does not skip the build during installation on the Jetson.
Upstream does not reliably propagate CMake/Make failures, so successful
`uv sync` alone is not proof that JetBot imports or its native plugin works.
Python 3.8/JetPack compatibility still needs validation on the device.

TensorFlow, UFF, GraphSurgeon, protobuf and the TensorFlow Object Detection API
occur inside model-conversion helpers, not the runtime import path or teleop.
They are outside this runtime setup. GPIO/SPI backends for Raspberry Pi,
BeagleBone and FT232H are also outside the Jetson I2C motor path.

Run the dependency-checker and teleop tests without hardware from `robot/`:

```sh
PYTHONPATH=src uv run --no-sync python -m unittest discover -s tests -v
```

## USB gamepad

Pygame is a project dependency; install it in `robot/.venv` using uv, rather
than installing it into the system Python with pip. Run these commands from
`robot/` on the Jetson after creating the Python 3.8 environment above:

```sh
uv sync --inexact
uv run --no-sync python -c "import sys, pygame; print(sys.executable); print(pygame.version.ver)"
```

`--inexact` preserves separately installed Jetson packages such as PyTorch.
Check the connected controller and its axis/button mapping without running
the motors:

```sh
uv run --no-sync python check_controller.py
```

The script enables SDL's classic Linux joystick interface, required to detect
the TGZ Controller on this Jetson, and supports running over SSH. Push the left
stick up and right, then press and release L1. Record the printed axis indices,
signs, and button index; do not assume the mapping matches `jstest`.
Press Ctrl+C to exit. Disconnecting the controller ends the check with an error.

Linux utilities and native build dependencies are system packages, outside
uv. To test the controller without Python:

```sh
sudo apt update
sudo apt install joystick
jstest /dev/input/js0
```

If Pygame falls back to a source build and reports missing SDL or FreeType,
install its native build dependencies on the Jetson, then retry uv sync:

```sh
sudo apt install build-essential pkg-config python3.8-dev libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libfreetype6-dev libportmidi-dev
uv sync --inexact
```

The Python development headers must match the Python 3.8 interpreter used by
the environment; if `python3.8-dev` is unavailable, obtain matching headers
from the source used to install that interpreter. The system Python 3.6 on
JetPack 4.5 does not satisfy this project's Python requirement.
