from __future__ import annotations

import json
import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ppt_system.export.editable_delivery_cache import load_cached_editable_delivery, save_editable_delivery_cache
from ppt_system.export.export_layer_mode import OVERLAY_LAYER_MODE


class EditableDeliveryCacheTests(unittest.TestCase):
    def test_reuses_existing_output_when_bundle_is_older(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            work_dir.mkdir()
            bundle_path = root / "editable_delivery.bundle.json"
            output_pptx = root / "result.editable.overlay.pptx"
            bundle_path.write_text(
                json.dumps(
                    {
                        "project": {"pages": [{"page_no": 1}, {"page_no": 2}]},
                        "work_dir": str(work_dir),
                        "assets": {"page_count": 2},
                        "page_results": [{"page_no": 1}, {"page_no": 2}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output_pptx.write_bytes(b"pptx")
            self._set_mtime(bundle_path, time.time() - 20)
            self._set_mtime(output_pptx, time.time())

            cached = load_cached_editable_delivery(bundle_path, output_pptx, layer_mode=OVERLAY_LAYER_MODE)

            self.assertIsNotNone(cached)
            self.assertEqual(cached["output_pptx"], str(output_pptx))
            self.assertEqual(cached["logical_page_count"], 2)
            self.assertEqual(cached["page_count"], 2)
            self.assertEqual(cached["layer_mode"], OVERLAY_LAYER_MODE)

    def test_cache_misses_after_bundle_content_changes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle_path = root / "editable_delivery.bundle.json"
            output_pptx = root / "result.editable.overlay.pptx"
            bundle_path.write_text(
                json.dumps({"project": {"pages": [{"page_no": 1}]}, "work_dir": str(root)}, ensure_ascii=False),
                encoding="utf-8",
            )
            output_pptx.write_bytes(b"pptx")
            export_payload = {
                "output_pptx": str(output_pptx),
                "logical_page_count": 1,
                "page_count": 1,
                "layer_mode": OVERLAY_LAYER_MODE,
            }
            save_editable_delivery_cache(
                bundle_path,
                output_pptx,
                layer_mode=OVERLAY_LAYER_MODE,
                export_payload=export_payload,
            )

            bundle_path.write_text(
                json.dumps({"project": {"pages": [{"page_no": 1}, {"page_no": 2}]}, "work_dir": str(root)}, ensure_ascii=False),
                encoding="utf-8",
            )
            self._set_mtime(bundle_path, time.time())
            self._set_mtime(output_pptx, time.time() - 20)

            cached = load_cached_editable_delivery(bundle_path, output_pptx, layer_mode=OVERLAY_LAYER_MODE)

            self.assertIsNone(cached)

    @staticmethod
    def _set_mtime(path: Path, timestamp: float) -> None:
        os.utime(path, (timestamp, timestamp))


if __name__ == "__main__":
    unittest.main()
