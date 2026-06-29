# Windows 桌面打包说明

本项目的第一阶段桌面分发采用「前端静态构建 + Flask 本地服务 + PyInstaller」方案。打包后的程序仍在本机启动 Web 工作区，默认监听 `http://127.0.0.1:7860`。

## 运行时数据目录

源码开发模式默认继续使用项目目录，便于调试：

- `config.local.json`
- `.env`
- `output/jobs.sqlite3`
- `output/<job_id>/`

PyInstaller 打包后的 exe 默认使用用户数据目录：

```text
%APPDATA%\AI PPT Maker\
├── .env
├── config.local.json
├── logs\
└── output\
    ├── jobs.sqlite3
    └── <job_id>\
```

可通过环境变量覆盖：

| 变量 | 说明 |
| --- | --- |
| `PPT_SYSTEM_DATA_DIR` | 指定完整的数据目录，优先级最高 |
| `PPT_SYSTEM_DATA_MODE=project` | 源码模式使用项目目录；打包后使用 exe 所在目录 |
| `PPT_SYSTEM_DATA_MODE=portable` | 源码模式使用项目目录下的 `data/`；打包后使用 exe 所在目录下的 `data/` |
| `PPT_SYSTEM_DATA_MODE=appdata` | 强制使用用户 AppData 目录 |

## 一键构建

在 Windows PowerShell 中执行：

```powershell
.\scripts\build_windows_desktop.ps1 -Clean
```

生成目录：

```text
dist\AI PPT Maker\
```

如需单文件 exe：

```powershell
.\scripts\build_windows_desktop.ps1 -Clean -OneFile
```

单文件模式启动更慢，正式内测更推荐默认的文件夹模式。

## 打包内容

脚本会执行：

1. 检查 `python` 和 `npm`。
2. 在 `web_ui/` 下执行 `npm ci` 或 `npm install`。
3. 执行 `npm run build`。
4. 确认或安装 `PyInstaller`。
5. 将 `config.json`、`web_ui/dist` 和文档图片资源打进程序。

## 后续产品化建议

- 增加 `packaging/windows/app.ico` 后，构建脚本会自动使用该图标。
- 用 Inno Setup 或 NSIS 包装 `dist/AI PPT Maker/`，创建开始菜单和桌面快捷方式。
- 发布给外部用户前建议做代码签名，减少 Windows SmartScreen 拦截。
- 下一阶段可以用 `pywebview` 增加桌面窗口壳，继续复用当前后端与前端。
