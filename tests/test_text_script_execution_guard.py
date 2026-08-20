"""文字脚本执行边界的安全回归测试。

生成脚本最终由 worker 子进程动态执行；如果未规范化的模型脚本引用了
执行环境之外的名称（例如 pages），会在运行时报出晦涩的
NameError: name 'pages' is not defined。

本测试锁定 build_project_script_source 作为唯一装配枢纽的职责：
任何来源（生成、断点缓存、bundle 重建）的脚本进入 worker 前都必须
通过白名单规范化，非法脚本在装配时即以清晰的中文错误被拒绝。
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ppt_system.export.text_script_runtime import build_project_script_source


def _build_project(page_count: int = 1) -> dict:
    return {
        "image_width": 2000,
        "image_height": 1125,
        "slide_width_inch": 13.333333,
        "default_font": {"font_name": "Microsoft YaHei", "color": "14254E"},
        "pages": [
            {"page_no": index + 1, "title": f"第 {index + 1} 页", "summary": "", "texts": [], "bullets": []}
            for index in range(page_count)
        ],
    }


class TextScriptExecutionGuardTests(unittest.TestCase):
    def test_rejects_script_referencing_undefined_pages(self) -> None:
        """引用未定义名称 pages 的脚本应在装配时被拒绝，而不是等到 worker 运行时抛 NameError。"""
        with TemporaryDirectory() as directory:
            project = _build_project()
            page_scripts = [
                {
                    "page_no": 1,
                    "script": 'for page in pages:\n    add_text(slide, page["title"], 1, 2, 3, 4)',
                    "asset_adjustments": {},
                }
            ]
            with self.assertRaises(RuntimeError) as context:
                build_project_script_source(
                    project,
                    Path(directory),
                    Path(directory) / "result.pptx",
                    page_scripts,
                    include_assets=False,
                )
            self.assertIn("第 1 页文字脚本不合法", str(context.exception))

    def test_rejects_subscript_access_on_pages(self) -> None:
        """以 pages[...] 形式引用未定义名称同样被白名单拦截。"""
        with TemporaryDirectory() as directory:
            project = _build_project()
            page_scripts = [
                {
                    "page_no": 1,
                    "script": 'add_text(slide, pages[0]["title"], 1, 2, 3, 4)',
                    "asset_adjustments": {},
                }
            ]
            with self.assertRaises(RuntimeError):
                build_project_script_source(
                    project,
                    Path(directory),
                    Path(directory) / "result.pptx",
                    page_scripts,
                    include_assets=False,
                )

    def test_allows_whitelisted_script_unchanged(self) -> None:
        """白名单内的脚本装配后仍保持原语义，且生成源码可被 ast 正常解析。"""
        with TemporaryDirectory() as directory:
            project = _build_project()
            page_scripts = [
                {
                    "page_no": 1,
                    "script": 'add_text(slide, "标题", 100, 100, 800, 80, size=32, bold=True)',
                    "asset_adjustments": {},
                }
            ]
            source = build_project_script_source(
                project,
                Path(directory),
                Path(directory) / "result.pptx",
                page_scripts,
                include_assets=False,
            )
            ast.parse(source)
            self.assertIn("add_text(slide, \"标题\", 100, 100, 800, 80, size=32, bold=True)", source)
            self.assertIn("def build_slide_01(slide)", source)

    def test_keeps_pass_placeholder_as_noop(self) -> None:
        """pass 占位脚本与空脚本按既有语义退化为无操作，不应被拒绝。"""
        with TemporaryDirectory() as directory:
            project = _build_project()
            for script in ("pass", ""):
                source = build_project_script_source(
                    project,
                    Path(directory),
                    Path(directory) / "result.pptx",
                    [{"page_no": 1, "script": script, "asset_adjustments": {}}],
                    include_assets=False,
                )
                ast.parse(source)
                self.assertIn("page_texts = PAGE_TEXTS[1]", source)

    def test_rejects_unlisted_call_anywhere_in_script(self) -> None:
        """脚本中出现白名单之外的调用同样在装配时被拒绝。"""
        with TemporaryDirectory() as directory:
            project = _build_project()
            page_scripts = [
                {
                    "page_no": 1,
                    "script": 'add_text(slide, "标题", 100, 100, 800, 80, size=32, bold=True)\nlen(pages)',
                    "asset_adjustments": {},
                }
            ]
            with self.assertRaises(RuntimeError) as context:
                build_project_script_source(
                    project,
                    Path(directory),
                    Path(directory) / "result.pptx",
                    page_scripts,
                    include_assets=False,
                )
            self.assertIn("第 1 页文字脚本不合法", str(context.exception))


if __name__ == "__main__":
    unittest.main()
