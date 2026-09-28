---
name: ai-ppt-maker
description: 用 Codex 内置生图工具和随包本地脚本，把长文或整页原稿图制成图片版、可编辑分层 PPTX。用于需要内容规划、两阶段生图、文字校正和 PPTX 交付的完整制作任务。
---

# AI PPT Maker

本 Skill 可单独复制到 Codex 的 skills 目录。`scripts/` 已包含所需的项目算法副本，运行时不读取原项目、不启动 Web 服务、不调用模型 HTTP API。Codex 负责规划、调用内置 `image_gen` 生图并对照视觉稿修正；本地 Python 脚本负责事实校验、画布适配、元素切分和 PPTX 导出。随包 `LICENSE` 适用于复制的项目代码，来源见 [随包代码来源](references/code-provenance.md)。

首次使用时在独立 Python 环境运行 `python -m pip install -r requirements.txt`。真实 PowerPoint 回看需要 Windows 与本机 PowerPoint；若不可用，不能把其他渲染结果称为“PowerPoint 真实导出图”。

## 工作流程

1. **规划内容。** 将用户长文保存为 UTF-8 `brief.txt`；只有主题时先起草可核查的演示内容。运行 `python scripts/deck_cli.py anchors --source brief.txt --pages <页数>`，再由 Codex 编写 `project.json` 的 `style_guide` 与逐页规划。为每页分配 `source_anchor_ids`，保留编号、日期、数字与业务原词。页数不少于 3 时使用至少 3 种版式家族，相邻页不重复。用 `validate` 校验，不让脚本机械截断原文。
2. **生成原稿图。** 用 `prompts` 命令取得压缩过的风格提示与每页原稿图提示。通过 Codex 内置 `image_gen` 逐页生成带文字的完整视觉稿，传入用户提供的风格参考图，并将选定图片保存到工作目录。用户提供已有整页原稿图时跳过此步，按原图顺序填入页面路径；支持 `stretch`、`contain`、`cover` 三种适配。
3. **生成元素图。** 运行 `normalize` 得到统一画幅的原稿图。将每页规范化原稿图作为内置 `image_gen` 的编辑目标，只去掉文字，保留布局和视觉元素；保存去文字元素图。跨页可按 `parallel_pages` 配置并行，同一页始终先有原稿图再做元素图。内置生图工具的文件应复制到工作目录，不能只留在 Codex 默认生成目录。
4. **首轮文字与元素处理。** 运行 `prepare`：脚本会检测原稿与元素图的文字差异、增强元素图、透明化并按连通域切分。Codex 对照两张图、`text_placeholders.json` 与原文，把准确文字写入 `project.json` 的 `text_boxes`。坐标采用画布像素，字号采用 PowerPoint pt。运行 `validate --require-text-boxes`，确保事实和数字最终出现在可编辑文字层。
5. **第二轮真实回看。** 运行 `preview`，脚本将逐页叠加元素与文字并由本机 PowerPoint 导出 PNG。Codex 对照原稿图与真实导出图，修正文本框的位置、尺寸、字体、颜色和换行，再次预览确认。原稿图里若有生图造成的错字，以核实后的原文与规划为准。
6. **交付。** 运行 `export`。默认 `separate_slides`，每个逻辑页生成相邻的元素资源页和可编辑文字页；`overlay` 生成元素与文字同页；`image_only` 导出原稿图。用 `--pages` 可只导出指定页，否则导出整套。打开 PPTX 核对页数和可编辑文字，返回文件路径。

完整 JSON 格式、命令与文件目录见 [项目格式与命令](references/project-format.md)。处理图像时检查透明图和 `assets.json`；若背景或元素被误删，针对原稿/元素图重新生成或调整输入，不把有缺失的页面直接交付。
