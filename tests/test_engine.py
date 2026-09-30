import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from auto_censor_studio.core import (
    Region,
    render,
    minimum_block,
    expanded_box,
    atomic_export,
    load_image,
    fingerprint,
    save_project,
    read_project,
    region_mask,
    region_covers,
)


from auto_censor_studio.services.detection import decode


class EngineTests(unittest.TestCase):
    def setUp(self):
        y, x = np.mgrid[:99, :131]
        self.pixels = np.stack(((x * 17) % 256, (y * 13) % 256, (x * 3 + y * 5) % 256), axis=2).astype("uint8")
        self.image = Image.fromarray(self.pixels)

    def test_guideline_rounds_up_and_uses_whole_image(self):
        for size, expected in [((200, 300), 4), ((400, 200), 4), ((2001, 1000), 21)]:
            self.assertEqual(minimum_block(size), expected)

    def test_exact_square_blocks_and_untouched_pixels(self):
        r = Region(16, 24, 64, 48)
        out = np.asarray(render(self.image, [r], 8, 0))
        self.assertTrue(np.array_equal(out[:24], self.pixels[:24]))
        self.assertTrue(np.array_equal(out[:, :16], self.pixels[:, :16]))
        self.assertTrue(np.array_equal(out[72:], self.pixels[72:]))
        for y in range(24, 72, 8):
            for x in range(16, 80, 8):
                block = out[y : y + 8, x : x + 8]
                self.assertTrue(np.all(block == block[0, 0]))
        self.assertFalse(np.array_equal(out[24:72, 16:80], self.pixels[24:72, 16:80]))

    def test_overlap_is_order_independent_and_does_not_accumulate(self):
        a, b = Region(5, 5, 55, 51), Region(20, 20, 75, 60)
        left = render(self.image, [a, b], 8, 15)
        right = render(self.image, [b, a, a], 8, 15)
        self.assertEqual(left.tobytes(), right.tobytes())
        self.assertEqual(self.image.tobytes(), self.pixels.tobytes())

    def test_margin_clips_at_all_image_edges(self):
        r = Region(0, 0, 131, 99)
        self.assertEqual(expanded_box(r, self.image.size, 100), (0, 0, 131, 99))
        self.assertEqual(render(self.image, [r], 8, 100).size, self.image.size)

    def test_decode_scaling_offset_label_filter_and_nms(self):
        output = np.zeros((1, 7, 3), dtype=np.float32)
        output[0, :4, 0] = [320, 320, 128, 256]
        output[0, 5, 0] = 0.9
        output[0, :, 1] = output[0, :, 0]
        output[0, 5, 1] = 0.8
        output[0, :4, 2] = [100, 100, 50, 50]
        output[0, 4, 2] = 0.95
        regions = decode(output, (1000, 500), 0.3, offset=(200, 300))
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0].label, "penis")
        self.assertEqual(regions[0].rect(), (600, 450, 800, 650))

    def test_export_keeps_source_and_strips_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "日本語の画像.png"
            target = Path(folder) / "出力.png"
            self.image.save(source)
            before = fingerprint(source)
            with self.assertRaises(ValueError):
                atomic_export(self.image, source, source)
            out = render(self.image, [Region(0, 0, 64, 64)], 8, 0)
            out.info["exif"] = b"should-not-be-copied"
            atomic_export(out, target, source)
            self.assertEqual(fingerprint(source), before)
            with Image.open(target) as saved:
                self.assertEqual(saved.tobytes(), out.tobytes())
                self.assertNotIn("exif", saved.info)
                self.assertEqual(saved.mode, "RGB")

    def test_project_round_trip_and_changed_source_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.png"
            project = Path(folder) / "work.json"
            self.image.save(source)
            save_project(project, source, [Region(2, 3, 50, 60)], 8, 15)
            _, loaded, regions, block, margin = read_project(project)
            self.assertEqual(loaded.size, self.image.size)
            self.assertEqual(regions[0].rect(), (2, 3, 52, 63))
            self.assertEqual((block, margin), (8, 15))
            save_project(project, source, [Region(2, 3, 50, 60), Region(5, 5, 20, 20, "nipple_f")], 8, 15)
            self.assertEqual([r.label for r in read_project(project)[2]], ["manual"])
            data = json.loads(project.read_text(encoding="utf-8"))
            data["regions"][0]["w"] = 999999
            project.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_project(project)
            save_project(project, source, [], 8, 15)
            Image.new("RGB", (5, 5)).save(source)
            with self.assertRaises(ValueError):
                read_project(project)

    def test_transparency_is_flattened_and_orientation_applied(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "alpha.png"
            im = Image.new("RGBA", (10, 20), (255, 0, 0, 0))
            im.putpixel((0, 0), (255, 0, 0, 255))
            im.save(path)
            loaded = load_image(path)
            self.assertEqual(loaded.getpixel((1, 1)), (255, 255, 255))
            self.assertEqual(loaded.getpixel((0, 0)), (255, 0, 0))
            rotated = Path(folder) / "rotated.png"
            exif = Image.Exif()
            exif[274] = 6
            Image.new("RGB", (10, 20)).save(rotated, exif=exif)
            self.assertEqual(load_image(rotated).size, (20, 10))

    def test_non_png_and_renamed_jpeg_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            for name, format_ in [("photo.jpg", "JPEG"), ("photo.bmp", "BMP"), ("fake.png", "JPEG")]:
                path = Path(folder) / name
                self.image.save(path, format=format_)
                with self.assertRaisesRegex(ValueError, "PNG"):
                    load_image(path)
            path = Path(folder) / "image.PNG"
            self.image.save(path, format="PNG")
            self.assertEqual(load_image(path).size, self.image.size)

    def test_contour_mosaic_leaves_empty_corners_and_concavity_untouched(self):
        region = Region(10, 10, 80, 70)
        region.set_points([[(10, 10), (90, 10), (90, 35), (35, 35), (35, 80), (10, 80)]])
        mask, (x, y) = region_mask(region, self.image.size)
        out = np.asarray(render(self.image, [region], 8, 0))
        full = np.zeros(self.image.size[::-1], dtype=bool)
        full[y : y + mask.shape[0], x : x + mask.shape[1]] = mask > 0
        np.testing.assert_array_equal(out[~full], self.pixels[~full])
        self.assertTrue(np.any(out[full] != self.pixels[full]))
        expected = np.asarray(render(self.image, [Region(0, 0, *self.image.size)], 8, 0))
        np.testing.assert_array_equal(out[full], expected[full])
        expanded, origin = region_mask(region, self.image.size, 10)
        self.assertTrue(expanded[40 - origin[1], 32 - origin[0]])
        self.assertFalse(expanded[65 - origin[1], 65 - origin[0]])
        self.assertFalse(region_covers(region, Region(60, 50, 15, 15)))
        self.assertTrue(region_covers(region, region))

    def test_contours_survive_project_save_and_invalid_vertices_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source, project = Path(folder) / "source.png", Path(folder) / "project.json"
            self.image.save(source)
            r = Region(0, 0, 1, 1)
            r.set_points([[(10, 10), (80, 20), (40, 80)]])
            save_project(project, source, [r], 8, 10)
            loaded = read_project(project)[2]
            self.assertEqual(render(self.image, [r], 8, 10).tobytes(), render(self.image, loaded, 8, 10).tobytes())
            data = json.loads(project.read_text(encoding="utf-8"))
            data["regions"][0]["contours"][0][0] = [float("nan"), 0.5]
            project.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_project(project)
            data["version"] = 1
            data["regions"][0].pop("contours")
            project.write_text(json.dumps(data), encoding="utf-8")
            self.assertIsNone(read_project(project)[2][0].contours)


if __name__ == "__main__":
    unittest.main()
