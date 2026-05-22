from __future__ import annotations

import unittest

from ppt_system.content_agent import fallback_style_guide, normalize_content_plan
from ppt_system.generation_options import resolve_generation_options


class CoverPageOptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.style_guide = fallback_style_guide("蓝白科技汇报", has_reference_images=True)

    def test_disable_cover_page_forces_first_page_to_body_mode(self) -> None:
        result = {
            "pages": [
                {
                    "page_no": 1,
                    "title": "项目概览",
                    "summary": "介绍项目目标与范围",
                    "bullets": ["目标", "范围"],
                    "layout_family": "hero_with_supporting_cards",
                    "reference_mode": "edit_with_refs",
                },
                {
                    "page_no": 2,
                    "title": "实施路径",
                    "summary": "介绍实施步骤",
                    "bullets": ["方案", "执行"],
                    "layout_family": "process_horizontal",
                },
            ]
        }

        plan = normalize_content_plan(
            result,
            content="项目概览与实施路径",
            page_count=2,
            image_width=2048,
            image_height=1152,
            style_notes="蓝白科技汇报",
            style_guide=self.style_guide,
            has_reference_images=True,
            generation_options={"include_cover_page": False},
        )

        self.assertEqual(plan["pages"][0]["reference_mode"], "generation")
        self.assertEqual(plan["pages"][0]["difference_from_previous"], "正文开篇，直接进入核心内容")

    def test_enable_cover_page_keeps_first_page_cover_strategy(self) -> None:
        result = {
            "pages": [
                {
                    "page_no": 1,
                    "title": "年度经营复盘",
                    "summary": "总览全年表现",
                    "bullets": ["增长", "结构"],
                    "layout_family": "hero_with_supporting_cards",
                    "reference_mode": "invalid_mode",
                },
                {
                    "page_no": 2,
                    "title": "核心数据",
                    "summary": "进入正文分析",
                    "bullets": ["收入", "利润"],
                    "layout_family": "grid_n_x_m",
                },
            ]
        }

        plan = normalize_content_plan(
            result,
            content="年度经营复盘与核心数据",
            page_count=2,
            image_width=2048,
            image_height=1152,
            style_notes="蓝白科技汇报",
            style_guide=self.style_guide,
            has_reference_images=True,
            generation_options=resolve_generation_options({"include_cover_page": "on"}),
        )

        self.assertEqual(plan["pages"][0]["reference_mode"], "edit_with_refs")
        self.assertEqual(plan["pages"][0]["difference_from_previous"], "首页建立视觉基调")


if __name__ == "__main__":
    unittest.main()
