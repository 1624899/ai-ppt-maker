---
name: ai-ppt-maker
description: 将长文制成演示文稿，或按原版式把整页截图还原成 PPTX。支持图片版、可编辑文字、原生图表和最终交付稿的 PowerPoint 回看。
---

# AI PPT Maker

本 Skill 可单独复制到 Codex 的 skills 目录。`scripts/` 已包含所需的项目算法副本，运行时不读取原项目、不启动 Web 服务、不调用模型 HTTP API。Codex 负责规划、调用内置 `image_gen` 生图并对照视觉稿修正；本地 Python 脚本负责事实校验、画布适配、元素切分和 PPTX 导出。随包 `LICENSE` 适用于复制的项目代码，来源见 [随包代码来源](references/code-provenance.md)。

首次使用时在独立 Python 环境运行 `python -m pip install -r requirements.txt`。真实 PowerPoint 回看需要 Windows 与本机 PowerPoint；若不可用，不能把其他渲染结果称为“PowerPoint 真实导出图”。

需要通用图标时，优先用 `python scripts/deck_cli.py icons --query "关键词"` 检索随包的完整 Lucide SVG 图库。按需读取返回的候选文件，使用与素材导出方法见[离线图标](references/icons.md)。仅在本地候选无法满足语义、风格或品牌要求时联网查找。

## 工作流程

0. **检查环境。** 运行 `python scripts/deck_cli.py doctor`，确认依赖、PowerPoint 渲染能力和可用字体。从输出中为规划选定覆盖所需语言的字体族。
1. **确定交付模式。** 默认使用 `overlay`，每张截图按原顺序还原为一张幻灯片。用户需要拆开的资源页和可编辑内容页时选择 `separate_slides`。只需整页图片时选择 `image_only`。
2. **准备原稿。** 截图还原使用 `external_reference`，保留原版式，允许相邻页重复版式，按原图顺序填写 `reference_image`。长文新做时，将原文保存为 UTF-8 `brief.txt`，运行 `anchors`，编写 `style_guide` 和逐页规划，并分配 `source_anchor_ids`。相邻页使用不同版式，三页及以上使用至少三种版式。运行 `validate` 与 `prompts`，再用内置 `image_gen` 生成原稿。把选定图像保存到工作目录并运行 `normalize`。
3. **按内容还原。** 图片版在规范化后直接运行 `export --mode image_only`。数据图表清晰可辨时，先核对分类、数值和单位。普通图表可填写 `charts`，由随包脚本生成。柱线组合图、次坐标轴，或已由 `@oai/artifact-tool` 制作的稿件，按[复杂图表与可编辑数据](references/advanced-charts.md)处理。默认使用随数据更新的原生标签。只有特殊排版才用独立文本框，交付时说明这些标签需要手动同步。无法确认的数值用原图保留或向用户核实。
4. **准备素材与文字。** 以规范化原稿为基准准备 `elements_image`，去掉将由图表和文本框重建的内容。`prepare` 自动跳过已登记的 `charts` 区域，保留在素材里的照片或图示可以用 `text_exclusion_regions` 标记。按每页 `text_boxes.draft.json` 的逐行候选填入准确原文，仅归并语义上属于同一段的行，并修正异常框。默认使用 `cutout_mode: "split"`，执行 `prepare` 并用切分素材组装页面，独立制作图表时也遵循这一规则。查看回拼告警定位视觉缺失，修正素材后重新切分。只有用户明确要求不切分时，才使用 `cutout_mode: "background_only"` 保留整页元素图。运行 `validate --require-text-boxes --work-dir <工作目录>`，分层交付时加 `--mode separate_slides`。处理提示的布局问题。
5. **保存并验收交付稿。** 保存最终 PPTX。使用随包脚本时运行 `export`。追加页面时，在已有文件的副本中插入页面，保存后核对原页页序、已有图表和嵌入数据。用 `preview --pptx <交付文件> --output-dir <预览目录>` 让本机 PowerPoint 渲染最终文件的每一页。核对轴标签、图例、数据标签和文字是否完整，并在 PowerPoint 中确认原生图表可用「编辑数据」打开嵌入表格。修正后重新保存和渲染。

完整 JSON 格式、命令与告警口径见 [项目格式与命令](references/project-format.md)。
