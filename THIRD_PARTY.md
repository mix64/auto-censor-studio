# Third-party components

Auto Censor Studio is not an official pixiv product.

## UI assets

- Design reference: https://design.google/library/expressive-material-design-google-research
- Icons: Google Material Symbols Rounded, bundled locally as `auto_censor_studio/assets/MaterialSymbolsRounded.ttf`.
- Source: https://github.com/google/material-design-icons/tree/master/variablefont
- License text: `auto_censor_studio/assets/MaterialSymbols-LICENSE.txt`.
- Font and codepoints retrieved 2026-09-30. No icon/font request is made at app runtime.

## Detection model

- Publisher: deepghs
- Repository: https://huggingface.co/deepghs/anime_censor_detection
- Revision: `0cf62fd6b28213b40ae0c0055f92e7ae6a96bdc2`
- File: `censor_detect_v1.0_s/model.onnx`
- SHA-256: `2c2524824d7d320c5619a0a73702a2e2186f619067c823d211e94f7cfe489cba`
- Model repository license metadata: MIT (retrieved 2026-09-30).
- Training architecture reported by the publisher: YOLOv8.
- Inference follows the publisher's documented default: RGB input, 640x640 resize, float32 CHW divided by 255; output is center-x/center-y/width/height and three class scores.
- Original model output labels: `nipple_f`, `penis`, `pussy`.
- Application detection classes: `penis`, `pussy` only. The `nipple_f` channel is always discarded; it cannot be enabled from the UI or the detector API. Pretrained weights and the original channel order are retained for correct inference.

The application's processing code is independently implemented; it does not install or bundle the imgutils or Ultralytics Python packages. The publisher's source was consulted to confirm this model's input/output format. The model's labels are used as identifiers; they are displayed in Japanese in the UI.

## Contour models

- MobileSAM upstream: https://github.com/ChaoningZhang/MobileSAM
- ONNX conversion publisher: https://huggingface.co/Acly/MobileSAM
- Pinned revision: `0d3b403339b4674a82493d5e97964dd78089ddc8`
- `mobile_sam_image_encoder.onnx`: SHA-256 `580f5fb648ea1062c0aabc26217aed56921985f03f0cbbd852bba81d760cc749`
- `sam_mask_decoder_single.onnx`: SHA-256 `93915fc7c993ab9d59ab8c9ccd3bce37f7509c81ab4150a74abd4d2abbd8570d`
- Upstream MobileSAM license: Apache-2.0, bundled as `auto_censor_studio/assets/MobileSAM-LICENSE`. The ONNX conversion repository declares MIT metadata.
- The encoder includes normalization and padding; it accepts resized RGB float32 HWC in the 0–255 range. The decoder receives box-corner prompts and a padding prompt. We use local crops for small image details, retain outer contours, and fill interior holes.
- All model hashes are checked before loading. No remote model code or Python model package is executed.

## Installed libraries

Their license texts are provided in each package's installed distribution. Refer to the upstream projects for redistribution requirements.

- PySide6 Essentials / Qt: https://doc.qt.io/qtforpython-6/licenses.html
- Pillow: https://github.com/python-pillow/Pillow
- NumPy: https://github.com/numpy/numpy
- ONNX Runtime: https://github.com/microsoft/onnxruntime
- OpenCV headless: https://github.com/opencv/opencv

`requirements.txt` pins the tested direct dependencies. An ONNX Runtime CPU session is used, and runtime telemetry is disabled before session creation. Only setup scripts download dependencies or the pinned model.
