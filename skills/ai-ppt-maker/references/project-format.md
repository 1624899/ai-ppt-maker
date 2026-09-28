# 项目格式与命令

在最终交付目录外创建工作目录，所有路径均可自行指定。`project.json`、`brief.txt` 与图像可放在同一工作区；相对图片路径以 `project.json` 所在目录为基准。所有文本文件使用 UTF-8。

## 项目 JSON

以下是一页项目的最小示例。多页时按顺序增加 `pages`，`page_no` 从 1 连续编号。文本框在完成两阶段生图后填写。

```json
{
  "source_mode": "text",
  "source_file": "brief.txt",
  "canvas": {"width": 1600, "height": 900},
  "slide_width_inch": 13.333333,
  "background_color": "#FFFFFF",
  "parallel_pages": 2,
  "style_reference_images": [],
  "required_terms": [],
  "style_guide": {
    "style_name": "简洁科技简报",
    "style_core": {
      "background_tone": "浅色背景",
      "palette": ["#163B6C", "#2C80D3", "#FFFFFF"],
      "title_style": "清楚的深蓝标题",
      "card_style": "仅在语义分组需要时使用容器",
      "icon_style": "简洁线性图标",
      "line_style": "细线连接"
    },
    "layout_families": ["hero_with_supporting_cards", "split_left_right", "timeline_horizontal"],
    "prompt_compression": "compressed",
    "prompt_max_chars": 1800
  },
  "pages": [{
    "page_no": 1,
    "title": "项目概览",
    "summary": "一句话说明本页主旨",
    "bullets": ["第一条有依据的事实"],
    "source_anchor_ids": ["S01"],
    "layout_family": "hero_with_supporting_cards",
    "visual_brief": "主体视觉、信息层级与留白要求",
    "difference_from_previous": "",
    "reference_image": "images/page_01_reference.png",
    "elements_image": "images/page_01_elements.png",
    "resize_mode": "contain",
    "background_color": "#FFFFFF",
    "text_boxes": [{
      "text": "项目概览", "left": 90, "top": 70, "width": 1100, "height": 100,
      "font_size": 38, "color": "#163B6C", "bold": true,
      "font_name": "Microsoft YaHei", "align": "LEFT", "valign": "TOP"
    }]
  }]
}
```

文本框的 `left/top/width/height` 使用 `canvas` 像素坐标。`text` 可包含换行。`font_size` 用 pt；颜色是六位十六进制值。可选字段有 `italic`、`align`、`valign`、`font_name`。先用检测结果估计位置，再用真实 PPT 预览微调。`required_terms` 填写必须逐字保留的业务口径；校验器还会核对原文中的数字与日期。

导入已有整页原稿图时，设 `source_mode` 为 `external_reference`，不需要 `source_file`；按用户给定顺序设置各页 `reference_image`。`resize_mode` 取 `stretch`、`contain`、`cover`，分别表示拉伸填满、等比留白、等比裁切。完成规范化后，再用内置生图工具生成对应 `elements_image`。

## 命令

以下命令在 Skill 根目录执行；若使用 PowerShell 读取中文内容，先运行 `chcp 65001` 并将控制台输出编码设为 UTF-8。

```text
python scripts/deck_cli.py anchors --source brief.txt --pages 6 --output anchors.json
python scripts/deck_cli.py validate --project project.json
python scripts/deck_cli.py prompts --project project.json --output prompts.json
python scripts/deck_cli.py normalize --project project.json --work-dir work
python scripts/deck_cli.py prepare --project project.json --work-dir work --workers 2
python scripts/deck_cli.py validate --project project.json --require-text-boxes
python scripts/deck_cli.py validate --project project.json --require-text-boxes --pages 2
python scripts/deck_cli.py preview --project project.json --work-dir work --output-dir previews
python scripts/deck_cli.py export --project project.json --work-dir work --output result.pptx
python scripts/deck_cli.py export --project project.json --work-dir work --output one-page.pptx --mode overlay --pages 2
```

`normalize` 将原稿图保存到 `work/page_XX/reference.png`，第二阶段生图以此为编辑目标。`prepare` 会生成 `elements.png`、`elements.transparent.png`、`text_placeholders.json`、`assets/assets.json` 和元素 PNG。检查 `asset_count`、透明图和实际元素图片；全白背景、渐变背景或原稿中的浅色元素可能需要重新生成透明元素图。

`preview` 会保留逐页的 `.pptx` 与 PowerPoint 导出 `.png`。若本机没有 PowerPoint，命令会明确报错；图片版导出不需要此步骤，可编辑版的“双轮真实回看”则需要它。`export` 的默认模式 `separate_slides` 会产生两倍于逻辑页数的实际幻灯片。输出文件与工作目录应放在 Skill 目录之外，方便更新和发布 Skill。

单页校验、预览或导出时加 `--pages`；规划与事实锚点仍按整套检查，可编辑文字层只检查选中的页。
