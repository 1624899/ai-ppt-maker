# PPT 自动制作系统

这是一个基于 AI 的多页 PPT 自动生成系统。当前主路径由 Flask 后端编排、React/Vite 前端交互、`ppt_system` 核心库执行生成与导出：

- 规划：对话模型生成设计语法、页面蓝图、原稿图 prompt 和元素图 prompt
- 生图：按页生成带文字原稿图，再生成去文字元素图
- 导出：`direct_office_refine` 用 `原稿图 + 元素图` 生成文字层脚本，并可用 PowerPoint 真导出图回看修正
- 交付：默认输出“元素资源页 + 可编辑文本框页”的分层 PPTX，也可继续触发暂停、续跑、单页重生成、Agent 草案和图片编辑候选

详细说明见 [PPT_SYSTEM_README.md](PPT_SYSTEM_README.md)，模块边界见 [docs/architecture.md](docs/architecture.md)，运行与排障见 [docs/runbook.md](docs/runbook.md)。

## 快速开始

```powershell
pip install -r requirements.txt
python main.py
```

另开一个终端启动前端：

```powershell
Set-Location web_ui
npm install
npm run dev
```

后端 API 默认运行在 `http://127.0.0.1:7860`，前端开发服务按 Vite 终端输出访问，通常是 `http://127.0.0.1:5173`。生成任务的中间产物和 PPTX 默认写入 `output/<job_id>/`。

## 常用命令

```powershell
Set-Location web_ui
npm run build
Set-Location ..
python -m pytest -q
```

## 核心目录

- `main.py`：Flask 后端启动入口；真实路由由 `ppt_system/web/` 的 Blueprint 和 service 分层承载。
- `web_ui/`：React/Vite 前端源码；生产构建输出到 `web_ui/dist` 后由 Flask 直接托管。
- `ppt_system/`：核心库，包含规划、生图 prompt、导出编排、真实闭环文字层直出和 PPTX 脚本运行时。
- `tools/`：导出诊断、资产重切分、分层 PPT 检查等维护工具。
- `tests/`：单元测试和诊断脚本。
- `output/`：任务数据库、模型缓存和生成产物。

## 配置要点

模型、尺寸、并发、重试与导出策略集中在 `config.json`。高敏感 API Key 统一保存在本地 `.env`，可通过 Web 的模型配置页面首次录入并自动写入；提交代码前不要把真实密钥写入文档或示例。

## 许可证

本项目采用非商业使用许可证（Non-Commercial Use License）。

- 允许：个人学习、研究、教育用途。
- 允许：非商业性质的内部使用。
- 禁止：未经授权的任何商业使用。

如需商业授权，请联系作者：1624899229@qq.com

详见 [LICENSE](LICENSE) 文件。
