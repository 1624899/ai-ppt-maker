from __future__ import annotations

import pytest

from ppt_system.export.text_script_schema import (
    CALL_SCHEMAS,
    KEYWORD_ALIASES,
    build_allowed_calls_doc,
    normalize_page_script,
    normalize_script_call_line,
)


def test_alias_font_normalized_to_font_name() -> None:
    script = 'add_text(slide, "标题", 0, 0, 100, 40, font="Microsoft YaHei")'
    normalized = normalize_page_script(script)
    assert normalized == 'add_text(slide, "标题", 0, 0, 100, 40, font_name="Microsoft YaHei")'


def test_alias_font_family_normalized_to_font_name() -> None:
    script = 'add_text(slide, "标题", 0, 0, 100, 40, font_family="SimSun")'
    assert normalize_page_script(script) == 'add_text(slide, "标题", 0, 0, 100, 40, font_name="SimSun")'


def test_alias_font_size_normalized_to_size() -> None:
    script = 'add_text(slide, "标题", 0, 0, 100, 40, font_size=18)'
    assert normalize_page_script(script) == 'add_text(slide, "标题", 0, 0, 100, 40, size=18)'


def test_alias_font_color_normalized_to_color() -> None:
    script = 'add_text(slide, "标题", 0, 0, 100, 40, font_color="355C7D")'
    assert normalize_page_script(script) == 'add_text(slide, "标题", 0, 0, 100, 40, color="355C7D")'


def test_unknown_keyword_dropped() -> None:
    script = 'add_text(slide, "标题", 0, 0, 100, 40, stroke="red")'
    assert normalize_page_script(script) == 'add_text(slide, "标题", 0, 0, 100, 40)'


def test_alias_and_canonical_coexist_last_wins() -> None:
    script = 'add_text(slide, "标题", 0, 0, 100, 40, font="Arial", font_name="微软雅黑")'
    assert normalize_page_script(script) == 'add_text(slide, "标题", 0, 0, 100, 40, font_name="微软雅黑")'


def test_center_text_align_not_in_schema_is_dropped() -> None:
    script = 'add_center_text(slide, "标题", 0, 0, 100, 40, align="LEFT")'
    assert normalize_page_script(script) == 'add_center_text(slide, "标题", 0, 0, 100, 40)'


def test_runs_font_field_normalized() -> None:
    script = 'add_runs(slide, [{"text": "A", "font": "微软雅黑", "size": 18}], 0, 0, 100, 40)'
    normalized = normalize_page_script(script)
    assert normalized == 'add_runs(slide, [{"text": "A", "size": 18, "font_name": "微软雅黑"}], 0, 0, 100, 40)'


def test_runs_unknown_field_dropped() -> None:
    script = 'add_runs(slide, [{"text": "A", "size": 18, "stroke": "red"}], 0, 0, 100, 40)'
    assert normalize_page_script(script) == 'add_runs(slide, [{"text": "A", "size": 18}], 0, 0, 100, 40)'


def test_runs_unknown_field_does_not_break_other_items() -> None:
    script = (
        'add_runs(slide, [{"text": "A", "font": "Arial", "size": 18}, '
        '{"text": "B", "size": 16, "stroke": "red"}], 0, 0, 100, 40)'
    )
    normalized = normalize_page_script(script)
    assert normalized == 'add_runs(slide, [{"text": "A", "size": 18, "font_name": "Arial"}, {"text": "B", "size": 16}], 0, 0, 100, 40)'


def test_normalization_is_idempotent() -> None:
    script = 'add_text(slide, "标题", 0, 0, 100, 40, font="Arial", stroke="red")'
    once = normalize_page_script(script)
    twice = normalize_page_script(once)
    assert twice == once


def test_invalid_value_still_rejected() -> None:
    script = 'add_text(slide, "标题", 0, 0, 100, 40, size=5000)'
    with pytest.raises(RuntimeError):
        normalize_page_script(script)


def test_invalid_enum_still_rejected() -> None:
    script = 'add_text(slide, "标题", 0, 0, 100, 40, align="DIAGONAL")'
    with pytest.raises(RuntimeError):
        normalize_page_script(script)


def test_unknown_function_still_rejected() -> None:
    script = 'add_sticker(slide, "标题", 0, 0, 100, 40)'
    with pytest.raises(RuntimeError):
        normalize_page_script(script)


def test_too_many_positional_args_still_rejected() -> None:
    script = 'add_text(slide, "标题", 0, 0, 100, 40, 1, 2)'
    with pytest.raises(RuntimeError):
        normalize_page_script(script)


