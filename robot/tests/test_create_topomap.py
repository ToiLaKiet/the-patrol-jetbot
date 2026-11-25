import csv
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from teach.create_topomap import create_topomap


class CreateTopomapTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.session = self.root / "run"
        (self.session / "images").mkdir(parents=True)
        self.destination = self.root / "topomap"

    def record(self, timestamps):
        with (self.session / "samples.csv").open("w", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(["image", "frame_read_s", "command_s", "left", "right"])
            for index, timestamp in enumerate(timestamps):
                filename = "images/{:06d}.jpg".format(index)
                Image.new("RGB", (8, 8), (index * 20, 50, 100)).save(str(self.session / filename))
                writer.writerow([filename, timestamp, timestamp, 0, 0])

    def test_samples_by_elapsed_time_and_preserves_jpeg_bytes(self):
        self.record([0.1, 0.3, 4.9, 5.2, 5.4, 10.4, 10.6])
        self.assertEqual(create_topomap(self.session, self.destination), 3)
        self.assertEqual(sorted(p.name for p in self.destination.iterdir()),
                         ["0.jpg", "1.jpg", "2.jpg"])
        for node, source in enumerate([0, 3, 5]):
            self.assertEqual((self.destination / "{}.jpg".format(node)).read_bytes(),
                             (self.session / "images/{:06d}.jpg".format(source)).read_bytes())

    def test_short_session_and_custom_interval(self):
        self.record([0, 0.2, 2.1])
        self.assertEqual(create_topomap(self.session, self.destination), 1)
        self.assertEqual(create_topomap(self.session, self.root / "dense", dt=2), 2)

    def test_rejects_invalid_intervals(self):
        for dt in [0, -1, float("nan"), float("inf")]:
            with self.subTest(dt=dt), self.assertRaises(ValueError):
                create_topomap(self.session, self.destination, dt)
        self.assertFalse(self.destination.exists())

    def test_rejects_invalid_timestamps_and_empty_session(self):
        for timestamps in [[], [0, -1], [0, 0], [1, 0.5], [float("nan")], [float("inf")]]:
            with self.subTest(timestamps=timestamps):
                self.record(timestamps)
                with self.assertRaises(ValueError):
                    create_topomap(self.session, self.destination)
                self.assertFalse(self.destination.exists())

    def test_preserves_existing_map_and_teach_data(self):
        self.record([0, 5])
        self.destination.mkdir()
        marker = self.destination / "old.jpg"
        marker.write_bytes(b"existing map")
        with self.assertRaises(FileExistsError):
            create_topomap(self.session, self.destination)
        self.assertEqual(marker.read_bytes(), b"existing map")
        with self.assertRaises(FileExistsError):
            create_topomap(self.session, self.session / "images")
        self.assertEqual(len(list((self.session / "images").glob("*.jpg"))), 2)

    def test_bad_image_does_not_leave_partial_map(self):
        for corrupt in [False, True]:
            with self.subTest(corrupt=corrupt):
                self.record([0, 5])
                image = self.session / "images/000001.jpg"
                if corrupt:
                    image.write_bytes(b"invalid JPEG")
                else:
                    image.unlink()
                with self.assertRaises(OSError):
                    create_topomap(self.session, self.destination)
                self.assertFalse(self.destination.exists())

    def test_rejects_csv_path_outside_session(self):
        (self.session / "samples.csv").write_text("image,frame_read_s\n../outside.jpg,0\n")
        with self.assertRaises(ValueError):
            create_topomap(self.session, self.destination)
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
