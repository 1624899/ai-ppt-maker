from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from typing import Any


ALLOWED_ALIGNS = {"LEFT", "CENTER", "RIGHT", "JUSTIFY"}
ALLOWED_ANCHORS = {"TOP", "MIDDLE", "BOTTOM"}


@dataclass(frozen=True)
class ScriptParamSpec:
    name: str
    value_kind: str
    required: bool = True
    min_value: float | None = None
    max_value: float | None = None
    min_length: int | None = None
    enum_values: tuple[str, ...] | None = None
    aliases: dict[str, str] | None = None
    item_schema: dict[str, "ScriptParamSpec"] | None = None
    allow_none: bool = False


@dataclass(frozen=True)
class ScriptCallSchema:
    function_name: str
    positional_params: tuple[ScriptParamSpec, ...]
    keyword_params: tuple[ScriptParamSpec, ...]
    content_params: tuple[str, ...] = ()


def normalize_page_script(script: str) -> str:
    normalized_lines: list[str] = []
    for raw_line in _coalesce_script_lines(str(script)):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            normalized_lines.append("")
            continue
        if stripped.startswith("#"):
            normalized_lines.append(stripped)
            continue
        sanitized = _sanitize_script_line(stripped)
        sanitized = normalize_script_call_line(sanitized)
        if sanitized:
            normalized_lines.append(sanitized)
    while normalized_lines and not normalized_lines[-1]:
        normalized_lines.pop()
    return "\n".join(normalized_lines)


def normalize_script_call_line(line: str) -> str:
    node = ast.parse(line, mode="exec")
    if len(node.body) != 1 or not isinstance(node.body[0], ast.Expr):
        raise RuntimeError(f"脚本行不合法：{line}")
    expression = node.body[0].value
    if not isinstance(expression, ast.Call) or not isinstance(expression.func, ast.Name):
        raise RuntimeError(f"脚本调用不合法：{line}")

    function_name = expression.func.id
    schema = CALL_SCHEMAS.get(function_name)
    if schema is None:
        raise RuntimeError(f"脚本调用超出白名单：{function_name}")

    positional_values = _normalize_positional_args(expression, schema, line)
    keyword_values = _normalize_keyword_args(expression, schema, line)
    if not _has_renderable_content(positional_values, keyword_values, schema):
        return ""
    return _render_normalized_call(function_name, positional_values, keyword_values, schema)


def sanitize_script_line(line: str) -> str:
    return _sanitize_script_line(line)


def literal_eval_allowed(node: ast.AST) -> Any:
    return _literal_eval(node)


def _coalesce_script_lines(script: str) -> list[str]:
    result: list[str] = []
    buffer: list[str] = []
    paren_depth = 0

    for raw_line in str(script).splitlines():
        stripped = raw_line.strip()
        if not stripped:
            if not buffer:
                result.append("")
            continue
        if stripped.startswith("#") and not buffer:
            result.append(stripped)
            continue

        buffer.append(stripped)
        paren_depth += stripped.count("(") - stripped.count(")")
        if paren_depth > 0:
            continue

        result.append(" ".join(buffer))
        buffer = []
        paren_depth = 0

    if buffer:
        result.append(" ".join(buffer))
    return result


def _sanitize_script_line(line: str) -> str:
    sanitized = str(line).replace("\\\r", "\\r").replace("\\\n", "\\n")
    if sanitized.count('"') % 2 != 0:
        sanitized = sanitized.replace("\\", "\\\\")
    return sanitized


def _normalize_positional_args(
    expression: ast.Call,
    schema: ScriptCallSchema,
    line: str,
) -> list[Any]:
    required_count = len(schema.positional_params)
    if len(expression.args) < required_count:
        raise RuntimeError(f"脚本参数不足：{line}")
    if len(expression.args) > required_count:
        raise RuntimeError(f"脚本位置参数过多：{line}")

    normalized: list[Any] = []
    for index, (node, spec) in enumerate(zip(expression.args, schema.positional_params, strict=True)):
        value = _literal_eval(node)
        normalized.append(_normalize_value(value, spec, line=line, param_label=f"位置参数 {index + 1}"))
    return normalized


