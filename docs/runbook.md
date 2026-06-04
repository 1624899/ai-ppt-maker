# 运行手册

## 环境准备

```powershell
pip install -r requirements.txt
Set-Location web_ui
npm install
npm run build
Set-Location ..
```

配置模板是 `config.json`，本机私有覆盖是 `config.local.json`。运行时会先读取模板，再合并本地覆盖；`config.local.json` 已加入 `.gitignore`，用于保存本地模型端点、激活模型和并发等私有设置。高敏感 API Key 不写入配置 JSON，统一保存在本地 `.env`；模型档案可以通过 Web 界面维护，首次保存时会自动创建或更新 `.env`。

## 启动后端

```powershell
python main.py
```

后端 API 默认运行在 `http://127.0.0.1:7860`。Web 端会写入 `output/jobs.sqlite3`，并为每个任务创建 `output/<job_id>/`。

## 前端开发

```powershell
Set-Location web_ui
npm install
npm run dev
```

前端开发服务按 Vite 终端输出访问，通常是 `http://127.0.0.1:5173`。`web_ui/vite.config.js` 会把 `/api`、`/output` 和 `/runs` 代理到后端；任务、模型配置和产物接口仍由 `python main.py` 提供。

## 任务与导出

常用 Web API：

- `POST /api/jobs`：创建任务。
- `GET /api/jobs/<job_id>`：读取任务状态。
- `GET /api/jobs/<job_id>/stream`：读取单任务 SSE。
- `POST /api/jobs/<job_id>/interrupt`：停止任务。
- `POST /api/jobs/<job_id>/resume`：续跑任务。
- `POST /api/jobs/<job_id>/deliver`：基于 `editable_delivery.bundle.json` 重新导出交付版本。
- `POST /api/jobs/<job_id>/operations`：提交单页重生成、文字优化、排版优化、风格调整或版本恢复。
- `POST /api/jobs/<job_id>/agent/draft`：根据对话生成结构化 Agent 草案。
- `POST /api/jobs/<job_id>/image-edit-candidates`：生成图片编辑候选。
- `POST /api/jobs/<job_id>/image-edit-candidates/<candidate_id>/apply`：确认替换候选图。

## 测试

```powershell
python -m pytest -q
Set-Location web_ui
npm run build
Set-Location ..
```

## 维护工具

```powershell
python tools\render_preview_from_script.py --source-script output\<job_id>\03_ppt_build\generated_text_layout.py --work-dir output\<job_id>\03_ppt_build --output-pptx output\<job_id>\probe.pptx --preview-image output\<job_id>\probe.png --reference-image output\<job_id>\01_reference_pages\page_01_reference.png --comparison-image output\<job_id>\probe_compare.png
python tools\rerun_transparent_asset_split.py --project output\<job_id>\project.generated.json --transparent-root output\<job_id>\03_ppt_build --output-root output\<job_id>\asset_split_retry --pages 1
python tools\inspect_layered_ppt.py
```

## 常见故障

- 前端开发服务打不开：确认后端已用 `python main.py` 启动，再在 `web_ui` 运行 `npm run dev`；如果端口被占用，以 Vite 终端输出的地址为准。
- `PowerPoint COM` 不可用：真实闭环会跳过真导出回看或停在相关预览阶段。用 `tools\render_preview_from_script.py` 复用已生成页脚本做最小探测。
- 图像生成接口偶发网络错误：检查 `request_retry_count`、`request_transport_retry_count`、`request_total_timeout_seconds`。
- 导出缺少原稿图或元素图：确认 `01_reference_pages/` 和 `02_elements_pages/` 已生成。
- 首轮文字层效果不错但修正轮过度收缩：优先检查 `03_ppt_build/generated_text_layout.py` 与页目录下的 `office_preview_round_01.png`、`comparison_round_01.png` 的对照。
- 最终 PPT 可打开但观感偏差大：确认文本框是否仍为 `MSO_AUTO_SIZE.NONE`，并检查首轮是否同时喂给了原稿图和元素图。