def test_tuple_unpacking_still_rejected() -> None:
    script = 'add_text(slide, "标题", 0, 0, 100, 40, **{"size": 20})'
    with pytest.raises(RuntimeError):
        normalize_page_script(script)


def test_dropped_keyword_logs_warning(caplog) -> None:
    with caplog.at_level("WARNING", logger="ppt_system.export.text_script_schema"):
        script = 'add_text(slide, "标题", 0, 0, 100, 40, stroke="red")'
        normalize_page_script(script)
    dropped = [record for record in caplog.records if "关键词参数不在白名单" in record.getMessage()]
    assert dropped
    assert "stroke" in dropped[0].getMessage()


def test_alias_normalization_logs_info(caplog) -> None:
    with caplog.at_level("INFO", logger="ppt_system.export.text_script_schema"):
        script = 'add_text(slide, "标题", 0, 0, 100, 40, font="Arial")'
        normalize_page_script(script)
    messages = [record.getMessage() for record in caplog.records if "关键词参数已按别名归一化" in record.getMessage()]
    assert messages
    assert "font -> font_name" in messages[0]


def test_runs_unknown_field_logs_warning(caplog) -> None:
    with caplog.at_level("WARNING", logger="ppt_system.export.text_script_schema"):
        script = 'add_runs(slide, [{"text": "A", "size": 18, "stroke": "red"}], 0, 0, 100, 40)'
        normalize_page_script(script)
    dropped = [record for record in caplog.records if "runs 字段不在白名单" in record.getMessage()]
    assert dropped
    assert "stroke" in dropped[0].getMessage()


def test_keyword_aliases_are_directional() -> None:
    # 别名必须指向规范参数名，不能指向另一个别名，避免归一化链失效。
    values = set(KEYWORD_ALIASES.values())
    assert values.isdisjoint(KEYWORD_ALIASES)


def test_single_line_normalize_reuses_same_policies() -> None:
    line = 'add_text(slide, "标题", 0, 0, 100, 40, font="Arial")'
    assert normalize_script_call_line(line) == 'add_text(slide, "标题", 0, 0, 100, 40, font_name="Arial")'


def test_allowed_calls_doc_contains_every_function() -> None:
    doc = build_allowed_calls_doc(
        ("add_text", "add_center_text", "add_runs"),
        excluded_names=("add_text_ref", "add_center_text_ref"),
    )
    for name in ("add_text", "add_center_text", "add_runs"):
        assert f"{name}(" in doc
    assert "不要使用 add_text_ref/add_center_text_ref" in doc


def test_allowed_calls_doc_lists_keyword_whitelist() -> None:
    doc = build_allowed_calls_doc(("add_text",))
    for spec in CALL_SCHEMAS["add_text"].keyword_params:
        assert f"{spec.name}=" in doc
        assert spec.name in doc.splitlines()[2]
    assert "CENTER" in doc and "JUSTIFY" in doc and "LEFT" in doc and "RIGHT" in doc
    assert "BOTTOM" in doc and "MIDDLE" in doc and "TOP" in doc


def test_allowed_calls_doc_center_text_excludes_align() -> None:
    doc = build_allowed_calls_doc(("add_center_text",))
    assert "align=" not in doc
    assert "MIDDLE" in doc


def test_allowed_calls_doc_describes_runs_item_fields() -> None:
    doc = build_allowed_calls_doc(("add_runs",))
    assert "runs 每项字段" in doc
    assert "text（字符串，必填）" in doc
    assert "size（数值1-400，必填）" in doc
    assert "font_name（字符串）" in doc


def test_allowed_calls_doc_matches_schema_keyword_names() -> None:
    # 渲染结果与 CALL_SCHEMAS 一致，是“单一事实来源”的回归防线。
    for name in ("add_text", "add_center_text", "add_runs"):
        doc = build_allowed_calls_doc((name,))
        keyword_section = next(line for line in doc.splitlines() if "关键词参数" in line)
        for spec in CALL_SCHEMAS[name].keyword_params:
            assert spec.name in keyword_section


def test_allowed_calls_doc_rejects_unknown_function() -> None:
    with pytest.raises(ValueError):
        build_allowed_calls_doc(("add_sticker",))


def test_allowed_calls_doc_requires_at_least_one_function() -> None:
    with pytest.raises(ValueError):
        build_allowed_calls_doc(())


def test_allowed_calls_doc_is_stable_across_calls() -> None:
    first = build_allowed_calls_doc(("add_text",))
    second = build_allowed_calls_doc(("add_text",))
    assert first == second