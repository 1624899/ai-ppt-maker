from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import numpy as np
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from ppt_system.export.direct_project_script import generate_direct_project_text_script
from ppt_system.export.library_icons import identify_library_icons, normalize_icon_placements
from ppt_system.export.text_script_runtime import build_project_script_source, execute_generated_text_script
from ppt_system.generation.generation_options import resolve_generation_options
from ppt_system.generation.generation_prompts import build_elements_prompt
from ppt_system.image.icon_library import render_icon, search_icons
from ppt_system.web.services.job_edit_planner import apply_page_layout_edit, build_edit_context


class IconProvider:
    def __init__(self, icons):
        self.icons = icons
        self.purposes = []

    def build_image_message_item(self, path):
        return {"type": "input_image", "image_url": str(path)}

    def complete_json(self, messages, *, purpose=""):
        self.purposes.append(purpose)
        if "本地图标定位" in purpose:
            return {"icons": self.icons}
        return {"page_script": 'add_text(slide, "Revenue 2026", 160, 40, 220, 50, size=20, color="14254E")'}


def icon_record(**overrides):
    return {"query": "users", "left": 20, "top": 30, "width": 60, "height": 80,
            "color": "#2563EB", **overrides}


def write_images(tmp_path):
    reference = tmp_path / "reference.png"
    elements = tmp_path / "elements.png"
    image = Image.new("RGB", (400, 225), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 30, 79, 109), fill="#2563EB")
    draw.text((160, 40), "Revenue 2026", fill="#14254E")
    image.save(reference)
    # 图标和文字都被抹除，允许只靠本地图标形成独立视觉素材。
    Image.new("RGBA", image.size, (255, 255, 255, 0)).save(elements)
    return reference, elements


def test_offline_search_and_colored_transparent_render(tmp_path):
    assert search_icons("users", 1) == ["users"]
    assert search_icons("用户")
    assert search_icons("no_such_icon_8964") == []
    output = tmp_path / "users.png"
    render_icon("users", output, color="#2563EB", size=180)
    with Image.open(output) as image:
        assert image.size == (180, 180)
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] == 0
        pixels = np.asarray(image)
        colors = pixels[pixels[:, :, 3] == 255, :3]
        assert len(colors) and np.all(colors == (37, 99, 235))
    assert "#2563EB" in output.with_suffix(".svg").read_text(encoding="utf-8")
    assert "Lucide" in (tmp_path / "icons.LICENSE.txt").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="不存在"):
        render_icon("../users", output, color="#2563EB", size=180)


@pytest.mark.parametrize("overrides", [
    {"left": -1}, {"top": 220}, {"width": 0}, {"height": float("inf")},
    {"left": float("nan")}, {"left": True}, {"width": "60"}, {"color": "blue"},
    {"query": ""}, {"query": "unmatched_icon_name_8964"},
])
def test_reject_invalid_icon_result(overrides):
    with pytest.raises(ValueError):
        normalize_icon_placements({"icons": [icon_record(**overrides)]}, 400, 225)


def test_empty_icon_result_and_canvas_edge():
    assert normalize_icon_placements({"icons": []}, 400, 225) == []
    icons = normalize_icon_placements({"icons": [icon_record(left=340, top=145)]}, 400, 225)
    assert icons[0]["name"] == "users"


def test_icon_identification_checkpoint_tracks_source_images(tmp_path):
    reference, elements = write_images(tmp_path)
    provider = IconProvider([icon_record()])
    kwargs = dict(reference_image=reference, elements_image=elements, page_dir=tmp_path / "work",
                  page_no=1, width=400, height=225)
    first = identify_library_icons(provider, **kwargs)
    assert identify_library_icons(provider, **kwargs) == first
    assert len(provider.purposes) == 1
    Image.new("RGB", (400, 225), "red").save(reference)
    identify_library_icons(provider, **kwargs)
    assert len(provider.purposes) == 2


