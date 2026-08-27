from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from typing import Any

from ppt_system.export.text_script_schema import (
    CALL_SCHEMAS,
    KEYWORD_ALIASES,
    normalize_page_script,
    normalize_script_call_line,
)

LOGGER = logging.getLogger(__name__)


# 二轮回看修正时允许模型直接覆盖的文字框字段（规范化后的参数名）。
# 字段集合从调用 Schema 派生，避免新增参数后出现两份白名单。
_EDITABLE_CALL_NAMES = ("add_text", "add_center_text", "add_runs")
_EDITABLE_POSITIONAL_FIELDS = frozenset(
    spec.name
    for call_name in _EDITABLE_CALL_NAMES
    for spec in CALL_SCHEMAS[call_name].positional_params
    if spec.name != "slide"
)
_EDITABLE_KEYWORD_FIELDS = frozenset(
    spec.name
    for call_name in _EDITABLE_CALL_NAMES
    for spec in CALL_SCHEMAS[call_name].keyword_params
)
EDIT_FIELD_NAMES = _EDITABLE_POSITIONAL_FIELDS | _EDITABLE_KEYWORD_FIELDS


@dataclass(frozen=True)
class EditApplicationResult:
    script: str
    accepted_count: int
    changed_count: int


@dataclass(frozen=True)
class TextBoxEntry:
    """脚本中一个可被差分引用的文字框。

    box_no 是模型视角的编号（从 1 开始，只统计白名单调用行）；
    line_index 是规范化脚本中的物理行号，用于回写 edits。
    """

    box_no: int
    line_index: int
    function_name: str
    line: str


def parse_text_box_view(page_script: str) -> list[TextBoxEntry]:
    """把规范化后的文字脚本解析为按顺序编号的文字框列表。

    注释行与空行不参与编号，只保留位置，保证回写 edits 时物理行号稳定。
    """
    canonical = normalize_page_script(page_script)
    entries: list[TextBoxEntry] = []
    box_no = 0
    for line_index, raw_line in enumerate(canonical.splitlines()):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        node = _parse_single_call(stripped)
        if node is None or node.func.id not in CALL_SCHEMAS:
            continue
        box_no += 1
        entries.append(
            TextBoxEntry(
                box_no=box_no,
                line_index=line_index,
                function_name=node.func.id,
                line=stripped,
            )
        )
    return entries


def format_text_box_view(page_script: str) -> str:
    """渲染模型提示词使用的编号文字框清单。"""
    entries = parse_text_box_view(page_script)
    if not entries:
        return "（当前页没有文字框）"
    return "\n".join(f"{entry.box_no}: {entry.line}" for entry in entries)


def apply_page_script_edits(page_script: str, edits: Any) -> str:
    """把模型返回的 edits 应用到当前文字脚本。"""
    return _apply_page_script_edits(page_script, edits).script


def apply_page_script_edits_with_stats(page_script: str, edits: Any) -> EditApplicationResult:
    """应用 edits 并返回合同校验所需的接受数与变更数。"""
    return _apply_page_script_edits(page_script, edits)


