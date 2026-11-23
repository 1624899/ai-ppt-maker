# 项目格式与命令

在最终交付目录外创建工作目录，所有路径均可自行指定。`project.json`、`brief.txt` 与图像可放在同一工作区；相对图片路径以 `project.json` 所在目录为基准。所有文本文件使用 UTF-8。

## 项目 JSON

以下是一页项目的示例。多页时按顺序增加 `pages`，`page_no` 从 1 连续编号。文本框在完成两阶段生图后填写。

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
    "cutout_mode": "split",
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

文本框的 `left/top/width/height` 使用 `canvas` 像素坐标。`text` 可包含换行。`font_size` 用 pt，颜色是六位十六进制值。可选字段有 `italic`、`align`、`valign`、`font_name`。`required_terms` 填写必须逐字保留的业务口径，校验器还会核对原文中的数字与日期。

导入已有整页原稿图时，设 `source_mode` 为 `external_reference`，按用户给定顺序设置各页 `reference_image`。此模式下 `source_file` 和 `layout_family` 可省略，相邻页面也可以使用同一版式。`resize_mode` 可选拉伸填满（`stretch`）、等比留白（`contain`）或等比裁切（`cover`）。`elements_image` 可使用原图裁出的素材，或由内置生图工具去字。将用原生图表重建的区域应从素材图中去除，避免重复叠加。

每页的 `cutout_mode` 默认是 `split`，对元素图执行透明化和切分。只有用户明确要求不切分时，才可设为 `background_only`，将规范化后的 `elements_image` 作为一张铺满资源页的图片。文字和图表仍按所选交付模式导出。更改 `cutout_mode` 或素材后，对该页重新运行 `prepare`。

页级 `text_exclusion_regions` 可标记整块保留为素材的区域，例如照片、地图或带文字的插画。填写画布像素矩形数组，例如 `[{"left": 1000, "top": 160, "width": 480, "height": 320}]`。`prepare` 自动跳过这些区域及已登记的 `charts` 区域。该字段只影响文字候选检测，已有 `text_boxes` 和素材保留方式由各自字段控制。若需要为图表补录单独的可编辑文字，可直接填写对应的 `text_boxes`。

截图中的数据清晰可辨时，可在该页填写 `charts`。一个图表对象如下。坐标与尺寸使用画布像素，数据按分类顺序录入。

```json
{
  "type": "doughnut",
  "categories": ["本科", "硕士"],
  "series": [{"name": "人数", "values": [31, 1]}],
  "left": 960, "top": 220, "width": 480, "height": 420,
  "show_legend": true,
  "show_percentage": true
}
```

支持 `bar`（横向条形）、`column`、`line`、`pie`、`doughnut` 和 `area`。原生数据标签默认开启。饼图和环图可用 `show_percentage: true` 显示随数据更新的占比。条形图若原始值本身就是比率，录入小数（如 `0.25`），使用 `number_format: "0%"`。需要独立排版时，显式设置 `show_data_labels: false`，再录入独立文本框并在交付时告知用户。只有原生图表且没有图像素材的页面可省略 `elements_image`，`prepare` 会跳过其素材处理。纯图表页可省略 `text_boxes`。

`charts` 是随包 Python 导出器的输入。需要柱线组合、次坐标轴，或交付由 `@oai/artifact-tool` 构建的图表时，使用[复杂图表与可编辑数据](advanced-charts.md)中的独立制作流程。

## 命令

以下命令在 Skill 根目录执行；若使用 PowerShell 读取中文内容，先运行 `chcp 65001` 并将控制台输出编码设为 UTF-8。

```text
python scripts/deck_cli.py doctor
python scripts/deck_cli.py anchors --source brief.txt --pages 6 --output anchors.json
python scripts/deck_cli.py validate --project project.json
python scripts/deck_cli.py prompts --project project.json --output prompts.json
python scripts/deck_cli.py normalize --project project.json --work-dir work
python scripts/deck_cli.py prepare --project project.json --work-dir work --workers 2 --font-name "Microsoft YaHei"
python scripts/deck_cli.py validate --project project.json --require-text-boxes --work-dir work
python scripts/deck_cli.py validate --project project.json --require-text-boxes --mode separate_slides --pages 2
python scripts/deck_cli.py export --project project.json --work-dir work --output result.pptx
python scripts/deck_cli.py export --project project.json --work-dir work --output one-page.pptx --mode overlay --pages 2
python scripts/deck_cli.py preview --pptx result.pptx --output-dir previews
python scripts/deck_cli.py preview --pptx result.pptx --output-dir previews --pages 3
```

`doctor` 输出 Python 依赖的导入状态、PowerPoint COM 的实测渲染状态，以及支持英语、简体中文和繁体中文的本机字体族。Windows 按代表性字符检测覆盖范围。PowerPoint 或字体探测不可用会单独报告，命令仅在必需的 Python 依赖缺失或加载失败时返回退出码 1。

`normalize` 将原稿图保存到 `work/page_XX/reference.png`，第二阶段生图以此为目标。`prepare` 在同一目录生成 `elements.png`、`text_placeholders.json`、`text_boxes.draft.json`、`assets/assets.json` 和 `assets.recomposed.png`。`split` 还会生成 `elements.transparent.png` 和拆分的元素图片。

- 草案按候选行给出 `text_boxes`。补入准确原文，并根据语义决定要归并的段落。字号按项目的 `slide_width_inch` 换算，字重、颜色和对齐从差异像素估计。占位文件另有采样到的背景色。草案使用 `--font-name` 指定的字体族，省略时使用 `Microsoft YaHei`。`prepare` 只写工作目录，已有文本框可保留在 `project.json` 中。
- `cutout_visual_difference` 告警包含页码和主要差异块的像素范围。`canvas_difference_ratio` 是差异像素占全画布的比例，计算时排除锐化等既有图像增强能够解释的色差。`lost_foreground_ratio` 是原先明显区别于声明底色、回拼后变成透明空洞的像素占原可见前景的比例。对照 `elements.png` 和 `assets.recomposed.png` 核实后，调整素材并重新切分。只有用户明确要求不切分时才改用整页底图。
- `validate --require-text-boxes` 会阻断无效字段和实际越界。显著重叠、距画布边缘不足 2%、估算溢出和低对比度列在 `warnings`。默认按 `overlay` 检查，传入 `--work-dir` 后从回拼图采样文字框覆盖区域。`separate_slides` 的文字页按声明底色检查。对比度阈值参考 WCAG，普通文字为 4.5:1，大号文字为 3:1。真实字体的换行和原生图表标签需要在最终 PPTX 中检查。

`preview` 用本机 PowerPoint 打开 `--pptx` 指定的文件，按实际页序输出 `slide_01.png` 等图片。追加、合并或手动修正后，把实际交付文件作为输入。缺少 PowerPoint 时，命令会明确报错。`export` 默认使用 `overlay`，每个逻辑页对应一张幻灯片。`separate_slides` 为每个逻辑页生成一张资源页和一张可编辑内容页。输出文件与工作目录应放在 Skill 目录之外。

校验或导出的 `--pages` 使用项目中的逻辑页码，规划与事实锚点仍按整套检查。预览的 `--pages` 使用交付文件中的实际幻灯片编号。
