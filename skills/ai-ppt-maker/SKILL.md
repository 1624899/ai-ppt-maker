---
name: ai-ppt-maker
description: 将长文制成演示文稿，或按原版式把整页截图还原成 PPTX。支持图片版、可编辑文字、原生图表和最终交付稿的 PowerPoint 回看。
---

# AI PPT Maker

本 Skill 可单独复制到 Codex 的 skills 目录。`scripts/` 已包含所需的项目算法副本，运行时不读取原项目、不启动 Web 服务、不调用模型 HTTP API。Codex 负责规划、调用内置 `image_gen` 生图并对照视觉稿修正；本地 Python 脚本负责事实校验、画布适配、元素切分和 PPTX 导出。随包 `LICENSE` 适用于复制的项目代码，来源见 [随包代码来源](references/code-provenance.md)。

首次使用时在独立 Python 环境运行 `python -m pip install -r requirements.txt`。真实 PowerPoint 回看需要 Windows 与本机 PowerPoint；若不可用，不能把其他渲染结果称为“PowerPoint 真实导出图”。

## 工作流程

1. **确定交付模式。** 默认使用 `overlay`，每张截图按原顺序还原为一张幻灯片。用户需要拆开的资源页和可编辑内容页时选择 `separate_slides`。只需整页图片时选择 `image_only`。
2. **准备原稿。** 截图还原使用 `external_reference`，保留原版式，允许相邻页重复版式，按原图顺序填写 `reference_image`。长文新做时，将原文保存为 UTF-8 `brief.txt`，运行 `anchors`，编写 `style_guide` 和逐页规划，并分配 `source_anchor_ids`。相邻页使用不同版式，三页及以上使用至少三种版式。运行 `validate` 与 `prompts`，再用内置 `image_gen` 生成原稿。把选定图像保存到工作目录并运行 `normalize`。
3. **按内容还原。** 图片版在规范化后直接运行 `export --mode image_only`。可编辑版遇到清晰可辨的数据图表时，核对分类、数值和单位，写入 `charts` 并重建 PowerPoint 原生图表。默认使用随数据更新的原生标签。只有原生标签无法表达特定排版时，才关闭对应图表标签并使用独立文本框，交付时说明这些标签需要手动同步。无法确认的数值用原图保留或向用户核实。插画、纹理和装饰可直接采用原图素材。需要去字时，以规范化原稿为编辑目标生成 `elements_image`，保留图形的位置和比例，去掉将由原生图表和文本框重建的内容。运行 `prepare` 切分素材，对照原文和 `text_placeholders.json` 重建其余文字。用 `validate --require-text-boxes` 检查可编辑内容。
4. **保存并验收交付稿。** 用 `export` 保存 PPTX。需要追加到已有 PPTX 时，在已有文件的副本中用 PowerPoint 插入页面，保存为交付文件，在最终文件中核对原页页序、已有图表和嵌入数据。用 `preview --pptx <交付文件> --output-dir <预览目录>` 直接打开同一份交付文件，由 PowerPoint 渲染全部实际幻灯片，包括拆分模式的资源页和内容页。逐页对照原稿，重点检查文字溢出、图表轴标签裁切、图例和数据标签遮挡。修正并保存后重跑最终预览。明确告知任何使用独立文本框的图表标签，再返回通过验收的文件路径。

完整 JSON 格式、命令与文件目录见 [项目格式与命令](references/project-format.md)。处理图像时检查透明图和 `assets.json`；若背景或元素被误删，针对原稿/元素图重新生成或调整输入，不把有缺失的页面直接交付。
