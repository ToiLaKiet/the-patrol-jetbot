import io
import time
import asyncio
from typing import Optional, AsyncGenerator
from PIL import Image, ImageDraw, ImageFont

class VideoStreamer:
    """
    Manages live camera frame buffer and MJPEG streaming generation.
    """
    def __init__(self):
        self._latest_frame: Optional[bytes] = None
        self._last_frame_time: float = 0.0
        self._frame_event = asyncio.Event()

    def update_frame(self, frame_bytes: bytes):
        """Update the latest camera frame received from robot or simulator"""
        self._latest_frame = frame_bytes
        self._last_frame_time = time.time()
        self._frame_event.set()
        self._frame_event.clear()

    def get_latest_frame(self) -> bytes:
        """Returns latest frame or fallback placeholder"""
        if self._latest_frame and (time.time() - self._last_frame_time < 3.0):
            return self._latest_frame
        return self._generate_placeholder_frame()

    def _generate_placeholder_frame(self, text: str = "JETBOT CAMERA STANDBY") -> bytes:
        """Generates a synthetic standby/test pattern frame"""
        width, height = 640, 480
        img = Image.new("RGB", (width, height), color=(24, 28, 36))
        draw = ImageDraw.Draw(img)

        # Draw tech border grid
        draw.rectangle([10, 10, width - 10, height - 10], outline=(45, 55, 72), width=2)
        draw.rectangle([15, 15, width - 15, height - 15], outline=(66, 153, 225), width=1)
        
        # Crosshair in center
        cx, cy = width // 2, height // 2
        draw.line([cx - 30, cy, cx + 30, cy], fill=(66, 153, 225), width=2)
        draw.line([cx, cy - 30, cx, cy + 30], fill=(66, 153, 225), width=2)
        draw.ellipse([cx - 15, cy - 15, cx + 15, cy + 15], outline=(66, 153, 225), width=2)

        # Status text
        current_ts = time.strftime("%Y-%m-%d %H:%M:%S")
        status_line = f"{text} | {current_ts}"
        draw.text((30, 30), "THE PATROL JETBOT v1.0", fill=(255, 255, 255))
        draw.text((30, 50), status_line, fill=(160, 174, 192))
        draw.text((30, height - 40), "STATUS: AWAITING STREAM OR SIMULATOR", fill=(229, 62, 62))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()

    async def generate_mjpeg_stream(self) -> AsyncGenerator[bytes, None]:
        """Async generator yielding MJPEG multipart stream packets"""
        while True:
            frame = self.get_latest_frame()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
            # Limit to ~25 fps max
            await asyncio.sleep(0.04)

video_streamer = VideoStreamer()
