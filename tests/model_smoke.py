"""Inference on synthetic, non-sensitive inputs. Does not measure real-image accuracy."""

import time
from PIL import Image, ImageDraw

from auto_censor_studio.services.detection import Detector

image = Image.new("RGB", (1400, 1000), "#f4f1e9")
draw = ImageDraw.Draw(image)
draw.rectangle((200, 200, 600, 600), fill="#4767a1")
draw.ellipse((700, 300, 1100, 700), fill="#70b69c")
detector = Detector()
start = time.perf_counter()
result = detector.detect(image, tiled=True, progress=lambda a, b: print(f"Inference {a}/{b}"))
assert isinstance(result, list)
assert all(0 <= r.x < image.width and 0 <= r.y < image.height for r in result)
print(f"CPU inference succeeded in {time.perf_counter() - start:.2f}s; {len(result)} candidates.")
print("Real illustration recall/precision has not been evaluated.")
