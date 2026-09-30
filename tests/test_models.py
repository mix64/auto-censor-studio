"""Model setup invariants, with no real downloads or inference."""

import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from auto_censor_studio.models import ModelSpec, download_models, verified_model


class ModelSetupTests(unittest.TestCase):
    def test_verified_download_and_reuse(self):
        payload = b"test model bytes"
        spec = ModelSpec("sample.onnx", "https://example.invalid/model", hashlib.sha256(payload).hexdigest())
        with tempfile.TemporaryDirectory() as folder, patch("auto_censor_studio.models.MODELS", {"sample": spec}):
            with patch("auto_censor_studio.models.urlopen", return_value=io.BytesIO(payload)) as download:
                download_models(folder)
                download_models(folder)
                self.assertEqual(download.call_count, 1)
            with patch("auto_censor_studio.models.model_directory", return_value=Path(folder)):
                self.assertEqual(verified_model("sample").read_bytes(), payload)

    def test_bad_download_never_replaces_existing_model(self):
        spec = ModelSpec("sample.onnx", "https://example.invalid/model", "0" * 64)
        with tempfile.TemporaryDirectory() as folder, patch("auto_censor_studio.models.MODELS", {"sample": spec}):
            target = Path(folder) / spec.filename
            target.write_bytes(b"existing")
            with patch("auto_censor_studio.models.urlopen", return_value=io.BytesIO(b"corrupt")):
                with self.assertRaises(ValueError):
                    download_models(folder)
            self.assertEqual(target.read_bytes(), b"existing")
            self.assertEqual(list(Path(folder).iterdir()), [target])


if __name__ == "__main__":
    unittest.main()
