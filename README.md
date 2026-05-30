# PPT 自动制作系统

这是一个基于 AI 的多页 PPT 自动生成系统。当前导出主路径已经统一为：

- 首轮：`参考图 + 元素图` 生成文字层脚本
- 二轮：`参考图 + PowerPoint 真导出图` 回看修正
- 最终：把分割后的元素资源页与可编辑文本框页按原位置分别导出到相邻两页，便于后续手动叠加或单独修改

详细说明见 [PPT_SYSTEM_README.md](PPT_SYSTEM_README.md)，模块边界见 [docs/architecture.md](docs/architecture.md)，运行与排障见 [docs/runbook.md](docs/runbook.md)。

## 快速开始

```powershell
conda activate aippt
pip install -r requirements.txt
python web_app.py
```

启动后访问 `http://127.0.0.1:7860`。生成任务的中间产物和 PPTX 默认写入 `output/<job_id>/`。

## 常用命令

```powershell
python ppt_pipeline.py --project project.generated.json --output auto_ppt_output.pptx
python -m pytest -q
```

## 核心目录

- `web_app.py`：Flask Web 入口，负责任务状态、模型配置、生成、导出、暂停和续跑。
- `front/`：Web 前端模板与静态资源。
- `ppt_system/`：核心库，包含规划、生图 prompt、导出编排、真实闭环文字层直出和 PPTX 脚本运行时。
- `tests/`：单元测试和诊断脚本。
- `output/`：任务数据库、模型缓存和生成产物。

## 配置要点

模型、尺寸、并发、重试与导出策略集中在 `config.json`。高敏感 API Key 统一保存在本地 `.env`，可通过 Web 的模型配置页面首次录入并自动写入；提交代码前不要把真实密钥写入文档或示例。