def _normalize_keyword_args(
    expression: ast.Call,
    schema: ScriptCallSchema,
    line: str,
) -> dict[str, Any]:
    allowed_specs = {spec.name: spec for spec in schema.keyword_params}
    normalized: dict[str, Any] = {}

    for keyword in expression.keywords:
        if keyword.arg is None:
            raise RuntimeError(f"不允许使用 **kwargs：{line}")
        spec = allowed_specs.get(keyword.arg)
        if spec is None:
            raise RuntimeError(f"脚本关键词参数超出白名单：{keyword.arg}")
        value = _literal_eval(keyword.value)
        normalized[keyword.arg] = _normalize_value(value, spec, line=line, param_label=f"关键词参数 {keyword.arg}")

    for spec in schema.keyword_params:
        if spec.required and spec.name not in normalized:
            raise RuntimeError(f"缺少必要关键词参数：{spec.name}")
    return normalized


def _normalize_value(value: Any, spec: ScriptParamSpec, *, line: str, param_label: str) -> Any:
    if value is None:
        if spec.allow_none:
            return None
        raise RuntimeError(f"{param_label} 不允许为 null：{line}")

    if spec.value_kind == "slide":
        if value != "slide":
            raise RuntimeError(f"{param_label} 必须是 slide：{line}")
        return "slide"
    if spec.value_kind == "page_texts":
        if value != "page_texts":
            raise RuntimeError(f"{param_label} 必须是 page_texts：{line}")
        return "page_texts"
    if spec.value_kind == "string":
        text = str(value)
        if spec.min_length is not None and len(text) < spec.min_length:
            raise RuntimeError(f"{param_label} 长度不足：{line}")
        return text
    if spec.value_kind == "number":
        number = _coerce_number(value, line=line, param_label=param_label)
        _validate_number_range(number, spec, line=line, param_label=param_label)
        return number
    if spec.value_kind == "bool":
        return _coerce_bool(value, line=line, param_label=param_label)
    if spec.value_kind == "enum":
        return _normalize_enum(value, spec, line=line, param_label=param_label)
    if spec.value_kind == "runs":
        return _normalize_runs(value, spec, line=line, param_label=param_label)
    raise RuntimeError(f"未知参数类型约束：{spec.value_kind}")


