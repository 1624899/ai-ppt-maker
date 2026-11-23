from __future__ import annotations

import json
import re
from pathlib import Path
from xml.etree import ElementTree


ICON_ROOT = Path(__file__).resolve().parents[2] / "assets" / "icons" / "lucide"


def _match_score(name: str, terms: list[str], alternatives: list[str]) -> int:
    score = 0
    for word in alternatives:
        if word == name:
            return 3
        if word in terms:
            score = max(score, 2)
        elif any(word in term for term in terms):
            score = max(score, 1)
    return score


def search_icons(query: str = "", limit: int = 8) -> dict:
    if not 1 <= limit <= 50:
        raise ValueError("图标检索数量必须在 1 到 50 之间。")
    catalog = json.loads((ICON_ROOT / "catalog.json").read_text(encoding="utf-8"))
    result = {"library": "lucide", "version": catalog["version"], "total": len(catalog["icons"])}
    if not query.strip():
        return result
    aliases = json.loads((ICON_ROOT.parent / "aliases.zh.json").read_text(encoding="utf-8"))
    # 每个检索词都需匹配，同一中文词的英文近义词按任一匹配。
    groups = [aliases.get(term, [term]) for term in query.casefold().split()]
    matches = []
    for icon in catalog["icons"]:
        name = icon["name"]
        terms = [name, *name.split("-"), *icon["tags"]]
        scores = [_match_score(name, terms, group) for group in groups]
        if all(scores):
            matches.append((sum(scores), name))
    matches.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
    return {
        **result,
        "query": query,
        "matched": len(matches),
        "icons": [{"name": name, "svg": str(ICON_ROOT / f"{name}.svg")} for _, name in matches[:limit]],
    }


def export_icon(name: str, output: Path, color: str = "#111111", size: int = 256) -> dict:
    catalog = json.loads((ICON_ROOT / "catalog.json").read_text(encoding="utf-8"))
    if name not in {icon["name"] for icon in catalog["icons"]}:
        raise ValueError(f"本地图标不存在：{name}，请先通过 icons --query 检索。")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("图标颜色必须是 #RRGGBB 格式。")
    if not 1 <= size <= 4096:
        raise ValueError("图标尺寸必须在 1 到 4096 像素之间。")
    output = output.resolve()
    if output.suffix.lower() != ".svg":
        raise ValueError("图标导出文件必须使用 .svg 扩展名。")
    if output.is_relative_to(ICON_ROOT.parents[2]):
        raise ValueError("请将导出图标保存到 Skill 目录之外的工作目录。")
    source = (ICON_ROOT / f"{name}.svg").read_text(encoding="utf-8")
    svg = ElementTree.fromstring(source)
    svg.set("width", str(size))
    svg.set("height", str(size))
    svg.set("stroke", color.upper())
    # 将随包许可嵌入导出文件，独立转交素材时仍保留完整声明。
    namespace = "http://www.w3.org/2000/svg"
    ElementTree.register_namespace("", namespace)
    metadata = ElementTree.SubElement(svg, f"{{{namespace}}}metadata")
    metadata.text = (ICON_ROOT / "LICENSE").read_text(encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(ElementTree.tostring(svg, encoding="unicode") + "\n", encoding="utf-8")
    return {"name": name, "svg": str(output), "color": color.upper(), "size": size}
