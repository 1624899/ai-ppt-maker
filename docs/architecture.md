# 架构说明

## 端到端流程

系统当前按“React/Vite 前端 + Flask API 编排 + 真实闭环导出”拆分：

1. `web_ui/src/` 提供创作工作区、PPT Studio、模型设置、任务操作、Agent 对话和图片标注编辑 UI。
2. `main.py` 创建 Flask 后端应用，`ppt_system.web.app.create_app()` 注册 UI、配置、任务、产物 API Blueprint。
3. `ppt_system.web.services.jobs_api_service` 接收长文、页数、风格参考、目标交付类型和模型配置，创建任务状态。
4. `ppt_system.web.services.job_pipeline_runner` 按阶段推进规划、原稿图、元素图和 PPT 导出，并支持暂停、续跑与恢复点跳过。
5. `ppt_system.generation.content_agent` 生成 `style_guide` 和页面规划。
6. `ppt_system.generation.design_grammar` 归一化设计语法、版式家族和 prompt 压缩策略。
7. `ppt_system.generation.generation_prompts` 构建每页原稿图 prompt 与元素图 prompt。
8. `ppt_system.integrations.openai_image_provider` 调用图像模型，输出原稿图和去文字元素图。
9. `ppt_system.generation.page_evaluator` 对页面规划和 prompt 做轻量规则评估。
10. `ppt_system.export.export_pipeline` 将 Web 任务转换为导出项目，并调度 `direct_office_refine`。
11. `ppt_system.export.direct_project_script` 按页执行：
   - 首轮：`原稿图 + 元素图`
   - 元素图增强、透明化、连通域分割
   - 真实 PPT 导出 PNG
   - 二轮：`原稿图 + 真实导出图`
12. `ppt_system.export.text_script_runtime` 负责白名单脚本校验、脚本模板组装与执行。
13. `ppt_system.web.services.job_operations_service`、`job_agent_draft_service`、`job_image_edit_service` 提供任务后续协作：结构化修改草案、单页/整套操作、图片编辑候选、版本保存与恢复。

## 主要模块边界

- 内容规划：`generation/content_agent.py`、`generation/planner.py`、`generation/design_grammar.py`
- Prompt 构建：`generation/generation_prompts.py`
- 模型访问：`integrations/openai_chat_provider.py`、`integrations/openai_image_provider.py`
- Web 路由：`web/app.py`、`web/blueprints/*.py`
- Web 服务：`web/services/jobs_api_service.py`、`job_pipeline_runner.py`、`job_operations_service.py`、`job_agent_draft_service.py`、`job_image_edit_service.py`
- Web 任务状态：`jobs/job_store.py`、`jobs/active_job_registry.py`、`export/stage_resume.py`
- 导出编排：`export/export_pipeline.py`、`export/direct_project_script.py`、`export/direct_page_script.py`
- 元素处理：`image/image_ops.py`、`image/background_removal.py`、`image/splitter.py`、`image/component_postprocess.py`
- PPT 真渲染：`export/ppt_calibration_renderer.py`
- 脚本运行时：`export/text_script_runtime.py`、`export/text_style_runtime.py`
- 风格运行时：`generation/style_runtime.py`、`generation/page_evaluator.py`
- 前端应用：`web_ui/src/components/Workspace/`、`web_ui/src/hooks/`、`web_ui/src/utils/`

## 数据产物

`output/<job_id>/` 是单个任务的工作目录，通常包含：

- `status.json`：Web 任务阶段状态。
- `job.json`：内容、规划、原稿图、元素图等任务快照。
- `01_reference_pages/`：带文字原稿图。
- `02_elements_pages/`：去文字元素图。
- `03_ppt_build/`：可编辑 PPT 导出工作目录。
  - `generated_text_layout.py`
  - `editable_delivery.bundle.json`
  - `page_XX/assets/assets.json`
  - 分割后的元素 PNG
  - `render_preview_round_01.pptx`
  - `office_preview_round_01.png`
  - `comparison_round_01.png`
- `04_image_edits/`：图片编辑候选图与 prompt。
- `versions/`：单页重生成、图片替换、恢复操作前的页面版本。
- 最终 `.pptx`：默认写在任务根目录。

`output/jobs.sqlite3` 保存任务历史；`output/model_cache/` 保存项目内模型缓存。

`status.json` 中还会保存 `operations`、`page_versions`、`agent_conversation`、`agent_pending_draft`、`image_edit_candidates`，前端据此展示最近操作、Agent 草案和可应用的图片编辑候选。

## 当前设计原则

- 只有一条导出主路径：`direct_office_refine`
- 不再保留 legacy/builtin 文字导出回退
- 文本框始终使用 `MSO_AUTO_SIZE.NONE`
- 首轮模型输入必须包含 `原稿图 + 元素图`
- 二轮校正只依赖 `原稿图 + PowerPoint 真导出图`
- 元素图最终会经过增强、透明化和分割，再与文本框一起叠加到 PPT 中
- 任务后编辑必须通过结构化操作记录进入状态；涉及图片替换前先生成候选并保留页面版本，避免直接覆盖不可回退
- Flask 托管优先使用 `web_ui/dist`；应用工厂里还保留历史模板路径 fallback，但当前仓库的前端源码在 `web_ui/`
