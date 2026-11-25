# 离线图标资源

`lucide-icons.zip` 复用仓库 Skill 的完整 `skills/ai-ppt-maker/assets/icons/` 素材快照，供系统独立运行与 Windows 打包使用。压缩包目录与原素材目录一致，包含 SVG、`catalog.json`、中文别名和 Lucide 许可。

来源为官方 npm 包 `lucide-static@1.78.0`。版本、来源与 npm 完整性摘要保存在包内 `lucide/catalog.json`。ISC / MIT 许可全文保存在 `lucide/LICENSE`，随素材一起分发。导出图标时会同时保留 SVG 中的许可元数据与 `icons.LICENSE.txt`。

检索规则复用 Skill 的中英文关键词匹配；系统不读取已安装的 Skill，也不通过生图模型生成替换图标。SVG 渲染使用 [resvg-py](https://resvg-py.readthedocs.io/en/latest/usage.html)。更新素材时应整体重新压缩该目录，并同步核对版本与许可。