def _normalize_runs(value: Any, spec: ScriptParamSpec, *, line: str, param_label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise RuntimeError(f"{param_label} 必须是数组：{line}")
    item_schema = dict(spec.item_schema or {})
    if not item_schema:
        raise RuntimeError("runs 参数缺少 item_schema 定义")

    normalized_runs: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise RuntimeError(f"{param_label} 第 {index} 项必须是对象：{line}")
        allowed_keys = set(item_schema)
        unknown_keys = sorted(set(item) - allowed_keys)
        if unknown_keys:
            joined = ", ".join(unknown_keys)
            raise RuntimeError(f"{param_label} 第 {index} 项包含未知字段：{joined}")
        text_spec = item_schema.get("text")
        if text_spec is None:
            raise RuntimeError("runs 参数缺少 text 字段约束")
        if "text" not in item:
            raise RuntimeError(f"{param_label} 第 {index} 项缺少字段：text")
        normalized_text = _normalize_value(
            item.get("text"),
            text_spec,
            line=line,
            param_label=f"{param_label}.text",
        )
        if not _value_has_renderable_text(normalized_text):
            continue

        normalized_item: dict[str, Any] = {"text": normalized_text}
        for field_name, field_spec in item_schema.items():
            if field_name == "text":
                continue
            if field_name not in item:
                if field_spec.required:
                    raise RuntimeError(f"{param_label} 第 {index} 项缺少字段：{field_name}")
                continue
            normalized_item[field_name] = _normalize_value(
                item[field_name],
                field_spec,
                line=line,
                param_label=f"{param_label}.{field_name}",
            )
        normalized_runs.append(normalized_item)
    return normalized_runs


def _has_renderable_content(
    positional_values: list[Any],
    keyword_values: dict[str, Any],
    schema: ScriptCallSchema,
) -> bool:
    if not schema.content_params:
        return True

    values_by_name = {
        spec.name: value
        for spec, value in zip(schema.positional_params, positional_values, strict=True)
    }
    values_by_name.update(keyword_values)
    return any(_value_has_renderable_text(values_by_name.get(name)) for name in schema.content_params)


def _value_has_renderable_text(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return any(_value_has_renderable_text(item) for item in value)
    if isinstance(value, dict):
        return _value_has_renderable_text(value.get("text"))
    return bool(str(value).strip())


def _coerce_number(value: Any, *, line: str, param_label: str) -> int | float:
    if isinstance(value, bool):
        raise RuntimeError(f"{param_label} 必须是数值：{line}")
    if isinstance(value, (int, float)):
        resolved = value
    else:
        try:
            resolved = float(value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"{param_label} 必须是数值：{line}") from exc
    if isinstance(resolved, float) and resolved.is_integer():
        return int(resolved)
    return resolved


def _validate_number_range(value: int | float, spec: ScriptParamSpec, *, line: str, param_label: str) -> None:
    if spec.min_value is not None and float(value) < float(spec.min_value):
        raise RuntimeError(f"{param_label} 不能小于 {spec.min_value}：{line}")
    if spec.max_value is not None and float(value) > float(spec.max_value):
        raise RuntimeError(f"{param_label} 不能大于 {spec.max_value}：{line}")


def _coerce_bool(value: Any, *, line: str, param_label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    raise RuntimeError(f"{param_label} 必须是布尔值：{line}")


def _normalize_enum(value: Any, spec: ScriptParamSpec, *, line: str, param_label: str) -> str:
    text = str(value).strip()
    alias_map = {key.upper(): val for key, val in dict(spec.aliases or {}).items()}
    normalized = alias_map.get(text.upper(), text.upper())
    allowed = tuple(spec.enum_values or ())
    if normalized not in allowed:
        joined = ", ".join(allowed)
        raise RuntimeError(f"{param_label} 必须是以下值之一：{joined}；当前为 {text}")
    return normalized


def _render_normalized_call(
    function_name: str,
    positional_values: list[Any],
    keyword_values: dict[str, Any],
    schema: ScriptCallSchema,
) -> str:
    rendered_args = [_render_literal(value, bare_name=True) for value in positional_values]
    for spec in schema.keyword_params:
        if spec.name not in keyword_values:
            continue
        rendered_args.append(f"{spec.name}={_render_literal(keyword_values[spec.name])}")
    return f"{function_name}({', '.join(rendered_args)})"


def _render_literal(value: Any, *, bare_name: bool = False) -> str:
    if bare_name and isinstance(value, str) and value in {"slide", "page_texts"}:
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "True" if value else "False"
    if value is None:
        return "None"
    if isinstance(value, list):
        return "[" + ", ".join(_render_literal(item) for item in value) + "]"
    if isinstance(value, tuple):
        inner = ", ".join(_render_literal(item) for item in value)
        if len(value) == 1:
            inner = f"{inner},"
        return f"({inner})"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{_render_literal(key)}: {_render_literal(item)}" for key, item in value.items()) + "}"
    return repr(value)


def _literal_eval(node: ast.AST) -> Any:
    try:
        return _eval_allowed_literal_node(node)
    except Exception as exc:
        raise RuntimeError(f"脚本参数必须是字面量：{ast.dump(node)}") from exc


def _eval_allowed_literal_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        json_literal_map = {
            "true": True,
            "false": False,
            "null": None,
            "slide": "slide",
            "page_texts": "page_texts",
        }
        lowered = node.id.lower()
        if lowered in json_literal_map:
            return json_literal_map[lowered]
        raise ValueError(f"unsupported name literal: {node.id}")
    if isinstance(node, ast.List):
        return [_eval_allowed_literal_node(item) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_eval_allowed_literal_node(item) for item in node.elts)
    if isinstance(node, ast.Set):
        return {_eval_allowed_literal_node(item) for item in node.elts}
    if isinstance(node, ast.Dict):
        if len(node.keys) != len(node.values):
            raise ValueError("dict key/value length mismatch")
        return {
            _eval_allowed_literal_node(key): _eval_allowed_literal_node(value)
            for key, value in zip(node.keys, node.values)
        }
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _eval_allowed_literal_node(node.operand)
        if not isinstance(operand, (int, float, complex)):
            raise ValueError("unary operator only supports numeric literals")
        return +operand if isinstance(node.op, ast.UAdd) else -operand
    raise ValueError(f"unsupported literal node: {type(node).__name__}")


def _build_numeric_param(name: str, *, min_value: float | None = None, max_value: float | None = None) -> ScriptParamSpec:
    return ScriptParamSpec(name=name, value_kind="number", required=False, min_value=min_value, max_value=max_value)


def _build_enum_param(
    name: str,
    *,
    enum_values: tuple[str, ...],
    aliases: dict[str, str] | None = None,
    required: bool = False,
) -> ScriptParamSpec:
    return ScriptParamSpec(
        name=name,
        value_kind="enum",
        required=required,
        enum_values=enum_values,
        aliases=aliases,
    )


RUN_ITEM_SCHEMA: dict[str, ScriptParamSpec] = {
    "text": ScriptParamSpec(name="text", value_kind="string", allow_none=True),
    "size": ScriptParamSpec(name="size", value_kind="number", min_value=1, max_value=400),
    "color": ScriptParamSpec(name="color", value_kind="string", min_length=1, required=False),
    "bold": ScriptParamSpec(name="bold", value_kind="bool", required=False),
    "italic": ScriptParamSpec(name="italic", value_kind="bool", required=False, allow_none=True),
    "font_name": ScriptParamSpec(name="font_name", value_kind="string", min_length=1, required=False),
}


TEXT_KWARGS: tuple[ScriptParamSpec, ...] = (
    _build_numeric_param("size", min_value=1, max_value=400),
    ScriptParamSpec(name="color", value_kind="string", required=False, min_length=1),
    ScriptParamSpec(name="bold", value_kind="bool", required=False),
    _build_enum_param(
        "align",
        enum_values=tuple(sorted(ALLOWED_ALIGNS)),
        aliases={"middle": "CENTER", "centre": "CENTER"},
        required=False,
    ),
    ScriptParamSpec(name="font_name", value_kind="string", required=False, min_length=1),
    _build_enum_param(
        "anchor",
        enum_values=tuple(sorted(ALLOWED_ANCHORS)),
        aliases={"center": "MIDDLE", "mid": "MIDDLE"},
        required=False,
    ),
    ScriptParamSpec(name="italic", value_kind="bool", required=False),
)


CALL_SCHEMAS: dict[str, ScriptCallSchema] = {
    "add_text": ScriptCallSchema(
        function_name="add_text",
        positional_params=(
            ScriptParamSpec(name="slide", value_kind="slide"),
            ScriptParamSpec(name="text", value_kind="string", allow_none=True),
            _build_numeric_param("x", min_value=0),
            _build_numeric_param("y", min_value=0),
            _build_numeric_param("w", min_value=1),
            _build_numeric_param("h", min_value=1),
        ),
        keyword_params=TEXT_KWARGS,
        content_params=("text",),
    ),
    "add_center_text": ScriptCallSchema(
        function_name="add_center_text",
        positional_params=(
            ScriptParamSpec(name="slide", value_kind="slide"),
            ScriptParamSpec(name="text", value_kind="string", allow_none=True),
            _build_numeric_param("x", min_value=0),
            _build_numeric_param("y", min_value=0),
            _build_numeric_param("w", min_value=1),
            _build_numeric_param("h", min_value=1),
        ),
        keyword_params=(
            _build_numeric_param("size", min_value=1, max_value=400),
            ScriptParamSpec(name="color", value_kind="string", required=False, min_length=1),
            ScriptParamSpec(name="bold", value_kind="bool", required=False),
            ScriptParamSpec(name="font_name", value_kind="string", required=False, min_length=1),
            _build_enum_param(
                "anchor",
                enum_values=tuple(sorted(ALLOWED_ANCHORS)),
                aliases={"center": "MIDDLE", "mid": "MIDDLE"},
                required=False,
            ),
            ScriptParamSpec(name="italic", value_kind="bool", required=False),
        ),
        content_params=("text",),
    ),
    "add_runs": ScriptCallSchema(
        function_name="add_runs",
        positional_params=(
            ScriptParamSpec(name="slide", value_kind="slide"),
            ScriptParamSpec(name="runs", value_kind="runs", item_schema=RUN_ITEM_SCHEMA),
            _build_numeric_param("x", min_value=0),
            _build_numeric_param("y", min_value=0),
            _build_numeric_param("w", min_value=1),
            _build_numeric_param("h", min_value=1),
        ),
        keyword_params=(
            _build_enum_param(
                "align",
                enum_values=tuple(sorted(ALLOWED_ALIGNS)),
                aliases={"middle": "CENTER", "centre": "CENTER"},
                required=False,
            ),
            ScriptParamSpec(name="font_name", value_kind="string", required=False, min_length=1),
            _build_enum_param(
                "anchor",
                enum_values=tuple(sorted(ALLOWED_ANCHORS)),
                aliases={"center": "MIDDLE", "mid": "MIDDLE"},
                required=False,
            ),
        ),
        content_params=("runs",),
    ),
    "add_text_ref": ScriptCallSchema(
        function_name="add_text_ref",
        positional_params=(
            ScriptParamSpec(name="slide", value_kind="slide"),
            ScriptParamSpec(name="page_texts", value_kind="page_texts"),
            ScriptParamSpec(name="text_id", value_kind="string", min_length=1),
            _build_numeric_param("x", min_value=0),
            _build_numeric_param("y", min_value=0),
            _build_numeric_param("w", min_value=1),
            _build_numeric_param("h", min_value=1),
        ),
        keyword_params=TEXT_KWARGS,
    ),
    "add_center_text_ref": ScriptCallSchema(
        function_name="add_center_text_ref",
        positional_params=(
            ScriptParamSpec(name="slide", value_kind="slide"),
            ScriptParamSpec(name="page_texts", value_kind="page_texts"),
            ScriptParamSpec(name="text_id", value_kind="string", min_length=1),
            _build_numeric_param("x", min_value=0),
            _build_numeric_param("y", min_value=0),
            _build_numeric_param("w", min_value=1),
            _build_numeric_param("h", min_value=1),
        ),
        keyword_params=(
            _build_numeric_param("size", min_value=1, max_value=400),
            ScriptParamSpec(name="color", value_kind="string", required=False, min_length=1),
            ScriptParamSpec(name="bold", value_kind="bool", required=False),
            ScriptParamSpec(name="font_name", value_kind="string", required=False, min_length=1),
            _build_enum_param(
                "anchor",
                enum_values=tuple(sorted(ALLOWED_ANCHORS)),
                aliases={"center": "MIDDLE", "mid": "MIDDLE"},
                required=False,
            ),
            ScriptParamSpec(name="italic", value_kind="bool", required=False),
        ),
    ),
}
