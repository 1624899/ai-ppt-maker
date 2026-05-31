from __future__ import annotations

import unittest

from ppt_system.generation.content_agent import normalize_content_plan
from ppt_system.export.export_pipeline import rebuild_page_texts
from ppt_system.generation.page_evaluator import evaluate_page


class StyleRuntimeAndEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.light_style_guide = {
            "style_name": "蓝白科技风",
            "prompt_anchor": "白底浅蓝科技纹理，深蓝标题，细描边圆角卡片",
            "style_core": {
                "background_tone": "高明度白色与极浅蓝背景为主，整体干净留白充足",
                "palette": ["深海军蓝", "科技亮蓝", "浅蓝灰"],
                "title_style": "深蓝粗体大标题",
                "card_style": "细蓝描边圆角卡片",
                "icon_style": "线性扁平图标",
                "line_style": "蓝色箭头与虚线连接器",
            },
            "layout_families": ["hub_and_spoke", "process_horizontal", "grid_n_x_m"],
            "element_primitives": [
                "带编号的蓝色阶段标签",
                "圆角信息卡片",
                "盾牌安全徽章",
                "红色风险告警卡",
                "蓝色线性功能图标",
                "虚线箭头连接器",
                "底部横向能力标签栏",
                "中心环形闭环流程",
                "坐标轴风险矩阵",
                "浅蓝科技网格背景",
            ],
            "variation_policy": {
                "same_layout_max_repeat": 1,
                "min_distinct_layout_families": 3,
                "allow_local_recomposition": True,
            },
            "negative_rules": [
                "避免深色沉重背景",
                "避免复杂炫光背景",
            ],
            "prompt_compression": "compressed",
        }

    def test_evaluator_uses_page_specific_visual_plan(self) -> None:
        page = {
            "page_no": 1,
            "layout_family": "hub_and_spoke",
            "element_plan": {
                "primitives": [
                    "中心盾牌安全徽章",
                    "圆角信息卡片",
                    "蓝色线性功能图标",
                    "虚线箭头连接器",
                    "底部横向能力标签栏",
                    "浅蓝科技网格背景",
                ],
                "icon_topics": ["搜索放大镜", "AI 智囊大脑", "雷达扫描"],
                "diagram_type": "中心辐射式信息雷达对比图",
            },
            "image_prompt": (
                "生成一张 16:9 企业级蓝白科技风 PPT 单页效果图。"
                "背景为高明度白色与极浅蓝科技网格纹理，中心是盾牌徽章与蓝色线性大脑雷达图标。"
                "左侧与右侧使用圆角卡片，底部有横向标签栏，并用虚线箭头连接。"
            ),
        }

        result = evaluate_page(page, self.light_style_guide, previous_pages=[])

        self.assertFalse(
            any("视觉元素计划覆盖不足" in issue for issue in result["issues"]),
            result["issues"],
        )

    def test_normalize_content_plan_recolors_light_theme_texts(self) -> None:
        result = {
            "style_type": "商务汇报",
            "pages": [
                {
                    "page_no": 1,
                    "title": "AI是信息雷达",
                    "summary": "本页解释 AI 的本质是高效信息获取",
                    "bullets": [
                        "学习 AI 的本质：高效获取、筛选、提炼信息",
                        "从关键词搜索切换为结构化检索型对话",
                    ],
                    "layout_family": "hub_and_spoke",
                }
            ],
        }

        plan = normalize_content_plan(
            result,
            content="学习 AI 的本质是高效信息获取",
            page_count=1,
            image_width=2048,
            image_height=1152,
            style_notes="蓝白科技风",
            style_guide=self.light_style_guide,
            has_reference_images=True,
            generation_options={"include_cover_page": False},
        )

        texts = plan["pages"][0]["texts"]
        title = next(item for item in texts if item.get("role") == "title")
        body = next(item for item in texts if item.get("role") == "body")

        self.assertEqual(title["color"], "163A63")
        self.assertEqual(body["color"], "355C7D")

    def test_rebuild_page_texts_recolors_existing_light_texts(self) -> None:
        page = {
            "page_no": 1,
            "title": "AI是信息雷达",
            "summary": "本页解释 AI 的本质是高效信息获取",
            "layout_family": "hub_and_spoke",
            "texts": [
                {
                    "role": "title",
                    "text": "AI是信息雷达",
                    "left": 614,
                    "top": 46,
                    "width": 819,
                    "height": 115,
                    "font_size": 34,
                    "bold": True,
                    "color": "FFFFFF",
                },
                {
                    "role": "body",
                    "text": "• 学习 AI 的本质：高效获取、筛选、提炼信息",
                    "left": 123,
                    "top": 230,
                    "width": 410,
                    "height": 323,
                    "font_size": 22,
                    "bold": False,
                    "color": "DDEBFF",
                },
            ],
        }

        rebuilt = rebuild_page_texts(page, 2048, 1152, self.light_style_guide)

        title = next(item for item in rebuilt if item.get("role") == "title")
        body = next(item for item in rebuilt if item.get("role") == "body")

        self.assertEqual(title["color"], "163A63")
        self.assertEqual(body["color"], "355C7D")


if __name__ == "__main__":
    unittest.main()
