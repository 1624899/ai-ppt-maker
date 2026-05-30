# 架构说明

## 端到端流程

系统当前按“Web 编排 + 真实闭环导出”拆分：

1. `web_app.py` 接收长文、页数、风格原稿图和模型配置。
2. `ppt_system.generation.content_agent` 生成 `style_guide` 和页面规划。
3. `ppt_system.generation.design_grammar` 归一化设计语法、版式家族和 prompt 压缩策略。
4. `ppt_system.generation.generation_prompts` 构建每页原稿图 prompt 与元素图 prompt。
5. `ppt_system.integrations.openai_image_provider` 调用图像模型，输出原稿图和去文字元素图。
6. `ppt_system.generation.page_evaluator` 对页面规划和 prompt 做轻量规则评估。
7. `ppt_system.export.export_pipeline` 将 Web 任务转换为导出项目，并调度 `direct_office_refine`。
8. `ppt_system.export.direct_project_script` 按页执行：
   - 首轮：`原稿图 + 元素图`
   - 元素图增强、透明化、连通域分割
   - 真实 PPT 导出 PNG
   - 二轮：`原稿图 + 真实导出图`
9. `ppt_system.export.text_script_runtime` 负责白名单脚本校验、脚本模板组装与执行。

## 主要模块边界

- 内容规划：`generation/content_agent.py`、`generation/planner.py`、`generation/design_grammar.py`
- Prompt 构建：`generation/generation_prompts.py`
- 模型访问：`integrations/openai_chat_provider.py`、`integrations/openai_image_provider.py`
- Web 任务状态：`jobs/job_store.py`、`export/stage_resume.py`
- 导出编排：`export/export_pipeline.py`、`export/direct_project_script.py`、`export/direct_page_script.py`
- 元素处理：`image/image_ops.py`、`image/background_removal.py`、`image/splitter.py`、`image/component_postprocess.py`
- PPT 真渲染：`export/ppt_calibration_renderer.py`
- 脚本运行时：`export/text_script_runtime.py`、`export/text_style_runtime.py`
- 风格运行时：`generation/style_runtime.py`、`generation/page_evaluator.py`

## 数据产物

`output/<job_id>/` 是单个任务的工作目录，通常包含：

- `status.json`：Web 任务阶段状态。
- `job.json`：内容、规划、原稿图、元素图等任务快照。
- `01_reference_pages/`：带文字原稿图。
- `02_elements_pages/`：去文字元素图。
- `export/` 或导出工作目录：
  - `generated_text_layout.py`
  - `page_XX/assets/assets.json`
  - 分割后的元素 PNG
  - `render_preview_round_01.pptx`
  - `office_preview_round_01.png`
  - `comparison_round_01.png`
  - 最终 `.pptx`

`output/jobs.sqlite3` 保存任务历史；`output/model_cache/` 保存项目内模型缓存。

## 当前设计原则

- 只有一条导出主路径：`direct_office_refine`
- 不再保留 legacy/builtin 文字导出回退
- 文本框始终使用 `MSO_AUTO_SIZE.NONE`
- 首轮模型输入必须包含 `原稿图 + 元素图`
- 二轮校正只依赖 `原稿图 + PowerPoint 真导出图`
- 元素图最终会经过增强、透明化和分割，再与文本框一起叠加到 PPT 中
