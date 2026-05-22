from __future__ import annotations

from typing import Any


STYLE_GUIDE = {
    "商务汇报": "高端 toB 商业汇报风格，深色背景，蓝白科技线稿，结构清晰，适合企业战略与业务增长主题。",
    "科技蓝图": "科技蓝图风格，深色透明画布，蓝白霓虹线条，抽象系统架构、数据流和模块化界面元素。",
    "视觉展示": "高级视觉展示风格，空间层次明确，元素轻量、半透明、边界清晰，适合图片与概念混排。",
    "通用简报": "现代中文简报风格，克制、清晰、专业，蓝白线条和低透明图形元素。",
}


def build_page_prompt(page: dict[str, Any], style_type: str, image_width: int, image_height: int) -> str:
    style = STYLE_GUIDE.get(style_type, STYLE_GUIDE["通用简报"])
    title = page.get("title", f"第 {page.get('page_no', '')} 页")
    summary = page.get("summary", "")

    return "\n".join(
        [
            f"请生成一张 {image_width}x{image_height} 的 PPT 页面视觉样式图。",
            f"页面主题：{title}",
            f"内容摘要：{summary}",
            f"整体风格：{style}",
            "硬性要求：不要生成任何文字、数字、字母、水印或 logo；所有文字区域必须留空。",
            "硬性要求：输出透明背景 PNG；若不能透明，则使用纯黑背景且主体元素边界清晰。",
            "硬性要求：元素之间保留透明间隔，避免互相粘连，方便后续自动分割。",
            "硬性要求：视觉元素低透明、边界清晰、线条锐利、噪点少。",
            "构图建议：左侧预留 45% 宽度作为可编辑文字区域，右侧和边缘放置装饰图形、流程框、图标、线条和抽象结构。",
        ]
    )


def build_image_prompts(project: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    image_width = int(project.get("image_width", 2000))
    image_height = int(project.get("image_height", 1125))
    style_type = str(plan.get("style_type", "通用简报"))
    prompts: list[dict[str, Any]] = []

    for page in project["pages"]:
        prompts.append(
            {
                "page_no": int(page["page_no"]),
                "prompt": build_page_prompt(page, style_type, image_width, image_height),
            }
        )

    return prompts

