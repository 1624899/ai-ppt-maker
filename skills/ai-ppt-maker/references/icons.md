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

长文新做 PPT 时，按内容需要规划图标，整页原稿作为替换位置和样式的依据。对生图原稿和用户截图，均默认把通用图标替换为语义一致的 Lucide SVG。以规范化原稿为准记录每个图标的位置、大小和线条颜色，在元素图编辑时擦除图标本身，保留周围的底座、阴影和背景，再把替换图标放回原位。

- **可编辑版**。元素图仍通过 `prepare` 切分并用独立素材组装。使用随包 `export` 后，由制作 Agent 用支持 SVG 的工具插入导出的 SVG。在 Windows 上可通过 PowerPoint 的 `Shapes.AddPicture` 插入 SVG 并嵌入文件，位置和大小按幻灯片尺寸将画布像素换算为点。`overlay` 插入对应幻灯片，`separate_slides` 插入对应资源页。使用 `preview` 回看最终文件，确认每个替换图标只出现一次，位置和大小与原稿一致。
- **整页图片版**。在规范化原稿上仅擦除待换图标，再将 Lucide SVG 渲染并合成到原位。将合成结果写入工作目录中该页的 `page_XX/reference.png`，再执行 `export --mode image_only`。

图库文件只在实际检索或选用时读取。日常使用无需联网下载图标，新增图库文件也不会自动进入模型上下文。需要全库缺少的图标、品牌 Logo 或其他风格时，再按需联网补充，并核对素材许可。
