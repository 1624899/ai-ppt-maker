"""结构化、可编辑的 PowerPoint 图表数据与导出辅助。"""
from __future__ import annotations

from math import isfinite
from typing import Any

from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE

CHART_TYPES = {
    "bar": XL_CHART_TYPE.BAR_CLUSTERED,
    "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "line": XL_CHART_TYPE.LINE_MARKERS,
    "pie": XL_CHART_TYPE.PIE,
    "doughnut": XL_CHART_TYPE.DOUGHNUT,
    "area": XL_CHART_TYPE.AREA,
}
PART_TO_WHOLE_TYPES = {"pie", "doughnut"}


def normalize_chart_data(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("图表必须是对象。")
    chart_type = value.get("type")
    if not isinstance(chart_type, str) or chart_type not in CHART_TYPES:
        raise ValueError(f"不支持的图表类型：{chart_type}")
    categories = value.get("categories")
    if not isinstance(categories, list) or not categories or any(
        not isinstance(item, str) or not item.strip() for item in categories
    ):
        raise ValueError("图表需要非空的分类名称数组。")
    raw_series = value.get("series")
    if not isinstance(raw_series, list) or not raw_series:
        raise ValueError("图表至少需要一个数据系列。")
    if chart_type in PART_TO_WHOLE_TYPES and len(raw_series) != 1:
        raise ValueError("饼图和环图需要一个数据系列。")
    if value.get("show_percentage") and chart_type not in PART_TO_WHOLE_TYPES:
        raise ValueError("占比标签适用于饼图和环图。比例数值可使用 0% 数字格式。")
    series = []
    for raw in raw_series:
        if not isinstance(raw, dict) or not isinstance(raw.get("values"), list):
            raise ValueError("每个图表系列需要一个数值数组。")
        values = raw["values"]
        if len(values) != len(categories):
            raise ValueError("图表分类数量必须与数据数量一致。")
        if any(type(item) not in (int, float) or not isfinite(item) for item in values):
            raise ValueError("图表数据必须全部是有限数字。")
        if chart_type in PART_TO_WHOLE_TYPES and (min(values) < 0 or max(values) == 0):
            raise ValueError("饼图和环图的数据必须非负，且至少一项大于零。")
        series.append({"name": str(raw.get("name", "系列")).strip() or "系列", "values": values})
    return {
        "type": chart_type,
        "title": str(value.get("title", "")).strip(),
        "categories": categories,
        "series": series,
        "show_legend": bool(value.get("show_legend", len(series) > 1)),
        "show_data_labels": bool(value.get("show_data_labels", True)),
        "show_percentage": bool(value.get("show_percentage", False)),
        "number_format": str(value.get("number_format") or "General"),
    }


def add_editable_chart(slide, chart_data: dict[str, Any], x, y, w, h):
    chart_config = normalize_chart_data(chart_data)
    data = CategoryChartData(number_format=chart_config["number_format"])
    data.categories = chart_config["categories"]
    for series in chart_config["series"]:
        data.add_series(series["name"], series["values"])
    chart = slide.shapes.add_chart(CHART_TYPES[chart_config["type"]], x, y, w, h, data).chart
    chart.has_legend = chart_config["show_legend"]
    if chart_config["title"]:
        chart.has_title = True
        chart.chart_title.text_frame.text = chart_config["title"]
    if chart_config["show_data_labels"]:
        plot = chart.plots[0]
        plot.has_data_labels = True
        labels = plot.data_labels
        percentage = chart_config["show_percentage"]
        labels.show_value = not percentage
        labels.show_percentage = percentage
        if percentage or chart_config["number_format"] != "General":
            labels.number_format = chart_config["number_format"] if "number_format" in chart_data else "0%"
    return chart
