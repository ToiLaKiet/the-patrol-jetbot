"""Utility script to pack mock/sample_route into sample_route.zip for Swagger upload tests."""

from pathlib import Path
import zipfile


def build_sample_zip(output_path: Path | None = None) -> Path:
    sample_dir = Path(__file__).resolve().parent
    target = output_path or (sample_dir.parent / "sample_route.zip")

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(sample_dir / "route.json", arcname="route.json")
        for img_path in sorted((sample_dir / "keyframes").glob("*.jpg")):
            zf.write(img_path, arcname=f"keyframes/{img_path.name}")

    return target


if __name__ == "__main__":
    zip_file = build_sample_zip()
    print(f"Created sample route package at: {zip_file}")
