"""Report JetBot runtime dependencies without constructing Robot or commanding motors."""

import subprocess
import sys


CHECKS = (
    ("JetBot package", "from importlib_metadata import version; print(version('jetbot'))"),
    ("NumPy", "import numpy"),
    ("OpenCV", "import cv2"),
    ("Pygame / SDL", "import pygame; print(pygame.get_sdl_version())"),
    ("traitlets", "import traitlets"),
    ("ipywidgets", "import ipywidgets.widgets"),
    ("ZeroMQ", "import zmq"),
    ("Pillow", "from PIL import Image, ImageDraw, ImageFont"),
    ("pkg_resources", "import pkg_resources"),
    ("I2C driver", "import Adafruit_GPIO.I2C, Adafruit_PureIO.smbus"),
    ("MotorHAT", "from Adafruit_MotorHAT import Adafruit_MotorHAT"),
    ("OLED driver", "import Adafruit_SSD1306"),
    ("GStreamer / NVIDIA JPEG", "import gi; gi.require_version('Gst', '1.0'); "
     "from gi.repository import GObject, Gst; Gst.init(None); "
     "assert Gst.ElementFactory.find('nvjpegenc') is not None, 'Missing nvjpegenc plugin'"),
    ("TensorRT", "import tensorrt"),
    ("PyTorch", "import torch"),
    ("JetBot TensorRT plugin", "import ctypes; from importlib_metadata import distribution; "
     "ctypes.CDLL(str(distribution('jetbot').locate_file('jetbot/ssd_tensorrt/libssd_tensorrt.so')))"),
)


def check(name, code):
    try:
        result = subprocess.run(
            [sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        print(f"FAIL {name}: timeout sau 30 giây", flush=True)
        return False
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        print(f"FAIL {name}:\n{detail}", flush=True)
        return False
    print(f"OK   {name}", flush=True)
    return True


def main():
    print("Python:", sys.executable, flush=True)
    failed = []
    for name, code in CHECKS:
        if not check(name, code):
            failed.append(name)
    if not failed:
        # Upstream import creates a JPEG encoder; run it in a child process after prerequisites pass.
        if not check("Full JetBot import", "import jetbot; print(jetbot.__file__)"):
            failed.append("Full JetBot import")
    if failed:
        print("\nChưa đạt:", ", ".join(failed), flush=True)
        return 1
    print("\nDependency checks OK. Chưa kiểm tra camera, I2C hoặc motor thực tế.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
