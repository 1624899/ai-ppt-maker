# 运行手册

## 环境准备

```powershell
conda activate aippt
pip install -r requirements.txt
```

配置文件是 `config.json`。高敏感 API Key 不写入 `config.json`，统一保存在本地 `.env`；模型档案可以通过 Web 界面维护，首次保存时会自动创建或更新 `.env`。

## 启动 Web

```powershell
python web_app.py
```

访问 `http://127.0.0.1:7860`。Web 端会写入 `output/jobs.sqlite3`，并为每个任务创建 `output/<job_id>/`。

## CLI 导出

### 项目级导出

```powershell
python ppt_pipeline.py --project project.generated.json --output auto_ppt_output.pptx
```

常用参数：

- `--work-dir`：导出中间产物目录。
- `--script-refine-rounds`：真实 PPT 导出回看轮数。

### 单页复跑

```powershell
python rerun_text_page.py --project output\<job_id>\project.generated.json --page-no 2 --output-dir output\<job_id>\page02_retry --output-name page02_retry.pptx --refine-rounds 1 --config config.json
```

## 测试

```powershell
python -m pytest -q
```

PowerPoint 真渲染探测：

```powershell
python diagnose_ppt_render.py --pptx output\demo.pptx --output output\probe.png --width 2048 --height 1152
```

## 常见故障

- `PowerPoint COM` 不可用：真实闭环会停在首轮直出。先运行 `diagnose_ppt_render.py` 检查。
- 图像生成接口偶发网络错误：检查 `request_retry_count`、`request_transport_retry_count`、`request_total_timeout_seconds`。
- 导出缺少原稿图或元素图：确认 `01_reference_pages/` 和 `02_elements_pages/` 已生成。
- 首轮文字层效果不错但修正轮过度收缩：优先检查 `generated_text_layout.py` 与 `office_preview_round_01.png`、`comparison_round_01.png` 的对照。
- 最终 PPT 可打开但观感偏差大：确认文本框是否仍为 `MSO_AUTO_SIZE.NONE`，并检查首轮是否同时喂给了原稿图和元素图。
