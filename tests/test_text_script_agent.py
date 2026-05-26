from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from PIL import Image
from pptx import Presentation
from pptx.enum.text import MSO_AUTO_SIZE

from ppt_system.direct_page_script import (
    build_direct_page_refine_prompt,
    build_direct_page_prompt,
    generate_direct_single_page_ppt,
)
from ppt_system.export_pipeline import export_project_to_pptx
from ppt_system.text_script_runtime import build_project_script_source, execute_generated_text_script, normalize_page_script
from ppt_system.text_style_runtime import should_wrap_text
from rerun_text_page import normalize_output_pptx_name, parse_args


class FakeChatProvider:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict[str, Any]]] = []

    def build_image_message_item(self, image_path: Path) -> dict[str, Any]:
        return {"type": "image_url", "image_url": {"url": str(image_path)}}

    def complete_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls.append(messages)
        if not self.responses:
            raise RuntimeError("no more responses")
        return self.responses.pop(0)


class TextScriptRuntimeAndDirectPathTests(unittest.TestCase):
    def test_normalize_output_pptx_name_appends_missing_suffix(self) -> None:
        self.assertEqual(normalize_output_pptx_name("demo"), "demo.pptx")
        self.assertEqual(normalize_output_pptx_name("demo.pptx"), "demo.pptx")

    def test_rerun_text_page_defaults_refine_rounds_to_zero(self) -> None:
        with patch("sys.argv", ["rerun_text_page.py", "--project", "demo.json", "--page-no", "2", "--output-dir", "out"]):
            args = parse_args()
        self.assertEqual(args.refine_rounds, 1)

    def test_should_wrap_text_keeps_single_line_banner_and_badge_unwrapped(self) -> None:
        self.assertFalse(should_wrap_text("01", 118, 88, 38))
        self.assertFalse(should_wrap_text("AI 转换", 300, 58, 26))
        self.assertFalse(should_wrap_text("进阶玩法：让 AI 从聊天助手变成流程生产工具", 1350, 82, 30))

    def test_should_wrap_text_allows_explicit_multiline_and_tall_body_wrapping(self) -> None:
        self.assertTrue(should_wrap_text("第一行\n第二行", 240, 90, 20))
        self.assertTrue(should_wrap_text("这是一个需要自动换行的长段落文本", 180, 140, 20))

    def test_direct_page_prompt_keeps_reference_and_elements_constraints(self) -> None:
        prompt = build_direct_page_prompt(image_width=2048, image_height=1152)
        self.assertIn("第一张图是完整参考图，第二张图是去文字后的元素图", prompt)
        self.assertIn("元素会在导出时单独加入", prompt)

    def test_direct_page_refine_prompt_allows_asset_adjustments(self) -> None:
        prompt = build_direct_page_refine_prompt(
            image_width=2048,
            image_height=1152,
            page_script='add_text(slide, "标题", 100, 100, 300, 60, size=24)',
            asset_adjustments={"global": {"dy": 6}},
            round_index=0,
        )
        self.assertIn("asset_adjustments", prompt)
        self.assertIn("本轮只修文字", prompt)
        self.assertIn("asset_adjustments 固定返回空对象 {}", prompt)
        self.assertIn("请直接修正 page_script", prompt)

    def test_normalize_page_script_rejects_disallowed_code(self) -> None:
        with self.assertRaises(RuntimeError):
            normalize_page_script("import os")

    def test_normalize_page_script_preserves_valid_text_call(self) -> None:
        script = 'add_text(slide, "标题", 10, 20, 200, 60, size=24, color="163A63")'
        self.assertEqual(normalize_page_script(script), script)

    def test_normalize_page_script_coalesces_multiline_call(self) -> None:
        script = 'add_text(slide,\n"标题",\n10, 20, 200, 60,\nsize=24, color="163A63")'
        expected = 'add_text(slide, "标题", 10, 20, 200, 60, size=24, color="163A63")'
        self.assertEqual(normalize_page_script(script), expected)

    def test_build_and_execute_project_script_produces_editable_ppt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            page_assets_dir = work_dir / "page_01" / "assets"
            page_assets_dir.mkdir(parents=True, exist_ok=True)
            output_pptx = root / "result.pptx"
            Image.new("RGBA", (40, 30), (0, 128, 255, 255)).save(page_assets_dir / "asset_001.png")
            (page_assets_dir / "assets.json").write_text(
                json.dumps(
                    {"assets": [{"file": "asset_001.png", "left": 40, "top": 50, "width": 120, "height": 80}]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            project = {
                "slide_width_inch": 13.333333,
                "image_width": 400,
                "image_height": 240,
                "default_font": {"font_name": "Microsoft YaHei", "font_size": 24, "color": "355C7D"},
                "pages": [
                    {
                        "page_no": 1,
                        "title": "示例页",
                        "summary": "摘要",
                        "texts": [
                            {"role": "title", "text": "示例页", "left": 20, "top": 20, "width": 160, "height": 40},
                            {"role": "body", "text": "第一条", "left": 30, "top": 120, "width": 200, "height": 40},
                        ],
                    }
                ],
            }
            script_source = build_project_script_source(
                project,
                work_dir,
                output_pptx,
                [{"page_no": 1, "script": 'add_text_ref(slide, page_texts, "title", 18, 18, 180, 44, size=24, color="163A63", bold=True)\nadd_text_ref(slide, page_texts, "body_1", 36, 122, 210, 36, size=14, color="355C7D", bold=False)'}],
                include_assets=True,
            )
            script_path = work_dir / "generated_text_layout.py"
            script_path.write_text(script_source, encoding="utf-8")

            execute_generated_text_script(script_path)

            prs = Presentation(str(output_pptx))
            slide = prs.slides[0]
            texts = [shape.text for shape in slide.shapes if hasattr(shape, "text") and shape.text]
            self.assertIn("示例页", texts)
            self.assertIn("第一条", texts)
            text_shapes = [shape for shape in slide.shapes if hasattr(shape, "text") and shape.text]
            self.assertEqual(text_shapes[0].text_frame.auto_size, MSO_AUTO_SIZE.NONE)

    def test_generated_script_maps_assets_using_manifest_canvas_size(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            page_assets_dir = work_dir / "page_01" / "assets"
            page_assets_dir.mkdir(parents=True, exist_ok=True)
            output_pptx = root / "result.pptx"
            Image.new("RGBA", (10, 10), (0, 128, 255, 255)).save(page_assets_dir / "asset_001.png")
            (page_assets_dir / "assets.json").write_text(
                json.dumps(
                    {
                        "image_width": 800,
                        "image_height": 400,
                        "assets": [
                            {"file": "asset_001.png", "left": 80, "top": 40, "width": 160, "height": 80}
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            project = {
                "slide_width_inch": 10.0,
                "image_width": 400,
                "image_height": 200,
                "default_font": {"font_name": "Microsoft YaHei", "font_size": 24, "color": "355C7D"},
                "pages": [{"page_no": 1, "title": "示例页", "summary": "", "texts": []}],
            }
            script_source = build_project_script_source(
                project,
                work_dir,
                output_pptx,
                [{"page_no": 1, "script": ""}],
                include_assets=True,
            )
            script_path = work_dir / "generated_text_layout.py"
            script_path.write_text(script_source, encoding="utf-8")

            execute_generated_text_script(script_path)

            prs = Presentation(str(output_pptx))
            picture_shapes = [shape for shape in prs.slides[0].shapes if shape.shape_type == 13]
            self.assertEqual(len(picture_shapes), 1)
            picture = picture_shapes[0]
            self.assertAlmostEqual(picture.left / prs.slide_width, 0.1, places=3)
            self.assertAlmostEqual(picture.top / prs.slide_height, 0.1, places=3)

    def test_generated_script_applies_asset_adjustments(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            page_assets_dir = work_dir / "page_01" / "assets"
            page_assets_dir.mkdir(parents=True, exist_ok=True)
            output_pptx = root / "result.pptx"
            Image.new("RGBA", (10, 10), (0, 128, 255, 255)).save(page_assets_dir / "asset_001.png")
            (page_assets_dir / "assets.json").write_text(
                json.dumps(
                    {
                        "image_width": 400,
                        "image_height": 200,
                        "assets": [
                            {"index": 1, "file": "asset_001.png", "left": 40, "top": 20, "width": 80, "height": 40}
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            project = {
                "slide_width_inch": 10.0,
                "image_width": 400,
                "image_height": 200,
                "default_font": {"font_name": "Microsoft YaHei", "font_size": 24, "color": "355C7D"},
                "pages": [{"page_no": 1, "title": "示例页", "summary": "", "texts": []}],
            }
            script_source = build_project_script_source(
                project,
                work_dir,
                output_pptx,
                [{"page_no": 1, "script": "", "asset_adjustments": {"global": {"dx": 20, "dy": 10}}}],
                include_assets=True,
            )
            script_path = work_dir / "generated_text_layout.py"
            script_path.write_text(script_source, encoding="utf-8")

            execute_generated_text_script(script_path)

            prs = Presentation(str(output_pptx))
            picture = [shape for shape in prs.slides[0].shapes if shape.shape_type == 13][0]
            self.assertAlmostEqual(picture.left / prs.slide_width, 0.15, places=3)
            self.assertAlmostEqual(picture.top / prs.slide_height, 0.15, places=3)

    def test_direct_single_page_generation_produces_editable_ppt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            output_pptx = root / "direct_result.pptx"
            reference_path = root / "reference.png"
            visual_path = root / "visual.png"
            Image.new("RGBA", (400, 240), (255, 255, 255, 255)).save(reference_path)
            Image.new("RGBA", (400, 240), (255, 255, 255, 0)).save(visual_path)
            with Image.open(visual_path).convert("RGBA") as image:
                image.paste((0, 82, 214, 255), (40, 40, 120, 100))
                image.save(visual_path)
            provider = FakeChatProvider(
                [{"page_script": 'add_text(slide, "示例页", 18, 18, 180, 44, size=24, color="163A63", bold=True)'}]
            )

            with patch("ppt_system.direct_page_script.render_pptx_first_slide_to_png", return_value=None):
                result = generate_direct_single_page_ppt(
                    provider,
                    reference_path,
                    visual_path,
                    work_dir,
                    output_pptx,
                    page_no=2,
                )

            self.assertEqual(result["output_pptx"], str(output_pptx))
            self.assertTrue(output_pptx.exists())
            prs = Presentation(str(output_pptx))
            slide = prs.slides[0]
            texts = [shape.text for shape in slide.shapes if hasattr(shape, "text") and shape.text]
            self.assertIn("示例页", texts)
            self.assertEqual(len(provider.calls), 1)
            self.assertEqual(len(provider.calls[0][1]["content"]), 3)
            self.assertFalse(result["office_render_available"])
            self.assertEqual(result["refine_rounds_applied"], 0)

    def test_direct_single_page_generation_can_refine_with_office_render(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            output_pptx = root / "direct_result.pptx"
            reference_path = root / "reference.png"
            visual_path = root / "visual.png"
            preview_path = work_dir / "office_preview_round_01.png"
            Image.new("RGBA", (400, 240), (255, 255, 255, 255)).save(reference_path)
            Image.new("RGBA", (400, 240), (255, 255, 255, 0)).save(visual_path)
            with Image.open(visual_path).convert("RGBA") as image:
                image.paste((0, 82, 214, 255), (40, 40, 120, 100))
                image.save(visual_path)
            provider = FakeChatProvider(
                [
                    {"page_script": 'add_text(slide, "初稿", 18, 18, 180, 44, size=24, color="163A63", bold=True)'},
                    {
                        "page_script": 'add_text(slide, "终稿", 20, 20, 200, 48, size=26, color="163A63", bold=True)',
                        "asset_adjustments": {"global": {"dy": 8}},
                    },
                ]
            )

            def fake_render(*args, **kwargs):
                preview_path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGBA", (400, 240), (255, 255, 255, 255)).save(preview_path)
                return preview_path

            with patch("ppt_system.direct_page_script.render_pptx_first_slide_to_png", side_effect=fake_render):
                result = generate_direct_single_page_ppt(
                    provider,
                    reference_path,
                    visual_path,
                    work_dir,
                    output_pptx,
                    page_no=2,
                    refine_rounds=1,
                )

            self.assertTrue(output_pptx.exists())
            self.assertTrue(result["office_render_available"])
            self.assertEqual(result["refine_rounds_applied"], 1)
            self.assertEqual(len(result["office_preview_paths"]), 1)
            self.assertEqual(len(result["comparison_paths"]), 1)
            self.assertEqual(len(provider.calls), 2)
            final_script = (work_dir / "generated_text_layout.py").read_text(encoding="utf-8")
            self.assertIn("终稿", final_script)
            self.assertNotIn('"dy": 8', final_script)

    def test_export_project_to_pptx_uses_direct_office_refine(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            output_pptx = root / "result.pptx"
            visual_path = root / "visual.png"
            reference_path = root / "reference.png"
            Image.new("RGBA", (400, 240), (255, 255, 255, 0)).save(visual_path)
            with Image.open(visual_path).convert("RGBA") as image:
                image.paste((0, 82, 214, 255), (40, 40, 120, 100))
                image.save(visual_path)
            Image.new("RGBA", (400, 240), (255, 255, 255, 255)).save(reference_path)
            project = {
                "slide_width_inch": 13.333333,
                "image_width": 400,
                "image_height": 240,
                "default_font": {"font_name": "Microsoft YaHei", "font_size": 24, "color": "355C7D"},
                "pages": [
                    {
                        "page_no": 1,
                        "title": "脚本页",
                        "summary": "摘要",
                        "visual_image": str(visual_path),
                        "reference_image": str(reference_path),
                        "texts": [],
                    }
                ],
            }
            provider = FakeChatProvider([{"page_script": 'add_text(slide, "脚本页", 12, 14, 130, 36, size=20, color="163A63", bold=True)'}])

            with patch("ppt_system.direct_project_script.render_pptx_first_slide_to_png", return_value=None):
                result = export_project_to_pptx(
                    project,
                    work_dir,
                    output_pptx,
                    chat_provider=provider,  # type: ignore[arg-type]
                )

            self.assertEqual(result["text_layout_strategy"], "direct_office_refine")
            self.assertTrue(Path(result["text_script_path"]).exists())
            self.assertTrue(output_pptx.exists())
            self.assertIn("page_results", result)

    def test_export_project_applies_third_round_asset_alignment_after_text_refine(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            output_pptx = root / "result.pptx"
            visual_path = root / "visual.png"
            reference_path = root / "reference.png"
            Image.new("RGBA", (400, 240), (255, 255, 255, 0)).save(visual_path)
            with Image.open(visual_path).convert("RGBA") as image:
                image.paste((0, 82, 214, 255), (40, 40, 120, 100))
                image.save(visual_path)
            Image.new("RGBA", (400, 240), (255, 255, 255, 255)).save(reference_path)
            project = {
                "slide_width_inch": 13.333333,
                "image_width": 400,
                "image_height": 240,
                "default_font": {"font_name": "Microsoft YaHei", "font_size": 24, "color": "355C7D"},
                "pages": [
                    {
                        "page_no": 1,
                        "title": "脚本页",
                        "summary": "摘要",
                        "visual_image": str(visual_path),
                        "reference_image": str(reference_path),
                        "texts": [],
                    }
                ],
            }
            provider = FakeChatProvider(
                [
                    {"page_script": 'add_text(slide, "首轮文字", 12, 14, 130, 36, size=20, color="163A63", bold=True)'},
                    {"page_script": 'add_text(slide, "二轮改字", 20, 24, 150, 40, size=22, color="163A63", bold=True)'},
                ]
            )

            class FakeDecision:
                should_apply = True
                suggested_adjustments = {"global": {"dx": 0, "dy": 16}}
                dx = 0
                dy = 16
                baseline_iou = 0.1
                shifted_iou = 0.3
                confidence = 0.2
                reason = "apply-global-shift"

            with patch("ppt_system.direct_project_script.render_pptx_first_slide_to_png", return_value=reference_path):
                with patch("ppt_system.direct_project_script.analyze_global_asset_alignment", return_value=FakeDecision()):
                    with patch(
                        "ppt_system.direct_project_script.analyze_text_asset_overlaps",
                        return_value=type(
                            "FakeOverlap",
                            (),
                            {
                                "total_boxes": 1,
                                "overlap_box_count": 1,
                                "overlap_ratio": 1.0,
                                "max_overlap_pixels": 200,
                                "overlapping_box_indices": [1],
                            },
                        )(),
                    ):
                        result = export_project_to_pptx(
                            project,
                            work_dir,
                            output_pptx,
                            chat_provider=provider,  # type: ignore[arg-type]
                        )

            final_script = Path(result["text_script_path"]).read_text(encoding="utf-8")
            self.assertIn("二轮改字", final_script)
            self.assertIn('"dy": 16', final_script)

    def test_export_project_to_pptx_requires_chat_provider(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_dir = root / "work"
            output_pptx = root / "result.pptx"
            visual_path = root / "visual.png"
            reference_path = root / "reference.png"
            Image.new("RGBA", (400, 240), (255, 255, 255, 255)).save(visual_path)
            Image.new("RGBA", (400, 240), (255, 255, 255, 255)).save(reference_path)
            project = {
                "slide_width_inch": 13.333333,
                "image_width": 400,
                "image_height": 240,
                "default_font": {"font_name": "Microsoft YaHei", "font_size": 24, "color": "355C7D"},
                "pages": [
                    {
                        "page_no": 1,
                        "title": "脚本页",
                        "summary": "摘要",
                        "visual_image": str(visual_path),
                        "reference_image": str(reference_path),
                        "texts": [],
                    }
                ],
            }

            with self.assertRaises(RuntimeError):
                export_project_to_pptx(project, work_dir, output_pptx)


if __name__ == "__main__":
    unittest.main()
