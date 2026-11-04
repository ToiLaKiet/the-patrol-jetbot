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
   uv sync
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
   outside the uv lockfile. Running `uv sync` again can remove them, so reinstall
   them after syncing. Use `uv run --no-sync` to run code without syncing.
5. Verify GPU access:

   ```sh
   uv run --no-sync python -c "import torch; print(torch.__version__); print('CUDA:', torch.cuda.is_available())"
   ```

JetPack supplies CUDA and other system libraries; uv does not install or
replace them. Keep the Conda configuration until the uv environment has been
verified on the target device.