def test_library_icons_export_in_both_layer_modes_and_resume(tmp_path):
    reference, elements = write_images(tmp_path)
    project = {"image_width": 400, "image_height": 225, "pages": [{
        "page_no": 1, "title": "Revenue 2026", "visual_image": str(elements),
        "reference_image": str(reference), "icon_source": "library", "texts": [],
    }]}
    provider = IconProvider([icon_record()])
    work_dir = tmp_path / "work"
    result = generate_direct_project_text_script(
        provider, project, work_dir, tmp_path / "result.pptx", refine_rounds=0,
    )
    assert len(provider.purposes) == 2
    manifest = json.loads((work_dir / "page_01/assets/assets.json").read_text(encoding="utf-8"))
    assert manifest["count"] == 1
    asset = manifest["assets"][0]
    assert (asset["source"], asset["icon_name"], asset["color"]) == ("lucide", "users", "#2563EB")
    assert (asset["left"], asset["top"], asset["width"], asset["height"]) == (20, 40, 60, 60)
    placeholders = json.loads((work_dir / "page_01/text_placeholders.json").read_text(encoding="utf-8"))
    assert placeholders["placeholders"]
    assert all(box["left"] > 100 for box in placeholders["placeholders"])

    for mode, expected_slides in (("overlay", 1), ("separate_slides", 2)):
        output = tmp_path / f"{mode}.pptx"
        script = tmp_path / f"{mode}.py"
        script.write_text(build_project_script_source(
            project, work_dir, output, result["page_scripts"], layer_mode=mode,
        ), encoding="utf-8")
        execute_generated_text_script(script)
        deck = Presentation(output)
        assert len(deck.slides) == expected_slides
        pictures = [shape for shape in deck.slides[0].shapes if shape.shape_type == MSO_SHAPE_TYPE.PICTURE]
        assert len(pictures) == 1
        assert pictures[0].left == pytest.approx(20 / 400 * deck.slide_width, abs=1)
        assert pictures[0].top == pytest.approx(40 / 225 * deck.slide_height, abs=1)
        assert "Revenue 2026" in " ".join(shape.text for shape in deck.slides[-1].shapes if shape.has_text_frame)

    generate_direct_project_text_script(provider, project, work_dir, tmp_path / "result.pptx", refine_rounds=0)
    assert len(provider.purposes) == 2


def test_icon_source_configuration_and_prompt_contract():
    assert resolve_generation_options({})["icon_source"] == "generated"
    assert resolve_generation_options({}, config={"default_icon_source": "library"})["icon_source"] == "library"
    assert resolve_generation_options({"icon_source": "generated"}, config={"default_icon_source": "library"})["icon_source"] == "generated"
    assert "icon" in build_elements_prompt("library")
    assert build_elements_prompt("generated") == "删除图片中的所有文字"
    custom = build_elements_prompt("library", base_prompt="保留右侧照片")
    assert "保留右侧照片" in custom
    assert build_elements_prompt("library", base_prompt=custom) == custom
    with pytest.raises(ValueError):
        resolve_generation_options({"icon_source": "unknown"})


def test_local_visual_feedback_reaches_generation_prompt_without_changing_facts():
    instruction = "保留项：标题、2026 年营收 3.8 亿元与蓝色主色；修改项：删除多余光晕，突出核心结论"
    state = {"job_meta": {"generation_options": {"icon_source": "library"}}, "plan": {}, "pages": [
        {"page_no": 1, "title": "年度营收", "summary": "2026 年营收 3.8 亿元",
         "bullets": ["2026 年营收 3.8 亿元"], "layout_family": "summary_detail",
         "visual_suggestion": "蓝色营收卡片", "page_richness": "medium"},
        {"page_no": 2, "title": "下一步", "summary": "保持原有计划"},
    ]}
    original = copy.deepcopy(state)
    apply_page_layout_edit(state, 1, instruction, {}, build_edit_context(state))
    page = state["pages"][0]
    assert instruction in page["reference_prompt"]
    assert "蓝色营收卡片" in page["reference_prompt"]
    assert "icon" in page["elements_prompt"]
    for field in ("title", "summary", "bullets"):
        assert page[field] == original["pages"][0][field]
    assert state["pages"][1] == original["pages"][1]
