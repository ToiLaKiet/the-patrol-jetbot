"""Route package unpacking, validation, and checkpoint ingestion service."""

import csv
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
from typing import Dict, List, Optional, Tuple
import uuid
import zipfile

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.models.route import Checkpoint, Route

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def safe_extract_zip(zip_path: str, extract_dir: str) -> None:
    """Extract a ZIP archive after verifying every entry against path traversal (Zip-Slip)."""
    base = Path(extract_dir).resolve()
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                member_name = info.filename
                if not member_name:
                    continue
                posix_parts = PurePosixPath(member_name).parts
                win_parts = PureWindowsPath(member_name).parts
                if (
                    member_name.startswith(("/", "\\"))
                    or ".." in posix_parts
                    or ".." in win_parts
                    or (win_parts and ":" in win_parts[0])
                ):
                    raise ValueError(f"Đường dẫn không an toàn trong file zip: {member_name}")

                target_path = (base / member_name).resolve()
                try:
                    target_path.relative_to(base)
                except ValueError as exc:
                    raise ValueError(
                        f"Đường dẫn thoát khỏi thư mục giải nén: {member_name}"
                    ) from exc

            zf.extractall(base)
    except zipfile.BadZipFile as exc:
        raise ValueError("File zip bị hỏng hoặc không đúng định dạng") from exc


def _to_storage_rel_path(
    candidate: Optional[str],
    base_dir: Path,
    route_dir: Path,
    route_id: str,
) -> Optional[str]:
    if not candidate:
        return None
    cleaned = candidate.replace("\\", "/").lstrip("./")
    resolved = (base_dir / cleaned).resolve()
    try:
        rel_inside_route = resolved.relative_to(route_dir.resolve()).as_posix()
        return f"routes/{route_id}/{rel_inside_route}"
    except ValueError:
        return f"routes/{route_id}/{cleaned}"


def _find_first_file(root: Path, filename: str) -> Optional[Path]:
    matches = [
        p
        for p in sorted(root.rglob(filename))
        if "__MACOSX" not in p.parts
    ]
    return matches[0] if matches else None


def parse_extracted_route(route_dir: str, route_id: str) -> Tuple[List[Dict], float]:
    """Parse checkpoints and total duration from an unpacked route package."""
    # [PENDING_INTEGRATION: TUANANH_ROUTE_PACKAGE]
    # Hiện tại: Ưu tiên đọc `route.json` + thư mục `keyframes/`; hỗ trợ fallback `samples.csv` (TeachRecorder) hoặc thư mục ảnh.
    # Cần khớp: Cấu trúc JSON/CSV chính thức, tên thư mục ảnh và định dạng keyframe giữa Tuấn Anh và Kiệt.
    # Hành động: Cập nhật hàm parse này khi chốt schema route.json cuối cùng.
    root = Path(route_dir)
    checkpoints: List[Dict] = []

    route_json_path = _find_first_file(root, "route.json")
    if route_json_path is not None:
        data = json.loads(route_json_path.read_text(encoding="utf-8"))
        raw_items = data.get("checkpoints", [])
        for idx, item in enumerate(raw_items):
            raw_kf = (
                item.get("keyframe_path")
                or item.get("keyframe")
                or item.get("image")
            )
            checkpoints.append(
                {
                    "seq": int(item.get("seq", idx)),
                    "keyframe_path": _to_storage_rel_path(
                        raw_kf, route_json_path.parent, root, route_id
                    ),
                    "timestamp_offset": float(item.get("timestamp_offset", 0.0)),
                    "command_summary": item.get("command_summary") or item.get("command"),
                }
            )
        total_duration = float(
            data.get("total_duration_s")
            or max((cp["timestamp_offset"] for cp in checkpoints), default=0.0)
        )
        return checkpoints, total_duration

    samples_csv_path = _find_first_file(root, "samples.csv")
    if samples_csv_path is not None:
        with samples_csv_path.open("r", encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for idx, row in enumerate(reader):
                ts_offset = float(row.get("frame_read_s") or 0.0)
                left = float(row.get("left") or 0.0)
                right = float(row.get("right") or 0.0)
                checkpoints.append(
                    {
                        "seq": idx,
                        "keyframe_path": _to_storage_rel_path(
                            row.get("image"), samples_csv_path.parent, root, route_id
                        ),
                        "timestamp_offset": ts_offset,
                        "command_summary": f"left={left:.3f}, right={right:.3f}",
                    }
                )
        total_duration = max((cp["timestamp_offset"] for cp in checkpoints), default=0.0)
        return checkpoints, total_duration

    image_files = [
        p
        for p in sorted(root.rglob("*"))
        if p.is_file()
        and p.suffix.lower() in IMAGE_SUFFIXES
        and "__MACOSX" not in p.parts
    ]
    for idx, img_path in enumerate(image_files):
        rel = img_path.relative_to(root).as_posix()
        checkpoints.append(
            {
                "seq": idx,
                "keyframe_path": f"routes/{route_id}/{rel}",
                "timestamp_offset": float(idx),
                "command_summary": None,
            }
        )
    total_duration = float(len(checkpoints) - 1) if len(checkpoints) > 1 else 0.0
    return checkpoints, total_duration


def create_route_from_zip(
    db: Session,
    name: str,
    upload_file: UploadFile,
    description: Optional[str] = None,
) -> Route:
    """Validate, unpack, parse, and persist a zipped Teach & Repeat route package."""
    filename = upload_file.filename or ""
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận file .zip")

    route_id = str(uuid.uuid4())
    route_dir = Path(settings.STORAGE_DIR) / "routes" / route_id
    route_dir.mkdir(parents=True, exist_ok=True)
    zip_path = route_dir / "package.zip"

    try:
        with zip_path.open("wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)

        safe_extract_zip(str(zip_path), str(route_dir))
        parsed_checkpoints, total_duration_s = parse_extracted_route(
            str(route_dir), route_id
        )
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        shutil.rmtree(route_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Lỗi xử lý gói tuyến: {exc}") from exc

    new_route = Route(
        id=route_id,
        name=name,
        description=description,
        checkpoint_count=len(parsed_checkpoints),
        total_duration_s=total_duration_s,
        status="ACTIVE",
        package_path=f"routes/{route_id}",
    )
    db.add(new_route)
    db.flush()

    for cp in parsed_checkpoints:
        db.add(
            Checkpoint(
                route_id=route_id,
                seq=cp["seq"],
                keyframe_path=cp["keyframe_path"],
                timestamp_offset=cp["timestamp_offset"],
                command_summary=cp["command_summary"],
            )
        )

    db.commit()
    db.refresh(new_route)
    return new_route


def delete_route_storage(package_path: Optional[str]) -> None:
    """Remove stored route directory on disk if it lives inside STORAGE_DIR."""
    if not package_path:
        return
    storage_root = Path(settings.STORAGE_DIR).resolve()
    candidate = Path(package_path)
    target = (
        candidate.resolve()
        if candidate.is_absolute()
        else (storage_root / package_path).resolve()
    )
    try:
        target.relative_to(storage_root)
    except ValueError:
        return
    if target.exists() and target != storage_root:
        shutil.rmtree(target, ignore_errors=True)