def _apply_page_script_edits(page_script: str, edits: Any) -> EditApplicationResult:
    """应用局部文字框修改，支持 update/delete/insert 三种操作。"""
    canonical = normalize_page_script(page_script)
    if edits is None:
        return EditApplicationResult(canonical, 0, 0)
    if not isinstance(edits, list):
        LOGGER.warning("edits 必须是数组，已忽略：%r", edits)
        return EditApplicationResult(canonical, 0, 0)

    entries_by_box = {entry.box_no: entry for entry in parse_text_box_view(canonical)}
    lines = canonical.splitlines()
    accepted_count = 0
    changed_count = 0
    for item in edits:
        if not isinstance(item, dict):
            LOGGER.warning("edits 项必须是对象，已忽略：%r", item)
            continue
        operation = str(item.get("op", "update")).strip().lower()
        if operation == "insert":
            if set(item) != {"op", "call"}:
                LOGGER.warning("insert 操作只允许 op/call 字段：%r", item)
                continue
            inserted = _insert_call(lines, item)
            if inserted:
                accepted_count += 1
                changed_count += 1
            continue

        box_no = _strict_positive_int(item.get("box"))
        entry = entries_by_box.get(box_no) if box_no is not None else None
        if entry is None:
            LOGGER.warning("edits 引用了不存在或非法的文字框编号，已忽略：%r", item)
            continue
        if operation == "delete":
            if set(item) != {"op", "box"}:
                LOGGER.warning("delete 操作只允许 op/box 字段：%r", item)
                continue
            lines[entry.line_index] = ""
            accepted_count += 1
            changed_count += 1
            continue
        if operation != "update":
            LOGGER.warning("不支持的 edits 操作：%s", operation)
            continue

        overrides: dict[str, Any] = {}
        invalid_field = False
        for field, value in item.items():
            if field in {"box", "op"}:
                continue
            canonical_field = KEYWORD_ALIASES.get(field, field)
            if canonical_field not in EDIT_FIELD_NAMES:
                LOGGER.warning("edits 字段不在白名单：%s（box %d）", field, box_no)
                invalid_field = True
                continue
            overrides[canonical_field] = value
        if invalid_field or not overrides:
            continue
        try:
            current_line = lines[entry.line_index]
            rewritten = _rewrite_call_line(current_line, overrides)
        except Exception as exc:
            LOGGER.warning("第 %d 个文字框的 edits 应用失败，保留原行：%s", box_no, exc)
            continue
        accepted_count += 1
        if rewritten != current_line:
            lines[entry.line_index] = rewritten or ""
            changed_count += 1

    script = normalize_page_script("\n".join(lines)) if changed_count else canonical
    return EditApplicationResult(script, accepted_count, changed_count)


def _insert_call(lines: list[str], item: dict[str, Any]) -> bool:
    call = item.get("call")
    if not isinstance(call, str) or not call.strip():
        LOGGER.warning("insert 操作缺少 call：%r", item)
        return False
    try:
        normalized_call = normalize_script_call_line(call.strip())
    except Exception as exc:
        LOGGER.warning("insert 的 call 不合法：%s", exc)
        return False
    node = _parse_single_call(normalized_call)
    if not normalized_call or node is None or node.func.id not in _EDITABLE_CALL_NAMES:
        return False
    lines.append(normalized_call)
    return True


def _parse_single_call(line: str) -> ast.Call | None:
    try:
        node = ast.parse(line, mode="exec")
    except (SyntaxError, ValueError):
        return None
    if len(node.body) != 1 or not isinstance(node.body[0], ast.Expr):
        return None
    expression = node.body[0].value
    if not isinstance(expression, ast.Call) or not isinstance(expression.func, ast.Name):
        return None
    return expression


def _rewrite_call_line(line: str, overrides: dict[str, Any]) -> str | None:
    """按字段覆盖重建一行调用，并走 Schema 规范化，保证改动仍符合白名单。"""
    node = _parse_single_call(line)
    if node is None:
        return None
    schema = CALL_SCHEMAS.get(node.func.id)
    if schema is None:
        return None

    positional_map = {spec.name: index for index, spec in enumerate(schema.positional_params)}
    keyword_specs = {spec.name: spec for spec in schema.keyword_params}
    for field, value in overrides.items():
        if field in positional_map:
            index = positional_map[field]
            args = list(node.args)
            while len(args) <= index:
                args.append(ast.Constant(None))
            args[index] = _literal_node(value)
            node.args = args
            continue
        if field not in keyword_specs:
            raise RuntimeError(f"字段 {field} 不适用于 {node.func.id}")
        keywords = list(node.keywords)
        replaced = False
        for keyword in keywords:
            if keyword.arg == field:
                keyword.value = _literal_node(value)
                replaced = True
                break
        if not replaced:
            keywords.append(ast.keyword(arg=field, value=_literal_node(value)))
        node.keywords = keywords
    return normalize_script_call_line(ast.unparse(node))


def _literal_node(value: Any) -> ast.AST:
    """把模型返回的 JSON 值转成 AST 字面量节点。"""
    if isinstance(value, bool):
        return ast.Constant(value)
    if value is None:
        return ast.Constant(None)
    if isinstance(value, (int, float)):
        return ast.Constant(value)
    if isinstance(value, str):
        return ast.Constant(value)
    if isinstance(value, list):
        return ast.List(elts=[_literal_node(item) for item in value])
    if isinstance(value, dict):
        return ast.Dict(
            keys=[ast.Constant(str(key)) for key in value],
            values=[_literal_node(item) for item in value.values()],
        )
    raise ValueError(f"edits 不支持的值类型：{type(value).__name__}")


def _strict_positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value