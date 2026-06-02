from __future__ import annotations

import unittest

from ppt_system.generation.title_extraction import (
    DEFAULT_JOB_TITLE,
    derive_title_from_content,
    normalize_title_text,
    resolve_plan_title,
)


class TitleExtractionTests(unittest.TestCase):
    def test_extracts_html_heading_from_rich_content(self) -> None:
        content = '<p align="center"><h1 align="center">AI PPT Maker</h1><p>后续介绍产品价值和流程。</p>'

        self.assertEqual(derive_title_from_content(content), "AI PPT Maker")

    def test_extracts_explicit_title_line(self) -> None:
        content = "PPT标题：企业级 AI 产品介绍\n任务内容：说明架构、部署和交付。"

        self.assertEqual(derive_title_from_content(content), "企业级 AI 产品介绍")

    def test_plain_long_task_content_falls_back_to_generic_title(self) -> None:
        content = "从 AI PPT Maker 的产品价值切入，依次说明核心能力、端到端生成流水线、系统架构与工程模块。"

        self.assertEqual(derive_title_from_content(content), DEFAULT_JOB_TITLE)

    def test_rich_saved_plan_title_is_normalized_to_heading(self) -> None:
        rich_title = '<p align="center"><h1 align="center">AI PPT Maker</h1><p>完整任务说明。</p>'

        self.assertEqual(normalize_title_text(rich_title), "AI PPT Maker")

    def test_rich_saved_plan_title_without_heading_is_ignored(self) -> None:
        rich_title = "<p>从产品价值切入，依次说明核心能力、生成流水线、系统架构与工程模块。</p>"

        self.assertEqual(normalize_title_text(rich_title), "")

    def test_resolve_plan_title_prefers_structured_title(self) -> None:
        content = "PPT标题：正文里的标题\n任务内容：更多说明"

        self.assertEqual(resolve_plan_title("结构化标题", fallback_content=content), "结构化标题")


if __name__ == "__main__":
    unittest.main()
