# Web UI

这是 PPT 自动制作系统的 React/Vite 前端。生产构建后的文件输出到 `web_ui/dist`，由根目录的 Flask 应用直接托管。

## 开发命令

```powershell
npm install
npm run dev
npm run build
npm run lint
```

开发时通常同时运行：

```powershell
python ..\main.py
npm run dev
```

Vite 只负责前端热更新；任务创建、模型配置、任务流、产物访问、Agent 草案和图片编辑候选都走 Flask API。

## 主要目录

- `src/components/Workspace/`：创作工作区、PPT Studio、Agent 对话、图片标注和任务操作。
- `src/components/Layout/`：顶部应用栏和设置弹窗。
- `src/components/styles/`：按领域拆分的 CSS Modules，承载工作区组件样式。
- `src/hooks/`：任务列表、任务详情、模型配置、任务操作和 Agent 草案请求。
- `src/utils/`：任务 API、展示模型、图片编辑候选和顶栏动作。
- `src/index.css`：全局基础样式，仅保留设计变量、重置、原生控件和滚动条。
- `dist/`：生产构建产物，不手写维护。
