from __future__ import annotations

import ast
import json
import logging
from dataclasses import dataclass
from typing import Any, Sequence


LOGGER = logging.getLogger(__name__)


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
    example: Any | None = None


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
        canonical_name = KEYWORD_ALIASES.get(keyword.arg, keyword.arg)
        spec = allowed_specs.get(canonical_name)
        if spec is None:
            # 未知关键词参数优先丢弃并留痕，避免模型多写的风格参数报废整页脚本。
            LOGGER.warning(
                "关键词参数不在白名单，已丢弃：%s（函数 %s）",
                keyword.arg,
                schema.function_name,
            )
            continue
        if canonical_name != keyword.arg:
            # 常见写法差异按别名归一化到规范参数名，等价于正常处理。
            LOGGER.info(
                "关键词参数已按别名归一化：%s -> %s（函数 %s）",
                keyword.arg,
                canonical_name,
                schema.function_name,
            )
        value = _literal_eval(keyword.value)
        normalized[canonical_name] = _normalize_value(
            value,
            spec,
            line=line,
            param_label=f"关键词参数 {canonical_name}",
        )

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
        # 字段名做别名归一化，未知字段优先丢弃并留痕，与关键词参数策略一致。
        canonical_item: dict[str, Any] = {}
        for field_name, field_value in item.items():
            canonical_name = KEYWORD_ALIASES.get(field_name, field_name)
            if canonical_name not in item_schema:
                LOGGER.warning(
                    "runs 字段不在白名单，已丢弃：%s（%s 第 %d 项）",
                    field_name,
                    param_label,
                    index,
                )
                continue
            canonical_item[canonical_name] = field_value
        text_spec = item_schema.get("text")
        if text_spec is None:
            raise RuntimeError("runs 参数缺少 text 字段约束")
        if "text" not in canonical_item:
            raise RuntimeError(f"{param_label} 第 {index} 项缺少字段：text")
        normalized_text = _normalize_value(
            canonical_item.get("text"),
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
            if field_name not in canonical_item:
                if field_spec.required:
                    raise RuntimeError(f"{param_label} 第 {index} 项缺少字段：{field_name}")
                continue
            normalized_item[field_name] = _normalize_value(
                canonical_item[field_name],
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


def _build_numeric_param(
    name: str,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
    example: Any | None = None,
) -> ScriptParamSpec:
    return ScriptParamSpec(
        name=name,
        value_kind="number",
        required=False,
        min_value=min_value,
        max_value=max_value,
        example=example,
    )


def _build_enum_param(
    name: str,
    *,
    enum_values: tuple[str, ...],
    aliases: dict[str, str] | None = None,
    required: bool = False,
    example: str | None = None,
) -> ScriptParamSpec:
    return ScriptParamSpec(
        name=name,
        value_kind="enum",
        required=required,
        enum_values=enum_values,
        aliases=aliases,
        example=example,
    )


# 关键词参数名别名：把模型常见的写法差异归一化到规范参数名，而不是丢弃。
# 命中别名的参数按规范名校验与渲染；完全不在白名单的参数才丢弃并记录警告。
KEYWORD_ALIASES: dict[str, str] = {
    "font": "font_name",
    "font_family": "font_name",
    "font_size": "size",
    "font_color": "color",
}


RUN_ITEM_SCHEMA: dict[str, ScriptParamSpec] = {
    "text": ScriptParamSpec(name="text", value_kind="string", allow_none=True),
    "size": ScriptParamSpec(name="size", value_kind="number", min_value=1, max_value=400, example=18),
    "color": ScriptParamSpec(name="color", value_kind="string", min_length=1, required=False, example="163A63"),
    "bold": ScriptParamSpec(name="bold", value_kind="bool", required=False, example=False),
    "italic": ScriptParamSpec(name="italic", value_kind="bool", required=False, allow_none=True, example=False),
    "font_name": ScriptParamSpec(name="font_name", value_kind="string", min_length=1, required=False, example="Microsoft YaHei"),
}


TEXT_KWARGS: tuple[ScriptParamSpec, ...] = (
    _build_numeric_param("size", min_value=1, max_value=400, example=12),
    ScriptParamSpec(name="color", value_kind="string", required=False, min_length=1, example="163A63"),
    ScriptParamSpec(name="bold", value_kind="bool", required=False, example=False),
    _build_enum_param(
        "align",
        enum_values=tuple(sorted(ALLOWED_ALIGNS)),
        aliases={"middle": "CENTER", "centre": "CENTER"},
        required=False,
        example="LEFT",
    ),
    ScriptParamSpec(name="font_name", value_kind="string", required=False, min_length=1, example="Microsoft YaHei"),
    _build_enum_param(
        "anchor",
        enum_values=tuple(sorted(ALLOWED_ANCHORS)),
        aliases={"center": "MIDDLE", "mid": "MIDDLE"},
        required=False,
        example="TOP",
    ),
    ScriptParamSpec(name="italic", value_kind="bool", required=False, example=False),
)


# 居中文本与居中文本引用共享的关键词参数，字段集一致，避免两处重复定义。
CENTER_TEXT_KWARGS: tuple[ScriptParamSpec, ...] = (
    _build_numeric_param("size", min_value=1, max_value=400, example=12),
    ScriptParamSpec(name="color", value_kind="string", required=False, min_length=1, example="163A63"),
    ScriptParamSpec(name="bold", value_kind="bool", required=False, example=False),
    ScriptParamSpec(name="font_name", value_kind="string", required=False, min_length=1, example="Microsoft YaHei"),
    _build_enum_param(
        "anchor",
        enum_values=tuple(sorted(ALLOWED_ANCHORS)),
        aliases={"center": "MIDDLE", "mid": "MIDDLE"},
        required=False,
        example="TOP",
    ),
    ScriptParamSpec(name="italic", value_kind="bool", required=False, example=False),
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
        keyword_params=CENTER_TEXT_KWARGS,
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
                example="LEFT",
            ),
            ScriptParamSpec(name="font_name", value_kind="string", required=False, min_length=1, example="Microsoft YaHei"),
            _build_enum_param(
                "anchor",
                enum_values=tuple(sorted(ALLOWED_ANCHORS)),
                aliases={"center": "MIDDLE", "mid": "MIDDLE"},
                required=False,
                example="TOP",
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
        keyword_params=CENTER_TEXT_KWARGS,
    ),
}


def build_allowed_calls_doc(
    function_names: Sequence[str],
    *,
    excluded_names: Sequence[str] = (),
) -> str:
    """由 CALL_SCHEMAS 渲染“允许的调用”说明，供生成提示词引用。

    提示词依赖此函数而不是手写签名，保证生成侧规则与后端白名单始终一致。
    """
    names = tuple(function_names)
    if not names:
        raise ValueError("至少需要一个允许调用的函数名")
    for name in names:
        if name not in CALL_SCHEMAS:
            raise ValueError(f"未知函数名：{name}")

    lines: list[str] = []
    excluded = tuple(excluded_names)
    if excluded:
        lines.append(f"允许的调用只有 {'/'.join(names)}，不要使用 {'/'.join(excluded)}。")
    else:
        lines.append(f"允许的调用只有 {'/'.join(names)}。")
    lines.append("参数名必须使用白名单中的规范书写，不允许写成别名或自创写法；多余参数会被丢弃。")

    for name in names:
        schema = CALL_SCHEMAS[name]
        positional_parts = [_render_positional_example(spec) for spec in schema.positional_params]
        keyword_parts = [f"{spec.name}={_render_keyword_example(spec)}" for spec in schema.keyword_params]
        signature = f"{name}({', '.join(positional_parts)}"
        if keyword_parts:
            signature = f"{signature}, {', '.join(keyword_parts)}"
        lines.append(f"{signature})")
        if schema.keyword_params:
            descriptions = "、".join(f"{spec.name}（{_describe_spec(spec)}）" for spec in schema.keyword_params)
            lines.append(f"  {name} 关键词参数：{descriptions}")
        for spec in schema.positional_params:
            if spec.value_kind == "runs" and spec.item_schema:
                item_descriptions = "、".join(
                    f"{field_name}（{_describe_spec(field_spec)}）"
                    for field_name, field_spec in spec.item_schema.items()
                )
                lines.append(f"  runs 每项字段：{item_descriptions}")
    return "\n".join(lines)


def _describe_spec(spec: ScriptParamSpec) -> str:
    required_suffix = "，必填" if spec.required else ""
    if spec.value_kind == "number":
        if spec.min_value is not None or spec.max_value is not None:
            lower = spec.min_value if spec.min_value is not None else "不限"
            upper = spec.max_value if spec.max_value is not None else "不限"
            return f"数值{lower}-{upper}{required_suffix}"
        return f"数值{required_suffix}"
    if spec.value_kind == "bool":
        return f"布尔{required_suffix}"
    if spec.value_kind == "enum":
        values = "/".join(spec.enum_values or ())
        return f"枚举{values}{required_suffix}"
    if spec.value_kind == "string":
        return f"字符串{required_suffix}"
    return f"{spec.value_kind}{required_suffix}"


_STRING_EXAMPLES: dict[str, str] = {
    "text": '"文字"',
    "color": '"163A63"',
    "font_name": '"Microsoft YaHei"',
}


def _render_keyword_example(spec: ScriptParamSpec) -> str:
    if spec.example is not None:
        return _render_literal(spec.example)
    if spec.value_kind == "number":
        return str(_example_number(spec))
    if spec.value_kind == "bool":
        return "False"
    if spec.value_kind == "enum":
        return repr(spec.enum_values[0])
    if spec.value_kind == "string":
        return _STRING_EXAMPLES.get(spec.name, '"示例"')
    return spec.value_kind


def _example_number(spec: ScriptParamSpec) -> int:
    min_value = spec.min_value if spec.min_value is not None else 0
    max_value = spec.max_value if spec.max_value is not None else 12
    return int(max(min_value, min(12, max_value)))


def _render_positional_example(spec: ScriptParamSpec) -> str:
    if spec.value_kind in {"slide", "page_texts"}:
        return spec.value_kind
    if spec.value_kind == "string":
        return '"文字"'
    if spec.value_kind == "runs":
        return '[{"text": "前半句", "size": 12}]'
    return spec.name
