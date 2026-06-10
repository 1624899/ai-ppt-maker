from __future__ import annotations


def build_content_planning_constraints(source_anchor_count: int, page_count: int) -> str:
    lines = [
        "- 先按目标页数设计整套叙事结构，不按输入章节号、源文页号或锚点顺序做一一映射。",
        "- 每页必须有明确且唯一的内容职责，title、summary、bullets 必须讲同一个主题。",
        "- 同一标题或同一核心主题不能重复占用多个页面；除非页面角色明显不同，并在标题中标明“总览/案例/对比/影响/处理/总结”等差异。",
        "- 总览页必须使用上位标题，例如“框架、总览、原则概览、路径概览”，不能占用后续单个子主题标题。",
    ]
    if source_anchor_count > 0:
        lines.append(
            "- source_anchor_ids 必须写明每页承载的事实锚点；一页可以承载多个相关锚点，但不能新增锚点外事实。"
        )
    if source_anchor_count > page_count > 0:
        lines.append(
            f"- 源文事实锚点数为 {source_anchor_count}，多于目标 {page_count} 页：必须合并相邻或同类主题，覆盖全文的开头、中段和结尾，不能只截取前 {page_count} 个锚点。"
        )
    return "\n".join(lines)
