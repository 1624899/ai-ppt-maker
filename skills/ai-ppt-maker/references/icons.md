# 离线图标

随包收录 `lucide-static@1.78.0` 的全部 2,414 个 SVG，覆盖常见商务、科技、教育、医疗、交通、生活和界面符号。图标保持统一线性风格。品牌 Logo、特殊行业符号和复杂插画按任务需要另行准备。

## 本地检索与导出

在 Skill 根目录执行以下命令。检索和 SVG 导出仅使用 Python 标准库，全程离线运行。

```text
python scripts/deck_cli.py icons
python scripts/deck_cli.py icons --query "医疗" --limit 8
python scripts/deck_cli.py icons --query "chart line" --limit 6
python scripts/deck_cli.py icons --name users --color "#2563EB" --size 256 --output <工作目录>/icons/users.svg
```

省略查询时返回图库版本和数量。检索返回匹配总数及最多 8 个候选名称与绝对路径，`--limit` 可设为 1 到 50。中文支持 `aliases.zh.json` 中的常用词，也可直接用英文名称与官方标签。多个空格分隔的词需要同时匹配，例如 `"arrow up"`。查询无结果时先换用简短中文词或英文近义词。

通常先查看少量候选，再按名称导出所选图标。按需读取单个 SVG，避免把整个索引或全部 SVG 读入上下文。`--color` 指定六位十六进制颜色，`--size` 设置 SVG 宽高，矢量 `viewBox` 保持原值。导出文件内嵌完整许可声明。原始资源和导出 SVG 都可作为矢量素材使用。

## 用于 PPT

长文新做 PPT 时，在规划阶段选定图标及位置，生成元素图时为这些图标留空。截图还原时，清晰且符合交付要求的原图标可以直接保留。需要替换的图标应在现有的元素图编辑步骤中一并擦除，保留周围的底座、阴影和背景，再将选好的本地图标作为独立对象放回原位。

支持 SVG 的 PPT 制作工具或 PowerPoint 可以插入导出的 SVG。使用随包 `python-pptx` 导出路径时，先用当前环境可用的 SVG 渲染工具转换为透明 PNG，再用 `slide.shapes.add_picture` 按画布坐标插入最终幻灯片。`icons` 命令导出 SVG，现有 `project.json` 和 `export` 命令的图标摆放需由制作 Agent 完成。图标替换时，元素图仍默认通过 `prepare` 切分，并使用 `assets.json` 中的独立素材组装页面。只有用户明确要求不切分时，才使用整页底图。完成插入后，对最终 PPTX 执行 `preview` 验收。

图库文件只在实际检索或选用时读取。日常使用无需联网下载图标，新增图库文件也不会自动进入模型上下文。需要全库缺少的图标、品牌 Logo 或其他风格时，再按需联网补充，并核对素材许可。
