---
name: ai-ppt-maker
description: 将长文制成演示文稿，或按原版式把整页截图还原成 PPTX。支持图片版、可编辑文字、原生图表和最终交付稿的 PowerPoint 回看。
---

# AI PPT Maker

本 Skill 可单独复制到 Codex 的 skills 目录。`scripts/` 已包含所需的项目算法副本，运行时不读取原项目、不启动 Web 服务、不调用模型 HTTP API。Codex 负责规划、调用内置 `image_gen` 生图并对照视觉稿修正；本地 Python 脚本负责事实校验、画布适配、元素切分和 PPTX 导出。随包 `LICENSE` 适用于复制的项目代码，来源见 [随包代码来源](references/code-provenance.md)。

首次使用时在独立 Python 环境运行 `python -m pip install -r requirements.txt`。真实 PowerPoint 回看需要 Windows 与本机 PowerPoint；若不可用，不能把其他渲染结果称为“PowerPoint 真实导出图”。

本文件所在目录记为 `<SKILL_DIR>`，下文的脚本与依赖路径均相对此目录；任务产物写入工作区。制作演示文稿时，严禁直接读取 `scripts/ppt_system/` 源码与大型 JSON 配置，锚点、校验和压缩提示词统一通过 `deck_cli.py` 获取。此限制不适用于用户明确要求的 Skill 代码维护。

仅在用户对风格举棋不定、提出视觉修改或要求收藏时读取[视觉调优](references/style-tuning.md)的对应部分。仅在用户点名复用收藏风格时读取工作区的 `user-styles.md`，或 `<SKILL_DIR>/references/user-styles.md`；同名以工作区为准，不预加载其他偏好。

截图还原或从生图原稿制作 PPT 时，默认用随包 Lucide SVG 替换原稿中的通用图标。品牌标志、无法等价替换的专用符号和用户要求保留的图标沿用原稿。需要替换时，运行 `python scripts/deck_cli.py icons --query "关键词"` 检索，并按[离线图标](references/icons.md)定位、擦除和回填。

## 工作流程

0. **检查环境。** 运行 `python scripts/deck_cli.py doctor`，确认依赖、PowerPoint 渲染能力和可用字体。从输出中为规划选定覆盖所需语言的字体族。
1. **确定交付模式。** 默认使用 `overlay`，每张截图按原顺序还原为一张幻灯片。用户需要拆开的资源页和可编辑内容页时选择 `separate_slides`。只需整页图片时选择 `image_only`。
2. **准备原稿与视觉定调。** 截图还原使用 `external_reference`，保留原版式，允许相邻页重复版式，按原图顺序填写 `reference_image`。长文新做时，将原文保存为 UTF-8 `brief.txt`，运行 `anchors`，编写 `style_guide` 和逐页规划，并分配 `source_anchor_ids`。相邻页使用不同版式，三页及以上使用至少三种版式。运行 `validate` 与 `prompts`，按以下规则调用内置 `image_gen`，把选定图像保存到工作目录并运行 `normalize`。
   - **⛔ 门禁 1：大纲与方向。** 纯文字新做时，用一条聚合消息给出逐页结论标题与角色，以及推荐的四维组合：信息密度（阅读型／演讲型）、基底明暗、视觉质感、主色与强调色。受众决定内容组织，各页版式继续按内容动态分配。等待用户确认后才生图；已明确的要求不重复询问，用户明确要求“直接生成、不用确认”时跳过两道确认。
   - **⛔ 门禁 2：单页试妆。** 无用户指定的风格参考图或可用收藏样板时，只生成一张最有代表性的内容内页并展示，确认前不得生成其余页或去字元素图；单页任务以该页为样板。仅当用户明确表示不知如何选风格时，为同一页生成两种方向供选。视觉反馈按需读取调优表，以上一版图为参考，只改目标问题；修改规划后重新运行 `validate` 与 `prompts`。
   - **锁图量产。** 将确认的样板或用户指定的风格参考图实际传入后续每次原稿生图调用，只继承配色、字体气质和质感，不复制样板构图与内容。收藏样板可用时跳过门禁 2；图片不可访问时先查找可用副本，仍不可用则按新样板流程处理。明确免确认时先自行检查一页，以该页为风格参考继续。去字阶段始终以各页自身的规范化原稿为参考。
3. **按内容还原。** 图片版在规范化及所需图标替换完成后运行 `export --mode image_only`。数据图表清晰可辨时，先核对分类、数值和单位。普通图表可填写 `charts`，由随包脚本生成。柱线组合图、次坐标轴，或已由 `@oai/artifact-tool` 制作的稿件，按[复杂图表与可编辑数据](references/advanced-charts.md)处理。默认使用随数据更新的原生标签。只有特殊排版才用独立文本框，交付时说明这些标签需要手动同步。无法确认的数值用原图保留或向用户核实。
4. **准备素材与文字。** 以规范化原稿为基准准备 `elements_image`，去掉将由 Lucide SVG、图表和文本框重建的内容。`prepare` 自动跳过已登记的 `charts` 区域，保留在素材里的照片或图示可以用 `text_exclusion_regions` 标记。按每页 `text_boxes.draft.json` 的逐行候选填入准确原文，仅归并语义上属于同一段的行，并修正异常框。默认使用 `cutout_mode: "split"`，执行 `prepare` 并用切分素材组装页面，独立制作图表时也遵循这一规则。查看回拼告警定位视觉缺失，修正素材后重新切分。只有用户明确要求不切分时，才使用 `cutout_mode: "background_only"` 保留整页元素图。运行 `validate --require-text-boxes --work-dir <工作目录>`，分层交付时加 `--mode separate_slides`。处理提示的布局问题。
5. **保存并验收交付稿。** 保存最终 PPTX。使用随包脚本时运行 `export`。可编辑版导出后将替换图标作为独立 SVG 对象放回对应页面。追加页面时，在已有文件的副本中插入页面，保存后核对原页页序、已有图表和嵌入数据。用 `preview --pptx <交付文件> --output-dir <预览目录>` 让本机 PowerPoint 渲染最终文件的每一页。核对轴标签、图例、数据标签和文字是否完整，并在 PowerPoint 中确认原生图表可用「编辑数据」打开嵌入表格。修正后重新保存和渲染。

局部修改仅重生成目标页；`normalize`、`prepare` 可用 `--pages` 限定处理，更新完整交付文件后回看受影响页。只有用户明确要求收藏时，才按[收藏格式](references/style-tuning.md#常用风格收藏)保存已确认的四维描述与持久样板路径，默认写入工作区 `user-styles.md`。

完整 JSON 格式、命令与告警口径见 [项目格式与命令](references/project-format.md)。
