from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


ICON_ARCHIVE = Path(__file__).resolve().parents[1] / "assets" / "lucide-icons.zip"


@lru_cache(maxsize=1)
def _catalog() -> dict:
    with ZipFile(ICON_ARCHIVE) as archive:
        return json.loads(archive.read("lucide/catalog.json").decode("utf-8"))


@lru_cache(maxsize=1)
def _aliases() -> dict:
    with ZipFile(ICON_ARCHIVE) as archive:
        return json.loads(archive.read("aliases.zh.json").decode("utf-8"))


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


def search_icons(query: str, limit: int = 8) -> list[str]:
    """复用 Skill 的中英文检索规则，返回本地图标名称。"""
    if not 1 <= limit <= 50:
        raise ValueError("图标检索数量必须在 1 到 50 之间。")
    groups = [_aliases().get(term, [term]) for term in query.casefold().split()]
    if not groups:
        return []
    matches = []
    for icon in _catalog()["icons"]:
        name = icon["name"]
        terms = [name, *name.split("-"), *icon["tags"]]
        scores = [_match_score(name, terms, group) for group in groups]
        if all(scores):
            matches.append((sum(scores), name))
    matches.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
    return [name for _, name in matches[:limit]]


def render_icon(name: str, output: Path, *, color: str, size: int) -> None:
    """将离线 SVG 渲染为透明 PNG，并保留源素材及许可。"""
    if name not in {icon["name"] for icon in _catalog()["icons"]}:
        raise ValueError(f"本地图标不存在：{name}")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("图标颜色必须是 #RRGGBB 格式。")
    if not 1 <= size <= 4096:
        raise ValueError("图标尺寸必须在 1 到 4096 像素之间。")
    from resvg_py import svg_to_bytes

    with ZipFile(ICON_ARCHIVE) as archive:
        svg = ElementTree.fromstring(archive.read(f"lucide/{name}.svg"))
        license_text = archive.read("lucide/LICENSE").decode("utf-8")
    svg.set("stroke", color.upper())
    namespace = "http://www.w3.org/2000/svg"
    ElementTree.register_namespace("", namespace)
    ElementTree.SubElement(svg, f"{{{namespace}}}metadata").text = license_text
    source = ElementTree.tostring(svg, encoding="unicode")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".svg").write_text(source + "\n", encoding="utf-8")
    output.write_bytes(svg_to_bytes(svg_string=source, width=size, height=size, skip_system_fonts=True))
    (output.parent / "icons.LICENSE.txt").write_text(license_text, encoding="utf-8")
