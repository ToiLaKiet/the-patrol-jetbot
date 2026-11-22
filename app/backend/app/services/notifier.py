"""Anti-spam alert cooldown buffer and evidence file persistence helpers."""

import base64
import binascii
from pathlib import Path
import time
from typing import Dict, Optional, Set
import uuid

from app.config import settings

ALWAYS_NOTIFY_TYPES: Set[str] = {
    "OBSTACLE_CLEARED",
    "EMERGENCY_STOP",
    "ERROR_LOST",
}

ALLOWED_IMAGE_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


class AlertNotifier:
    """Rate-limits repetitive security alerts using a per-event-type cooldown window."""

    def __init__(self, cooldown_seconds: Optional[float] = None) -> None:
        self._cooldown_override = cooldown_seconds
        self._last_sent: Dict[str, float] = {}

    @property
    def cooldown_seconds(self) -> float:
        if self._cooldown_override is not None:
            return self._cooldown_override
        return settings.ALERT_COOLDOWN_SECONDS

    def reset(self) -> None:
        """Clear cooldown state (used between tests)."""
        self._last_sent.clear()

    def should_notify(
        self,
        event_type: str,
        *,
        force: bool = False,
        now: Optional[float] = None,
    ) -> bool:
        """Return True if an alert of event_type should be emitted/recorded now."""
        key = event_type.strip().upper()
        current = now if now is not None else time.monotonic()

        if force or key in ALWAYS_NOTIFY_TYPES:
            self._last_sent[key] = current
            return True

        previous = self._last_sent.get(key)
        if previous is not None and (current - previous) < self.cooldown_seconds:
            return False

        self._last_sent[key] = current
        return True


def _ensure_evidences_dir(storage_dir: str) -> Path:
    evidences_dir = Path(storage_dir) / "evidences"
    evidences_dir.mkdir(parents=True, exist_ok=True)
    return evidences_dir


def save_evidence_bytes(
    raw_bytes: bytes,
    ext: str,
    storage_dir: Optional[str] = None,
    prefix: str = "ev",
) -> str:
    """Persist raw evidence image bytes on disk and return storage-relative POSIX path."""
    if not raw_bytes:
        raise ValueError("Ảnh bằng chứng rỗng")

    normalized_ext = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
    if normalized_ext not in ALLOWED_IMAGE_EXTENSIONS:
        normalized_ext = ".jpg"

    root = storage_dir or settings.STORAGE_DIR
    evidences_dir = _ensure_evidences_dir(root)
    filename = f"{prefix}_{uuid.uuid4().hex[:12]}{normalized_ext}"
    (evidences_dir / filename).write_bytes(raw_bytes)
    return f"evidences/{filename}"


def save_evidence_base64(
    image_base64: str,
    storage_dir: Optional[str] = None,
    prefix: str = "ev",
) -> str:
    """Decode base64 image (raw or data URI) and save under storage/evidences/."""
    payload = image_base64.strip()
    ext = ".jpg"
    if payload.startswith("data:") and ";base64," in payload:
        header, payload = payload.split(";base64,", 1)
        mime_sub = header.split("/")[-1].lower()
        if mime_sub == "png":
            ext = ".png"
        elif mime_sub == "webp":
            ext = ".webp"
        elif mime_sub in {"jpg", "jpeg"}:
            ext = ".jpg"

    try:
        raw_bytes = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Chuỗi image_base64 không hợp lệ") from exc

    return save_evidence_bytes(raw_bytes, ext, storage_dir=storage_dir, prefix=prefix)


notifier = AlertNotifier()
