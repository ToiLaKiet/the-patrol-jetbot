"""Export a PlaceNav image map from a completed JPEG/CSV Teach session."""

import argparse
import csv
import math
from pathlib import Path
import shutil

from PIL import Image


def create_topomap(session, destination, dt=2.0):
    if not math.isfinite(dt) or dt <= 0:
        raise ValueError("dt phải hữu hạn và lớn hơn 0.")

    session = Path(session).resolve()
    destination = Path(destination)
    selected = []
    previous_time = None
    selected_time = None
    last_image = None
    with (session / "samples.csv").open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if not {"image", "frame_read_s"}.issubset(reader.fieldnames or []):
            raise ValueError("samples.csv phải có cột image và frame_read_s.")
        for row in reader:
            timestamp = float(row["frame_read_s"])
            if (not math.isfinite(timestamp) or timestamp < 0
                    or (previous_time is not None and timestamp <= previous_time)):
                raise ValueError("frame_read_s phải hữu hạn, không âm và tăng dần.")
            previous_time = timestamp
            last_image = (session / row["image"]).resolve()
            last_image.relative_to(session)
            if selected_time is None or timestamp - selected_time >= dt:
                selected.append(last_image)
                selected_time = timestamp

    if not selected:
        raise ValueError("Phiên Teach không có mẫu ảnh.")
    if selected[-1] != last_image:
        selected.append(last_image)

    destination.mkdir(parents=True, exist_ok=False)
    try:
        for index, image in enumerate(selected):
            with Image.open(str(image)) as frame:
                if frame.format != "JPEG":
                    raise ValueError("Ảnh Teach phải là JPEG: " + str(image))
                frame.load()
            shutil.copyfile(str(image), str(destination / "{}.jpg".format(index)))
    except BaseException:
        shutil.rmtree(str(destination))
        raise
    return len(selected)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tạo topomap ảnh từ phiên Teach JPEG/CSV đã đóng.")
    parser.add_argument("session", type=Path, help="Thư mục run_... chứa samples.csv và images/.")
    parser.add_argument("destination", type=Path, help="Thư mục map mới; không ghi đè map đã có.")
    parser.add_argument("--dt", type=float, default=2.0,
                        help="Khoảng lấy mẫu tối thiểu, giây (mặc định: 2); luôn giữ ảnh đầu và cuối.")
    args = parser.parse_args(argv)
    try:
        count = create_topomap(args.session, args.destination, args.dt)
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    print("Đã xuất {} ảnh topomap vào {}".format(count, args.destination))


if __name__ == "__main__":
    main()
