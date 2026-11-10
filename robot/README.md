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
`traitlets`, used by JetBot but missing from its upstream dependency metadata,
is also a project dependency. `uv.lock` pins the Git commit. Other platforms
skip the hardware package so development and mock-based tests can run there.

After pulling the updated repository, run from `robot/` on the Jetson:

```sh
uv sync --locked --inexact
uv run --no-sync python -c "import jetbot; print(jetbot.__file__)"
```

The import check does not instantiate the robot or send motor commands.
Only after it succeeds, test teleop with the wheels raised:

```sh
uv run --no-sync python src/main.py
```

JetBot's upstream installer invokes CMake and Make to build a CUDA/TensorRT
plugin, even when only using motors. If the build tools are missing, install
the native tools with apt, then retry syncing:

```sh
sudo apt update
sudo apt install git cmake build-essential
```

CUDA and TensorRT development libraries must be available in the environment
where uv runs. JetBot also imports OpenCV, TensorRT and PyTorch through its
package initialization; those must work with the project's Python 3.8.
These JetPack-specific libraries are not installed automatically from PyPI.
Check the first native Python imports with:

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
