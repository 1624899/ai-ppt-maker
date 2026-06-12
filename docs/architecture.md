# AI PPT Maker — 系统架构文档

## 目录

- [1. 项目概述](#1-项目概述)
- [2. 技术栈](#2-技术栈)
- [3. 系统架构](#3-系统架构)
- [4. 核心流程](#4-核心流程)
- [5. 模块与文件详解](#5-模块与文件详解)
  - [5.1 根目录文件](#51-根目录文件)
  - [5.2 内容规划模块 (ppt_system/generation/)](#52-内容规划模块-ppt_systemgeneration)
  - [5.3 导出模块 (ppt_system/export/)](#53-导出模块-ppt_systemexport)
  - [5.4 图像处理模块 (ppt_system/image/)](#54-图像处理模块-ppt_systemimage)
  - [5.5 模型集成模块 (ppt_system/integrations/)](#55-模型集成模块-ppt_systemintegrations)
  - [5.6 任务管理模块 (ppt_system/jobs/)](#56-任务管理模块-ppt_systemjobs)
  - [5.7 运行时工具模块 (ppt_system/runtime/)](#57-运行时工具模块-ppt_systemruntime)
  - [5.8 Web 层 — 路由 (ppt_system/web/blueprints/)](#58-web-层--路由-ppt_systemwebblueprints)
  - [5.9 Web 层 — 服务 (ppt_system/web/services/)](#59-web-层--服务-ppt_systemwebservices)
  - [5.10 Web 层 — 应用入口 (ppt_system/web/)](#510-web-层--应用入口-ppt_systemweb)
  - [5.11 前端 — 入口与配置 (web_ui/)](#511-前端--入口与配置-web_ui)
  - [5.12 前端 — 布局组件 (web_ui/src/components/Layout/)](#512-前端--布局组件-web_uisrccomponentslayout)
  - [5.13 前端 — 工作区组件 (web_ui/src/components/Workspace/)](#513-前端--工作区组件-web_uisrccomponentsworkspace)
  - [5.14 前端 — 表单与动画组件](#514-前端--表单与动画组件)
  - [5.15 前端 — 自定义 Hooks (web_ui/src/hooks/)](#515-前端--自定义-hooks-web_uisrchooks)
  - [5.16 前端 — 工具函数 (web_ui/src/utils/)](#516-前端--工具函数-web_uisrcutils)
  - [5.17 维护工具 (tools/)](#517-维护工具-tools)
  - [5.18 辅助脚本 (scripts/)](#518-辅助脚本-scripts)
  - [5.19 测试文件 (tests/)](#519-测试文件-tests)
- [6. 数据流与存储](#6-数据流与存储)
- [7. 设计原则](#7-设计原则)
- [8. 并发与性能](#8-并发与性能)
- [9. API 端点总览](#9-api-端点总览)
- [10. 部署与运行](#10-部署与运行)

---

## 1. 项目概述

AI PPT Maker 是一个端到端的 AI 驱动 PPT 自动制作系统。用户输入长文内容（或已有整页原稿图），系统自动完成内容规划、版式设计、配图生成和可编辑 PPT 导出的全流程。

**核心能力：**
- 输入长文 → AI 智能规划页面结构与风格
- 自动生成带文字原稿图 → 去文字元素图
- 双轮闭环导出，生成可编辑分层 PPTX
- 支持已有原稿图直接导入转换
- Web 工作区实时协作：Agent 对话编辑、图片标注、版本管理

---

## 2. 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端框架 | React 19 + Vite 5 | SPA 应用，开发热更新，生产构建由 Flask 托管 |
| 前端动画 | Framer Motion | 页面过渡与组件动画 |
| 前端图标 | Lucide React | 轻量图标库 |
| 后端框架 | Flask (Python 3.10+) | 轻量 Web 框架，应用工厂模式 |
| AI 对话模型 | OpenAI 兼容 API (gpt-5.5) | 内容规划、文字脚本生成、回看修正 |
| AI 图像模型 | OpenAI 兼容 API (gpt-image-2) | 原稿图、元素图生成 |
| PPT 生成 | python-pptx | 程序化创建/修改 PPTX 文件 |
| 图像处理 | OpenCV + Pillow | 背景移除、连通域分割、Alpha 处理、形态学操作 |
| 任务持久化 | SQLite | 轻量嵌入式数据库，存储任务状态与历史 |
| 真实渲染 | PowerPoint COM (可选) | 通过 PowerShell 调用真实 PowerPoint 渲染 PPTX 为 PNG |
| 并发模型 | ThreadPoolExecutor | Python 线程池处理并发任务与图像生成 |
| 浏览器测试 | Playwright | UI 自动化审计 |

---

## 3. 系统架构

### 3.1 整体分层

```
┌─────────────────────────────────────────────────────────────────┐
│                       React/Vite 前端 (web_ui/)                 │
│  CreationForm · PPTStudio · TaskCenter · AgentWorkspace         │
│  ImageMarkup · PagePlanEditor · StageProgress                   │
├─────────────────────────────────────────────────────────────────┤
│                       Flask API 后端 (ppt_system/web/)          │
│  Blueprint 路由 → Service 编排 → Pipeline 执行                   │
├───────────────┬───────────────┬─────────────────────────────────┤
│  generation/  │    export/    │           image/                │
│  内容规划      │   导出编排     │        元素处理                  │
│  设计语法      │   文字脚本     │        背景移除                  │
│  Prompt 构建   │   PPT 渲染    │        连通域分割                │
├───────────────┴───────────────┴─────────────────────────────────┤
│                       integrations/                             │
│            OpenAI Chat Provider · OpenAI Image Provider         │
│                       model_config                              │
├─────────────────────────────────────────────────────────────────┤
│                       jobs/ + runtime/                          │
│         SQLite 存储 · 活跃任务注册 · 断点续跑 · 中断信号            │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 前后端通信

- **RESTful API**：任务 CRUD、配置管理、操作提交
- **SSE (Server-Sent Events)**：任务进度实时推送（`/api/jobs/:id/stream`）
- **静态资源**：Flask 托管 `web_ui/dist/` 作为前端入口
- **代理模式**：Vite 开发服务器将 `/api`、`/output`、`/runs` 代理到 Flask :7860

---

## 4. 核心流程

### 4.1 从文本生成

```
用户输入长文 + 可选风格参考图
        │
        ▼
┌─────────────────────────┐
│  ① 内容规划 (Planning)    │  content_agent.py
│  - 分析长文结构            │  → style_guide + 逐页 plan
│  - 设计语法约束            │  design_grammar.py
│  - 版式多样性保证          │  ≥3 种版式家族，相邻不重复
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  ② 原稿图生成 (Stage 1)   │  generation_prompts.py
│  - 构建每页 prompt         │  openai_image_provider.py
│  - 带文字的完整视觉稿       │  并发生成，支持重试
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  ③ 元素图生成 (Stage 2)   │  generation_prompts.py
│  - 基于原稿图去文字         │  openai_image_provider.py
│  - 纯元素背景图            │  并发生成
└───────────┬─────────────┘
            │
            ▼
┌───────────────────────────────────────────────┐
│  ④ 双轮闭环导出 (Export)                         │
│                                                │
│  首轮：原稿图 + 元素图 → 文字层布局脚本            │
│    ├─ 元素图增强、透明化、连通域分割                │
│    ├─ text_script_runtime 执行脚本生成 PPTX       │
│    └─ PowerPoint COM 渲染临时真实预览 PNG          │
│                                                │
│  二轮：原稿图 + 临时真实导出图 → 回看修正           │
│    ├─ AI 对比原稿与导出差异                       │
│    ├─ 修正文字位置、样式、大小                     │
│    ├─ 回看 PPTX/PNG 用完即清理                    │
│    └─ 生成最终 editable_delivery.bundle.json     │
│                                                │
│  输出：分层 PPTX                                 │
│    ├─ 元素资源页（图片元素）                       │
│    └─ 可编辑文本框页（完全可编辑）                  │
└───────────────────────────────────────────────┘
```

### 4.2 从已有原稿图继续

```
用户上传整页原稿图 (PNG/JPG/WEBP)
        │
        ▼
┌─────────────────────────┐
│  登记为任务原稿图          │  external_reference_job.py
│  - 多图按顺序生成多页      │  支持拉伸/等比留白/等比裁切
│  - 可选「只登记」模式       │  跳过后续阶段
└───────────┬─────────────┘
            │
            ▼
     从 ③ 元素图生成阶段继续 → ④ 双轮闭环导出
```

### 4.3 工作流模式

| 模式 | 说明 |
|------|------|
| `auto` | 自动模式：规划完成后直接执行全部阶段 |
| `guided` | 引导模式：规划完成后暂停，等待用户确认/编辑页面计划后再执行 |

---

## 5. 模块与文件详解

### 5.1 根目录文件

| 文件 | 职责 |
|------|------|
| `main.py` | Flask 后端启动入口。初始化 SQLite 数据库、ThreadPoolExecutor 线程池、DB 维护调度器；通过 `ppt_system.web.create_app()` 创建应用并注册全部 Blueprint 路由；暴露 REST API 端点用于任务创建、Pipeline 执行、计划确认、交付导出、模型配置和 DB 维护 |
| `project_builder.py` | CLI 工具。接收长文文件和视觉参考图片，构建包含页面规划、文本布局和图像 prompt 的项目 JSON 配置，供下游 PPT 生成使用 |
| `config.json` | 全局配置文件。定义图像尺寸预设（square/landscape/portrait，1K-4K）、API 端点、模型设置（chat & image）、并发限制、任务 DB 维护参数和设计语法选项 |
| `requirements.txt` | Python 依赖清单：`requests`、`flask`、`python-pptx`、`opencv-python-headless`、`Pillow` |
| `package.json` | 根目录 Node.js 依赖，仅含 `playwright`（用于浏览器 UI 测试/自动化） |
| `.env.example` | 环境变量模板，展示 OpenAI 兼容 chat 和 image API 的 Base URL 和 Key 所需的变量名 |
| `.gitignore` | Git 忽略规则：`.env`、`config.local.json`、`output/`、`__pycache__`、`node_modules`、临时文档、审计脚本等 |
| `LICENSE` | 非商业使用许可证 |

---

### 5.2 内容规划模块 (`ppt_system/generation/`)

负责从用户输入的长文出发，调用 AI 进行内容分析、版式规划和 prompt 构建。

| 文件 | 职责 |
|------|------|
| `__init__.py` | 包初始化标记 |
| `content_agent.py` | **核心规划引擎**。调用对话 AI 分析长文，构建完整的多页内容规划，包括生成 `style_guide`（色彩、字体、视觉风格）和逐页 `plan`（标题、内容要点、版式建议、元素规划、源锚点分配和图像 prompt） |
| `planner.py` | 规划构建工具集。估算页数、推断风格类型、为每页推断版式家族、去重版式序列、构建默认元素规划 |
| `design_grammar.py` | **设计语法系统**。定义版式家族（grid、timeline、hub-spoke、split、process、hero cards）及其槽位模板、元素图元、变化策略；归一化版式分配与别名映射，强制页间多样性约束 |
| `generation_prompts.py` | 图像生成 prompt 构建器。为每页构建原稿图和元素图的 prompt，支持多种压缩模式（baseline、compact、slot_brief），融合风格锚点、视觉引导和形状约束 |
| `text_layout.py` | 文本布局引擎。将内容拆分到各页，分配版式家族，基于槽位计算文本框坐标，生成回退文本框 |
| `style_runtime.py` | 风格运行时。分类背景色调（light/dark）、从 style_guide 推断主题模式、解析文本配色方案、将主题颜色应用到文本框 |
| `page_evaluator.py` | 页面质量评估器。基于规则检查每页规划是否符合 style_guide（版式重复、图元覆盖、背景色调、负面规则、prompt 压缩），给出质量分数 |
| `page_image_pipeline.py` | 并发两阶段图像生成流水线。使用 ThreadPoolExecutor 协调原稿图和元素图的逐页生成，支持依赖关系（元素图等原稿图完成） |
| `page_richness.py` | 页面丰富度定义。定义 low/medium/high 三级丰富度，标准化丰富度映射，提供各级别的规划/渲染引导文本 |
| `generation_options.py` | 生成选项解析。标准化生成选项（封面页开关、页面丰富度、风格参考遵循度），合并用户参数与配置默认值 |
| `planning_constraints.py` | 规划约束生成器。生成文本约束规则注入规划 prompt，强制叙事结构、去重和源锚点覆盖 |
| `planning_state.py` | 规划状态检查。检测任务的页面规划是否完整可恢复（所有页面有 prompt、页数正确） |
| `source_content_anchors.py` | 源内容锚点解析。将用户输入文本解析为结构化的「事实锚点」（S01, S02…），通过检测标题、编号段落和分页拆分来映射锚点到页面 |
| `source_content_control.py` | 源内容预算控制。定义 `SourceContentBudget` 数据类，根据页面丰富度和事实数量解析每页的内容预算（最大要点数、摘要长度） |
| `prompt_visual_guidance.py` | 视觉引导构建器。为 prompt 构建视觉引导文本，根据是否存在参考图和风格上下文调整语气 |
| `reference_shape_constraints.py` | 参考图形状约束。生成 prompt 行来强制形状清晰度约束（连接线样式、元素边界、反贴纸规则） |
| `reference_style_adherence.py` | 风格参考遵循度。定义和标准化参考风格遵循级别（loose/balanced/strict），生成对应 prompt 行和规划引导 |
| `title_extraction.py` | 标题提取器。从用户内容或 LLM 输出中提取干净的短标题，处理 HTML 标签、标签行和长文本 |

---

### 5.3 导出模块 (`ppt_system/export/`)

负责将规划和图像资产转换为最终的可编辑 PPTX 文件，包含双轮闭环导出全流程。

| 文件 | 职责 |
|------|------|
| `__init__.py` | 包初始化标记 |
| `direct_project_script.py` | **双轮闭环导出主流程编排器**。为每页准备分割资产，通过 LLM 生成初始文字脚本，执行真实 PPTX 渲染-修正循环；回看 PPTX/PNG 仅在当前轮使用并在 `finally` 中清理，最终组装项目脚本 |
| `direct_page_script.py` | 单页导出脚本构建器。为每页构建首轮和二轮的 LLM prompt，准备每页的资产分割；常规流程不再生成透明化预览副本 |
| `export_pipeline.py` | 高层导出流水线。从 Web 任务数据构建项目，准备可编辑交付包，调度文字脚本执行导出 PPTX |
| `text_script_runtime.py` | **文字脚本运行时**（584 行）。生成完整的 Python 脚本源码（使用 python-pptx 的 `add_text`、`add_center_text`、`add_runs`、像素到英寸映射），在沙箱子进程中执行 |
| `text_script_schema.py` | 文字脚本 Schema。定义严格的 AST 级别的允许脚本调用白名单（`add_text`、`add_center_text`、`add_runs` 等），包含参数校验、标准化和清理 |
| `text_script_worker.py` | 子进程 Worker。在隔离进程中执行生成的文字布局脚本，捕获 stdout/stderr，返回结构化 JSON 结果 |
| `text_style_runtime.py` | 文本样式运行时。python-pptx 的文本样式辅助函数：字体族注入（latin/ea/cs）、文本宽度估算、换行策略 |
| `ppt_calibration_renderer.py` | PowerPoint 真实渲染器。通过 PowerShell COM 自动化调用真实 PowerPoint 将 PPTX 首张幻灯片渲染为 PNG，用于真实办公环境预览对比 |
| `editable_delivery_bundle.py` | 可编辑交付包序列化/反序列化。将项目、页面脚本、资产和图层模式打包为 JSON，支持无重新生成的重新导出 |
| `editable_delivery_cache.py` | 交付缓存。基于签名缓存可编辑 PPTX 交付结果，当 bundle 和输出未变化时避免重复导出 |
| `delivery_options.py` | 交付模式定义。定义参考图模式和可编辑模式的常量、标签和文件名（overlay vs. separate layer） |
| `export_layer_mode.py` | 图层模式定义。定义 overlay（叠加）和 separate（分离幻灯片）两种图层模式，构建 `SlideLayerSpec` 列表，计算输出幻灯片数量 |
| `export_artifact_policy.py` | 产物策略。处理 PPTX 原子保存（先写临时文件再重命名）、回看预览产物生命周期（创建、唯一命名、用完即清理，并清理历史旧式路径）和文件锁错误消息 |
| `export_step_checkpoint.py` | 步骤检查点。管理子步骤级 JSON 检查点（含内容哈希签名），支持重复运行时跳过已完成的 LLM 或渲染步骤 |
| `export_page_resume.py` | 单页恢复管理。基于签名的页面级导出检查点，支持逐页恢复无需重跑完整导出 |
| `export_asset_checkpoint.py` | 资产准备检查点。基于图像哈希和选项的资产准备检查点，缓存命中时跳过分割元素处理 |
| `stage_resume.py` | 阶段恢复工具。检查阶段完成状态，判断 Pipeline 阶段是否需要运行或可跳过 |
| `stage_labels.py` | 阶段标签映射。将 Pipeline 阶段 key 映射到中文可读标签（排队中、规划中、原稿图生成中等） |
| `reference_preview_export.py` | 参考图预览导出。将原稿页面图片导出为纯图片 PPTX 用于预览 |
| `preview_artifact_paths.py` | 预览产物路径。重新导出 `build_round_preview_artifacts` 用于构建每轮预览文件路径 |

---

### 5.4 图像处理模块 (`ppt_system/image/`)

负责元素图的增强、透明化、连通域分割和资产清理，是导出 Pipeline 的关键前置处理。

| 文件 | 职责 |
|------|------|
| `__init__.py` | 包初始化标记 |
| `splitter.py` | **主资产分割器**（299 行）。接收透明 PNG，查找连通分量，应用分组/合并策略（颜色、图标、实例、桥接切割），输出独立资产 PNG 和清单 manifest |
| `image_ops.py` | 高层图像操作。`enhance_image`（对比度/锐度增强）和 `make_transparent`（背景移除封装） |
| `background_removal.py` | 背景移除策略。保留已有 Alpha 通道或应用内置 Alpha 蒙版精修，含基于组件的噪声过滤 |
| `foreground_reconstruction.py` | 前景重建。从边框估算背景色，构建核心/种子掩码，修剪苍白边界，恢复封闭填充区域 |
| `alpha_matte_refinement.py` | Alpha 蒙版精修。从源图重新估算背景模型，应用白轴裁切获得更干净的 Alpha |
| `alpha_matte_debug.py` | Alpha 蒙版调试。导出中间步骤图像用于可视化检查裁切流水线 |
| `alpha_edge_trim.py` | Alpha 边缘修剪。修剪 Alpha 边缘的外部背景类杂散像素，移除弱半透明边界像素同时保留完全不透明描边 |
| `alpha_fill_region_cleanup.py` | Alpha 填充区域清理。分析并清理 Alpha 掩码中的封闭填充区域，恢复属于前景的孔洞 |
| `visual_white_axis.py` | 视觉白轴检测。基于亮度、色度和背景距离阈值构建「视觉白」掩码 |
| `white_axis_cutout.py` | 白轴裁切。通过识别「视觉白」像素从 RGB 重建 Alpha，构建种子/候选前景掩码 |
| `image_alpha_profile.py` | 图像 Alpha 通道检测。检查图像 Alpha 通道极值以判断是否已有透明度 |
| `text_placeholder_detection.py` | 文本占位符检测。通过参考图和去文字元素图的像素差异，使用形态学操作检测文本占位符边界框 |
| `cv_mask_components.py` | 连通分量提取。OpenCV 或纯 NumPy 回退的连通分量提取、基于种子的掩码生长和边界泛洪填充 |
| `binary_morphology.py` | 二值形态学操作。开/闭运算和 RGB 绝对差值灰度转换，支持 OpenCV 或 NumPy 回退 |
| `component_postprocess.py` | 组件后处理。合并虚线组件簇，提供通用组件组合并（掩码联合） |
| `component_color_grouping.py` | 颜色聚类分组。合并空间上接近且共享相似主色的小碎片 |
| `component_color_signature.py` | 组件颜色签名。计算每组件的颜色签名（主色、饱和度、亮度比率）供分组决策使用 |
| `component_graph_clustering.py` | 图聚类。基于结构特征（颜色距离、描边方向相似度）的组件图聚类，用于合并虚线/断线 |
| `component_container_analysis.py` | 容器特征分析。标注组件的容器特征（填充率、孔洞率、周长占用率），构建屏障掩码防止跨容器合并 |
| `component_icon_grouping.py` | 图标碎片分组。基于间距、颜色签名和图标跨度限制合并看起来像局部图标的相邻小碎片 |
| `component_instance_grouping.py` | 实例分组。使用屏障区域、空间邻近和颜色相似度通过并查集将邻近组件分组为逻辑实例 |
| `component_bridge_cut.py` | 桥接切割。检测并切割容器边界和内部图标/元素之间的细「桥」，拆分混合组件 |
| `component_geometry.py` | 组件几何工具。边界框几何辅助：bbox 提取、合并、间距/中心计算 |
| `component_stroke_features.py` | 描边特征提取。基于饱和度/亮度统计将组件分类为鲜艳色或彩色描边碎片 |
| `asset_alignment_runtime.py` | 资产对齐分析。通过将分割资产合成到画布上，检查与页面脚本文本框区域的重叠情况 |
| `asset_output_dir.py` | 资产输出目录准备。清理旧的资产 PNG/SVG 文件 |
| `asset_cleaner.py` | 资产清理器。平滑恢复父资产中被裁切给子图标的区域，填充残余伪影 |
| `manifest_paths.py` | 清单路径解析。从分割 manifest JSON 解析资产目录路径 |
| `intermediate_artifact_cleanup.py` | 中间产物清理。分割完成后移除中间的增强/透明 PNG 文件 |

---

### 5.5 模型集成模块 (`ppt_system/integrations/`)

封装与 OpenAI 兼容 API 的所有交互，提供对话和图像生成两大能力。

| 文件 | 职责 |
|------|------|
| `__init__.py` | 包初始化标记 |
| `openai_chat_provider.py` | **对话模型适配器**（299 行）。发送消息（文本+图像），处理 JSON 模式响应，支持重试策略（指数退避）、超时和模糊响应处理，兼容 OpenAI API 协议 |
| `openai_image_provider.py` | **图像模型适配器**（306 行）。处理 API 请求（含重试）、尺寸/分辨率/质量配置、图像下载/保存，支持扩展选项 |
| `model_config.py` | 多模型档案管理。读写 JSON 配置，支持 CRUD、激活模型切换，通过环境变量安全存储 API Key（`__ENV__` 占位符），提供活跃配置解析 |
| `model_connectivity.py` | 模型连通性测试。用轻量请求测试模型 API 端点，报告延迟和状态 |
| `http_retry_policy.py` | HTTP 重试策略。定义可重试 HTTP 状态码和传输错误分类 |
| `chat_response_parser.py` | 对话响应解析器。从 OpenAI 兼容的 Chat Completion 响应中提取文本内容，处理各种代理格式差异 |
| `image_prompt.py` | 图像 prompt 构建。基于风格类型（business、tech、visual、general）构建页面级图像生成 prompt，含硬编码风格引导 |
| `image_response.py` | 图像响应处理。解析图像 API 响应（b64_json 或 URL），下载图像并保存到磁盘 |
| `api_url.py` | API URL 标准化。规范化 API Base URL（协议、主机、路径去重、尾斜杠） |

---

### 5.6 任务管理模块 (`ppt_system/jobs/`)

负责任务状态的持久化、生命周期管理和并发控制。

| 文件 | 职责 |
|------|------|
| `__init__.py` | 包初始化标记 |
| `job_store.py` | **SQLite 任务存储**（171 行）。任务表 CRUD 操作（job_id、status、request/state/result JSON blob），Schema 自动迁移 |
| `active_job_registry.py` | 活跃任务注册表。线程安全的内存注册表，跟踪当前进程管理的任务（含 Future 绑定） |
| `job_interrupt_signal.py` | 任务中断信号。基于文件的协作中断机制：写入/检查/清除 `.job_stop_requested.json` 文件 |
| `job_delivery_state.py` | 任务交付状态管理。构建参考/可编辑交付载荷，标准化结果 JSON，跟踪交付 key/文件名/URL |
| `job_errors.py` | 任务错误定义。定义 `JobInterruptedError` 异常类 |
| `job_status_messages.py` | 状态消息常量。定义停止和中断状态的常量消息 |
| `job_targets.py` | 任务目标类型。定义目标类型（reference_only、editable_ppt）、阶段常量、终态映射和目标标签 |
| `concurrent_stage.py` | 并发阶段执行器。通用的 Future 排空工具，支持失败安全错误处理和补充回调 |
| `db_maintenance_scheduler.py` | DB 维护调度器。后台线程定时执行数据库维护（裁剪旧任务、VACUUM），基于可配置间隔 |
| `db_lifecycle.py` | 数据库生命周期工具。收集 DB 统计信息（大小、任务数、freelist），执行维护/裁剪和 VACUUM 操作 |

---

### 5.7 运行时工具模块 (`ppt_system/runtime/`)

提供跨模块共享的底层运行时工具。

| 文件 | 职责 |
|------|------|
| `__init__.py` | 包初始化标记 |
| `console_encoding.py` | 控制台编码。在 Windows 上配置 stdout/stderr 的 UTF-8 编码 |
| `env_loader.py` | 环境变量加载器。将 `.env` 文件加载到 `os.environ`（简单 key=value 解析器，不覆盖已有值） |
| `interruptible_execution.py` | 可中断执行。支持协作中断的可调用对象和子进程执行器（后台线程轮询 `stop_checker`） |
| `logging_utils.py` | 日志工具。格式化带时间戳和作用域前缀的日志行 |
| `time_utils.py` | 时间工具。UTC 时间戳工具函数：naive datetime、毫秒格式、ISO-8601 格式 |

---

### 5.8 Web 层 — 路由 (`ppt_system/web/blueprints/`)

Flask Blueprint 路由定义，负责 HTTP 请求分发。

| 文件 | 职责 |
|------|------|
| `__init__.py` | Blueprint 包初始化 |
| `jobs_api.py` | **任务 API Blueprint**。注册全部任务相关端点：创建、状态查询、SSE 流、历史列表、中断/续跑、交付导出、编辑操作、Agent 草案、图片编辑候选、DB 维护 |
| `config_api.py` | **配置 API Blueprint**。配置/模型配置 CRUD 端点：读取配置、列出/创建/更新/删除模型配置、测试连通性 |
| `artifacts_api.py` | **产物 API Blueprint**。任务运行文件服务（图片、PPTX、脚本），从 runs 目录提供文件下载 |
| `ui.py` | **UI Blueprint**。服务 SPA index.html 和公共静态资源（favicon、icons） |

---

### 5.9 Web 层 — 服务 (`ppt_system/web/services/`)

业务逻辑层，被 Blueprint 路由调用。

| 文件 | 职责 |
|------|------|
| `__init__.py` | 服务包初始化 |
| `jobs_api_service.py` | **任务 API 核心服务**。任务创建（从文本或外部图片）、状态获取、SSE 流式推送、历史列表、中断/续跑、交付导出、运行文件服务 |
| `job_pipeline_runner.py` | **全流水线编排器**（746 行）。按阶段推进 规划→原稿图→元素图→PPT 导出，支持并发、中断、阶段恢复和检查点跳过 |
| `job_state_runtime.py` | **任务状态管理核心**。读写任务状态 JSON，管理页面/阶段状态，处理错误/中断恢复，发射 SSE 事件 |
| `job_event_bus.py` | SSE 事件总线。基于 `threading.Condition` 的线程安全发布/订阅机制，跟踪每任务和历史版本号 |
| `job_snapshot_runtime.py` | 任务快照运行时。为 API 响应构建运行时任务载荷，包含交付状态、页面集合和交付动作解析 |
| `jobs_api_service` 依赖 | 以下是被 `jobs_api_service` 调用的子服务 |
| `job_operations_service.py` | 页面操作服务。单页文字/布局/样式编辑、Agent 指令、任务级风格调整，含操作历史记录 |
| `job_agent_draft_service.py` | Agent 草案服务。通过 LLM 或规则创建草案，应用已确认的编辑 |
| `job_agent_draft_model_planner.py` | Agent 草案 LLM 规划器。使用 LLM 从自然语言用户反馈中规划编辑草案，结合图像上下文、标注和对话历史 |
| `job_agent_draft_rule_planner.py` | Agent 草案规则规划器。非 LLM 回退方案：关键词匹配推断编辑类型、目标页面和操作类型 |
| `job_agent_draft_models.py` | Agent 草案模型。定义 `AgentDraft` 数据类（draft_id、operation_type、edit_kind、page_no、summary、changes、confidence） |
| `job_edit_planner.py` | 编辑规划器。将已确认的编辑应用到任务状态：文本内容变更、版式家族替换、风格调整，含 prompt 重新生成 |
| `job_image_edit_service.py` | 图片编辑服务。重新生成单个参考/元素图像，触发下游阶段重置 |
| `job_image_tasks.py` | 图像任务提交器。向 ThreadPoolExecutor 提交逐页图像生成任务（参考/元素），更新状态 |
| `job_stage_requeue.py` | 阶段重排队。当产物变更时重置下游 Pipeline 阶段，确定哪些阶段需要重新执行 |
| `job_artifact_paths.py` | 产物路径解析。从 URL 式引用解析任务产物文件路径，含安全检查（后缀白名单、目录 containment） |
| `job_runtime_limits.py` | 运行时限制。从配置解析限制：任务工作线程数和 LRU 状态缓存最大条目 |
| `job_submission_runtime.py` | 任务提交运行时。将已有任务提交到线程池，合并图像预设构建活跃配置 |
| `job_db_maintenance_service.py` | DB 维护服务。暴露 DB 统计信息，执行裁剪/真空操作 |
| `workflow_policy.py` | 工作流策略。定义工作流模式（auto/guided）、计划确认策略和阶段门控逻辑 |
| `plan_version_store.py` | 计划版本存储。管理可编辑的计划快照：提取、标准化和应用计划编辑（文本/布局/样式/丰富度/标题变更） |
| `external_reference_job.py` | 外部原稿图任务创建。从上传的外部参考图创建任务：调整/标准化图片，构建页面条目，设置交付目标 |
| `config_api_service.py` | 配置 API 服务。返回合并配置（含布局选项、风格遵循级别），处理模型配置 CRUD |
| `app_config_runtime.py` | 应用配置运行时。读取应用配置并从运行时模块解析图像预设 |
| `api_response.py` | API 响应辅助。标准化 Flask JSON 响应封装（`api_success`、`api_error`、`api_ok`） |
| `static_assets.py` | 静态资源版本。计算 CSS/JS 资源的内容哈希版本字符串（用于缓存失效） |

---

### 5.10 Web 层 — 应用入口 (`ppt_system/web/`)

| 文件 | 职责 |
|------|------|
| `__init__.py` | 包初始化，导出 `create_app` |
| `app.py` | **Flask 应用工厂**。注册 4 个 Blueprint（UI、配置 API、任务 API、产物 API），配置静态/模板目录，禁用浏览器缓存 |
| `runtime.py` | 运行时模块桥接。从 `sys.modules` 解析 `main` 运行时模块，用于共享后端状态访问 |

---

### 5.11 前端 — 入口与配置 (`web_ui/`)

| 文件 | 职责 |
|------|------|
| `index.html` | HTML 入口页面。标题「PPT Agent 工作台」，加载 `main.jsx`，定义 `#root` 挂载点 |
| `package.json` | 前端项目清单。依赖：React 19、Framer Motion、Lucide React、clsx；开发依赖：Vite 5、ESLint、@vitejs/plugin-react |
| `vite.config.js` | Vite 配置。React 插件，代理 `/api`、`/output`、`/runs` 到 `127.0.0.1:7860` |
| `eslint.config.js` | ESLint 扁平配置。强制 React Hooks 规则和 React Refresh for Vite |
| `src/main.jsx` | React 19 入口。在 `StrictMode` 中将 `<App />` 渲染到 `#root` DOM 节点 |
| `src/App.jsx` | 根组件。渲染 `<WorkspaceShell />` |
| `src/index.css` | 全局设计系统。CSS 变量（颜色、阴影、圆角）、排版、重置、滚动条和全部组件级 class 样式 |
| `src/App.css` | 遗留 Vite 脚手架 CSS，当前应用基本未使用 |

---

### 5.12 前端 — 布局组件 (`web_ui/src/components/Layout/`)

| 文件 | 职责 |
|------|------|
| `Header.jsx` | 顶部应用栏。品牌 Logo、当前任务标题/状态、设置按钮、任务启动切换、上下文感知操作按钮（创建/暂停/续跑/确认计划） |
| `SettingsModal.jsx` | 设置模态框。管理 OpenAI 兼容模型配置（对话 & 图像模型）：创建、编辑、激活、删除、测试连通性 |
| `Sidebar.jsx` | 左侧边栏。历史任务列表（交错动画）和「新任务」按钮，用于旧版布局 |
| `MainPanel.jsx` | 中间面板包装器。渲染 `<TaskConfigForm>` 查看/编辑任务参数，用于旧版布局 |
| `ResultPanel.jsx` | 右侧结果面板。阶段时间线（动画进度）、页面缩略图画廊、阶段日志模态框和下载链接，用于旧版布局 |

---

### 5.13 前端 — 工作区组件 (`web_ui/src/components/Workspace/`)

| 文件 | 职责 |
|------|------|
| `WorkspaceShell.jsx` | **工作区主壳**（310 行）。顶层编排器，管理所有全局状态（当前任务、页面选择、预览类型、工作流模式、任务启动、图片标注、计划确认），串联 Header、TaskCenter、AgentWorkspace/TaskLaunchPanel、PPTStudio 和模态框 |
| `TaskCenter.jsx` | 左侧面板。任务列表（置顶/历史分区）、内联重命名、置顶/取消置顶/删除的上下文菜单、风格参考查看器和资源链接占位 |
| `AgentWorkspace.jsx` | 中间面板。带标签页的工作区：「对话」（Agent 反馈 + 聊天 + 操作流）、「规划」（PlanningEditor）、「编辑」（逐页图像编辑含标注和候选生成/应用） |
| `TaskLaunchPanel.jsx` | 任务启动面板。动画面板显示源任务摘要、参数洞察，内嵌 `<CreationForm>` 配置任务参数 |
| `PPTStudio.jsx` | 右侧 PPT 预览工作室。幻灯片预览含图片类型切换、页面结构列表、导出区（生成/下载 PPTX）、续跑/中断/确认计划控制 |
| `CreationForm.jsx` | **任务创建表单**。来源模式（文本 prompt vs 外部参考图）、工作流模式切换、内容编辑器、页数、图像预设、质量、风格备注、逐页丰富度、风格遵循度、风格图上传；通过 `POST /api/jobs` 提交 |
| `ContentEditorDialog.jsx` | 内容编辑器对话框。可展开的全屏模态编辑器，含 `ContentCapacityPanel` 分析文本并根据内容密度推荐页数 |
| `PlanningEditor.jsx` | 完整计划编辑 UI。工具栏（保存/确认/添加页），全局计划字段（标题、受众、风格），和 `<PagePlanEditor>` 卡片列表 |
| `PagePlanEditor.jsx` | 逐页计划编辑器。基础字段（标题、布局、摘要、要点、视觉建议）和高级区域（参考/元素 prompt 覆盖），含重排/复制/删除控制 |
| `UnsavedPlanConfirmModal.jsx` | 未保存计划确认模态框。在确认生成前提示用户保存、丢弃或继续编辑未保存的计划变更 |
| `AgentChatPanel.jsx` | 多轮 Agent 聊天 UI。快捷 prompt、消息线程（用户/助手气泡）、待确认草案卡片（含可编辑指令）和清空对话功能 |
| `AgentFeedbackCard.jsx` | Agent 反馈卡片。可折叠卡片显示 Agent 生成的摘要和可点击的页面大纲网格 |
| `StageProgress.jsx` | 阶段进度条。可展开显示所有 Pipeline 阶段（规划、原稿图、元素图、PPT 导出）的状态图标、进度百分比和可选日志展开 |
| `ImageMarkupPanel.jsx` | 图片标注面板。全屏面板通过指针拖拽在幻灯片图片上绘制矩形标注框，标注与 Agent 聊天同步用于空间「这里/那里」引用 |
| `ImagePreviewSwitch.jsx` | 图片预览切换。分段切换器在页面的参考/元素/预览图片类型之间切换 |
| `SlideImage.jsx` | 通用图片展示组件。加载/错误/空状态，变体模式（预览 vs 缩略图），可选元数据覆盖（来源标签、尺寸） |
| `ImageUploadPreviewList.jsx` | 多文件图片上传器。带缩略预览的图片上传，拖拽添加和单张删除，管理对象 URL 生命周期 |
| `TaskActionMenu.jsx` | 任务操作菜单。Portal 定位下拉菜单，自动相对锚点元素定位，处理外部点击关闭 |
| `TaskMetaInfo.jsx` | 任务元数据标签。状态·页数·时间的 chip 组件，hover 时通过 Portal 显示详细任务信息 |
| `TaskSkeletonList.jsx` | 骨架屏加载占位。初始数据加载时渲染闪光动画的任务卡片占位 |
| `WorkflowModeSwitch.jsx` | 工作流模式切换。双选项 radio（auto/guided），带动画滑动指示器和弹性过渡 |
| `StyleReferenceViewer.jsx` | 风格参考查看器。Portal 模态框显示任务的风格参考图，含主舞台和缩略侧栏 |
| `FeaturePending.jsx` | 功能待实现提示。显示扳手图标的小信息卡片，可自定义标题和消息 |

---

### 5.14 前端 — 表单与动画组件

| 文件 | 职责 |
|------|------|
| `components/Forms/TaskConfigForm.jsx` | 任务配置表单。手风琴折叠式表单，包含任务参数（内容、输出规格、风格约束），用于旧版布局的 MainPanel，含全屏内容编辑器模态框 |
| `components/Motion/MotionUI.jsx` | Framer Motion 原语。`FadeIn`（淡入+滑动）、`StaggerContainer`/`StaggerItem`（交错列表动画，支持 reduced-motion）和 `ScaleButton`（弹性 hover/tap 反馈） |

---

### 5.15 前端 — 自定义 Hooks (`web_ui/src/hooks/`)

| 文件 | 职责 |
|------|------|
| `useJobs.js` | 任务列表 Hook。从 `GET /api/jobs` 获取任务列表，订阅 `EventSource /api/jobs/stream` 实时更新，暴露 `{ jobs, loading, setJobs, refreshJobs }` |
| `useJobDetail.js` | 单任务详情 Hook。通过 REST + SSE 流（`/api/jobs/:id` + `/api/jobs/:id/stream`）获取单任务，处理状态转换时的流重启，暴露 `{ job, loading, error, setJob }` |
| `useJobActions.js` | 任务操作 Hook。通用的任务操作/提交 Hook，跟踪 pending key 和错误状态，通过 `onJobUpdated` 回调返回响应 |
| `useAgentDraft.js` | Agent 草案 Hook。发送 Agent 草案请求（`POST /api/jobs/:id/agent/draft`），跟踪多轮聊天工作流的 pending/error 状态 |
| `usePlanningDraft.js` | 计划草稿 Hook。复杂 Hook 管理计划草稿生命周期：从 API 加载计划，通过 reducer 跟踪本地编辑（基于指纹比较的脏检测），提供保存/确认/丢弃操作 |
| `useConfig.js` | 配置 Hook。挂载时从 `GET /api/config` 获取应用配置，暴露 `{ config, loading, error }` |
| `useModelConfigs.js` | 模型配置 Hook。模型配置 CRUD 操作（列出、保存、激活、删除、测试连通性），通过 `/api/model-configs` 端点 |

---

### 5.16 前端 — 工具函数 (`web_ui/src/utils/`)

| 文件 | 职责 |
|------|------|
| `jobActions.js` | API 客户端函数。所有任务相关端点的请求封装：提交操作、获取/更新/确认计划、提交操作、Agent 草案、图片编辑候选、清空对话 |
| `jobPresentation.js` | 任务展示辅助。状态/阶段标签、任务标题推导、页面合并（plan + reference + element 产物）、图片 URL 解析、页面摘要、操作格式化、进度计算、Agent 摘要构建 |
| `jobStateMerge.js` | 任务状态深度合并。处理对象字段合并、阶段数组按 key/index 合并、交付结果失效时清除交付动作 |
| `planningDraft.js` | 计划数据标准化。`normalizePagePlan`（强制所有字段为安全类型）、`normalizePlan`、`renumberPlanPages`、`createBlankPagePlan` |
| `contentCapacity.js` | 内容容量分析。分析输入文本推荐页数：统计字符/单元/信号、检测列表标记、通过关键词评分构建大纲条目、评估页数过低的风险级别 |
| `imageEditCandidates.js` | 图片编辑候选过滤。按页码和预览类型过滤/排序图片编辑候选，返回最新候选并检查是否已应用 |
| `workflowMode.js` | 工作流模式常量与辅助。定义 auto（一键）和 guided（先规划）模式的标签、标准化和 `isAwaitingPlanConfirmation` 检查 |
| `topbarTaskAction.js` | 顶栏操作按钮推导。从当前任务状态和待处理操作推导上下文顶栏操作按钮状态（创建/暂停/续跑/确认计划） |
| `resumeControl.js` | 恢复控制状态。从任务提取恢复控制状态：确定可见性、是否允许恢复、是否等待停止以及适当的标签/消息 |
| `taskLaunchSummary.js` | 任务启动摘要。构建任务启动参数的紧凑摘要（工作流模式、页数、目标、图像预设、质量、风格参考） |
| `taskLaunchInsights.js` | 参数洞察生成。生成人类可读的参数洞察卡片，解释每个配置选择对用户意味着什么 |
| `taskLaunchLabels.js` | 任务启动标签常量。按钮标签字符串（「基于当前参数新建任务」「创建任务参数」「收起参数」） |
| `generationParameterLabels.js` | 参数标签映射。生成参数标签查询：任务目标、图像质量、丰富度级别、风格遵循度，含统一的 `getGenerationParameterLabel` 调度器 |
| `generationOptions.js` | 生成选项工具。布尔选项解析工具和 `resolveIncludeCoverPage` 函数，从配置+任务元数据确定封面页生成（含优先级） |
| `titleExtraction.js` | 标题提取。从原始内容文本提取短展示标题：处理 HTML 标题、显式标题行和启发式标题检测（含字符限制） |
| `contentCapacity.test.js` | 内容容量测试。验证短结构内容推荐页数、高密度长内容风险评估和最大页数限制 |
| `imageEditCandidates.test.js` | 图片编辑候选测试。验证相同时间戳和不同时间戳候选的正确排序 |
| `jobStateMerge.test.js` | 状态合并测试。验证失效时交付结果清除、摘要更新时保留详情和隐藏过期下载动作 |

---

### 5.17 维护工具 (`tools/`)

| 文件 | 职责 |
|------|------|
| `assemble_assets_only_ppt.py` | CLI 工具。仅组装元素层资产（无文本）的 PPTX，读取每页 `assets.json` 清单并将裁切图片定位到空白幻灯片上 |
| `assemble_preview_ppt_from_assets.py` | CLI 工具。将生成的文字布局 Python 脚本与每页资产清单组合，生成带图片和文本覆盖的完整预览 PPTX |
| `continue_from_reference_image.py` | CLI 工具。将外部参考图登记为任务原稿图并继续转换流水线（元素图生成→PPT 导出），支持恢复已有任务 |
| `inspect_layered_ppt.py` | 诊断脚本。使用文字脚本运行时创建最小分层 PPTX 演示（资产层+文本层分离），检查并打印幻灯片结构 |
| `reconstruct_transparent_pages_from_assets.py` | CLI 工具。通过使用 `assets.json` 清单的位置信息将单独裁切的资产 PNG 合成回透明画布，重建全页透明元素 PNG |
| `render_preview_from_script.py` | CLI 工具。复用已有的页面级 Python 脚本，替换工作目录路径后执行构建 PPTX，渲染首张幻灯片为 PNG 预览并生成并排对比图 |
| `rerun_transparent_asset_split.py` | CLI 工具。在已有的透明页面图上重新运行资产分割/裁切流程，支持可配置的合并距离和 Alpha 阈值参数 |

---

### 5.18 辅助脚本 (`scripts/`)

| 文件 | 职责 |
|------|------|
| `create_page02_text_ppt.py` | 独立脚本。使用硬编码的像素级文本框规格（标题、编号段落、项目列表）手动重建第 2 页的文本覆盖 PPTX，用于手动微调 |
| `create_page02_text_ppt_from_images_only.py` | 独立脚本。类似上述脚本，但文本定位/颜色值略有不同，合并了单个 `•` 标记与其文本 |

---

### 5.19 测试文件 (`tests/`)

项目包含 52 个测试文件，覆盖所有核心模块：

| 文件 | 测试范围 |
|------|----------|
| `test_alpha_edge_trim.py` | Alpha 边缘修剪模块：收紧半透明杂散像素、移除背景类外缘同时保留不透明描边 |
| `test_alpha_matte_refinement.py` | Alpha 蒙版精修：视觉白掩码检测、背景模型构建、颜色引导的 Alpha 蒙版精修 |
| `test_asset_alignment_runtime.py` | 资产对齐运行时：检测文本占位框与裁切资产图片的重叠 |
| `test_asset_cleaner.py` | 资产清理器：`restore_removed_regions` 函数用背景填充色重绘被移除的图标/元素区域 |
| `test_component_color_grouping.py` | 颜色聚类：合并共享相似颜色的邻近图像碎片 |
| `test_concurrent_stage.py` | 并发阶段：`drain_fail_safe_futures` 正确收集成功/错误并支持补充回调 |
| `test_config_api_reference_style_adherence.py` | 配置 API：通过配置 API 读写 `reference_style_adherence` 和 `page_richness` 字段 |
| `test_cover_page_option.py` | 封面页选项：禁用封面页强制首页为 body 模式，`normalize_content_plan` 尊重该设置 |
| `test_editable_delivery_cache.py` | 交付缓存：当 bundle 未变化时缓存和复用先前生成的可编辑 PPTX |
| `test_export_artifact_policy.py` | 产物策略：PPTX 原子保存、轮预览产物构建/清理、文件内容签名检查 |
| `test_export_options.py` | 导出选项：`build_export_options` 正确读取 `export_page_concurrency` 并强制最小值 |
| `test_export_page_resume.py` | 导出页面恢复：已完成页面跳过、中断页面在续跑时重新导出 |
| `test_external_reference_job_api.py` | 外部参考图 API：上传参考图、创建任务、验证任务状态转换 |
| `test_guided_workflow_api.py` | 引导工作流 API：计划生成、计划确认/拒绝、规划与执行之间的状态转换 |
| `test_image_response.py` | 图像响应：data URI 解码、HTTP 响应和 URL 字符串的图像字节解析、payload 到文件保存 |
| `test_image_retry_policy.py` | 图像重试策略：各种 HTTP 错误码（429/500/502/503）、传输错误（超时/断连）和模糊失败的重试逻辑 |
| `test_interruptible_execution.py` | 可中断执行：`run_interruptible_call` 正确返回结果或在停止请求时抛出 `JobInterruptedError` |
| `test_job_api_page_richness.py` | 任务 API 页面丰富度：逐页丰富度级别（low/medium/high）和 `page_richness_map` 参数处理 |
| `test_job_artifact_paths.py` | 产物路径：接受 run-relative、job-relative 和绝对路径，拒绝路径遍历攻击 |
| `test_job_db_maintenance_api.py` | DB 维护 API：手动触发任务数据库维护 |
| `test_job_db_maintenance_scheduler.py` | DB 维护调度器：配置解析（默认值、边界、负值钳制）和调度维护触发生命周期 |
| `test_job_delivery_state.py` | 交付状态：`merge_job_result`（增量 vs 重置）和 `attach_delivery_actions`（构建交付动作元数据） |
| `test_job_event_bus.py` | 事件总线：任务变更通知的发布/订阅和历史版本推进 |
| `test_job_interrupt_api.py` | 中断 API：各种任务状态下的中断/停止请求和阶段特定行为 |
| `test_job_manage_api.py` | 任务管理 API：任务列表、详情获取、置顶/取消置顶和删除操作 |
| `test_job_operations_api.py` | 操作 API：任务重跑、升级为可编辑、可编辑交付导出和交付重置 |
| `test_job_runtime_limits.py` | 运行时限制：`BoundedJobStatusCache` LRU 淘汰和刷新、工作线程数和缓存大小配置解析 |
| `test_job_snapshot_runtime.py` | 快照运行时：`build_job_payload` 正确保留图片编辑候选并构建可序列化载荷 |
| `test_job_store.py` | 任务存储：SQLite CRUD 操作的字段持久化和检索验证 |
| `test_layout_family_registry.py` | 版式家族注册表：所有注册家族有槽位模板、选项元数据和一致标签 |
| `test_model_config_env_storage.py` | 模型配置环境存储：`.env` 密钥读写、配置 upsert 和环境变量注入 |
| `test_model_connectivity.py` | 模型连通性：chat 和 image 模型连通性检查端点及错误处理 |
| `test_openai_chat_provider.py` | 对话提供者：消息构建、重试逻辑、JSON 提取、超时处理和配置清理 |
| `test_page_image_pipeline.py` | 图像流水线：两阶段编排验证（元素图在每页原稿图完成后交错启动） |
| `test_page_richness.py` | 页面丰富度：逐页丰富度解析及其与 `normalize_content_plan` 和生成选项的集成 |
| `test_plan_prompt_sync.py` | 计划同步：`apply_plan_to_state` 将计划编辑同步回任务状态页面 |
| `test_planning_state.py` | 规划状态：占位符 vs 完整页面规划检测，确保不完整规划不被视为可恢复 |
| `test_reference_prompt_shape_constraints.py` | 参考图形状约束：compact/compressed prompt 正确包含/排除虚线、连接线类型和布局槽位描述 |
| `test_reference_task_guard.py` | 参考任务守卫：`submit_reference_task` 和 `submit_elements_task` 在空 prompt 时拒绝 API 调用 |
| `test_source_content_anchors.py` | 源内容锚点：从源内容中提取和保留关键事实（数字、日期、名称） |
| `test_splitter.py` | 分割器：`split_transparent_png` 的组件检测、合并、Alpha 阈值处理和 manifest 生成 |
| `test_stage_labels.py` | 阶段标签：内置阶段标签映射和 `normalize_stage_label` 修复损坏 `????` 标签 |
| `test_stage_resume.py` | 阶段恢复：`should_run_stage` 和 `reconcile_completed_stages` 判断哪些阶段需要重跑 |
| `test_stage1_reference_defaults.py` | Stage 1 默认值：当计划指定 `reference_style_adherence` 时正确覆盖遗留 `image_prompt` 字段 |
| `test_style_runtime_and_evaluator.py` | 风格运行时与评估器：style_guide 遵从评分正确识别违规（错误颜色、缺少元素、不一致布局） |
| `test_text_placeholder_detection.py` | 文本占位符检测：通过参考图和元素图差异检测文本占位符边界框 |
| `test_text_script_agent.py` | 文字脚本 Agent：端到端测试 prompt 构建、脚本标准化、资产调整解析、逐页修正和检查点恢复 |
| `test_text_script_empty_content.py` | 空内容过滤：`normalize_page_script` 过滤空/纯空白文本内容 |
| `test_title_extraction.py` | 标题提取：从 HTML 标题、显式标题行和纯文本推导任务标题，含默认回退 |
| `test_web_job_state_labels.py` | Web 任务状态标签：`enrich_job_state_with_record` 修复损坏标签并合并 DB 记录运行时状态 |
| `test_workflow_policy.py` | 工作流策略：工作流模式标准化、确认策略构建和计划确认状态转换 |
| `image_transport_diagnose.py` | 图像传输诊断（非单元测试）。测试图像 API 连通性，发送真实生成请求并测量下载/解码时间 |

---

## 6. 数据流与存储

### 6.1 任务生命周期

```
创建 → 规划中 → 原稿图生成中 → 元素图生成中 → 导出中 → 完成
                                                    ↓
                                              可中断/暂停
                                                    ↓
                                              续跑/恢复
```

### 6.2 任务目录结构 (`output/<job_id>/`)

```
output/<job_id>/
├── status.json                         # 任务阶段状态、操作记录、Agent 对话
├── job.json                            # 内容、规划、原稿图 URL、元素图 URL 等快照
├── 01_reference_pages/                 # 带文字原稿图
│   ├── page_01.png
│   └── ...
├── 02_elements_pages/                  # 去文字元素图
│   ├── page_01.png
│   └── ...
├── 03_ppt_build/                       # PPT 导出工作目录
│   ├── generated_text_layout.py        # AI 生成的文字布局脚本
│   ├── editable_delivery.bundle.json   # 交付清单
│   ├── page_01/assets/
│   │   ├── assets.json                 # 分割后的元素资产清单
│   │   └── asset_001.png               # 分割后的独立元素 PNG
│   ├── page_01/text_placeholders.json  # 原稿图与元素图差分得到的文字占位框
│   ├── page_01/page_export_checkpoint.json
│   └── page_01/step_checkpoints/       # LLM 子步骤检查点
├── 04_image_edits/                     # 图片编辑候选
├── versions/                           # 页面版本备份
└── <job_name>.pptx                     # 最终分层 PPTX
```

`03_ppt_build/page_XX/preview_pptx/`、`preview_images/`、`preview_comparisons/` 以及旧式
`render_preview_round_*.pptx`、`office_preview_round_*.png/.PNG`、`comparison_round_*.png`
只属于真实回看轮的短生命周期临时产物。常规导出会在当前轮渲染、回看修正或异常退出后立即清理它们；`comparison_round_*.png`
不再由主流程默认生成。透明化阶段只把当前透明图作为切分输入，不再额外落盘
`page_XX_transparent_preview.png` 调试副本。

### 6.3 全局存储

| 存储 | 位置 | 说明 |
|------|------|------|
| 任务数据库 | `output/jobs.sqlite3` | SQLite，存储任务历史与状态 |
| 全局配置 | `config.json` + `config.local.json` | 模型、并发、重试等配置 |
| 环境变量 | `.env` | API Key 安全存储，不入库 |
| 模型缓存 | `output/model_cache/` | 项目内模型缓存 |

---

## 7. 设计原则

- **单一导出路径**：只保留 `direct_office_refine`，无 legacy 回退
- **双轮闭环校正**：首轮生成+二轮修正，确保文字与原稿一致
- **设计语法约束**：≥3 种版式家族，相邻页不重复
- **断点续跑**：所有阶段支持检查点恢复，中断信号线程安全
- **中间产物轻量化**：只持久化重导出/续跑必需资产；透明化预览副本不落盘，真实回看 PPTX/PNG 用完即清理
- **安全设计**：API Key 仅存 `.env`，文字脚本沙箱执行，白名单校验
- **文本框规范**：始终 `MSO_AUTO_SIZE.NONE`，避免自动调整偏移

---

## 8. 并发与性能

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `stage1_concurrency` | 10 | 原稿图并发生成数 |
| `stage2_concurrency` | 10 | 元素图并发生成数 |
| `export_page_concurrency` | 10 | 导出阶段并发页面数 |
| `job_worker_count` | 2 | 任务工作线程数 |
| `request_retry_count` | 4 | API 请求重试次数 |
| `request_retry_initial_delay_seconds` | 6 | 重试初始延迟（指数退避） |
| `request_timeout_seconds` | 180 | 单次 API 请求超时 |

---

## 9. API 端点总览

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/jobs` | 创建生成任务（文本 / 外部原稿图） |
| `GET` | `/api/jobs` | 获取任务列表 |
| `GET` | `/api/jobs/:id` | 获取单任务详情 |
| `GET` | `/api/jobs/:id/stream` | SSE 实时进度推送 |
| `POST` | `/api/jobs/:id/interrupt` | 中断任务 |
| `POST` | `/api/jobs/:id/resume` | 续跑任务 |
| `POST` | `/api/jobs/:id/deliver` | 重新导出交付版本 |
| `DELETE` | `/api/jobs/:id` | 删除任务 |
| `POST` | `/api/jobs/:id/operations` | 提交页面操作 |
| `POST` | `/api/jobs/:id/agent/draft` | 生成 Agent 修改草案 |
| `POST` | `/api/jobs/:id/image-edit-candidates` | 生成图片编辑候选 |
| `GET` | `/api/config` | 获取全局配置 |
| `PUT` | `/api/config` | 更新全局配置 |
| `GET` | `/api/model-configs` | 获取模型配置列表 |
| `POST` | `/api/model-configs` | 创建模型配置 |
| `PUT` | `/api/model-configs/:id` | 更新模型配置 |
| `DELETE` | `/api/model-configs/:id` | 删除模型配置 |
| `POST` | `/api/model-configs/:id/test` | 测试模型连通性 |
| `GET` | `/api/artifacts/:job_id/:path` | 下载任务产物 |

---

## 10. 部署与运行

### 开发环境

```bash
# 后端
pip install -r requirements.txt
python main.py                    # Flask 服务 :7860

# 前端（开发模式）
cd web_ui && npm install && npm run dev   # Vite :5173，API 代理到 :7860
```

### 生产环境

```bash
# 构建前端
cd web_ui && npm install && npm run build && cd ..

# 启动服务（Flask 托管前端 dist）
python main.py                    # 访问 http://127.0.0.1:7860
```

### 环境变量

```env
# 对话模型
PPT_SYSTEM_CHAT_<CONFIG_ID>_OPENAI_COMPATIBLE_BASE_URL=https://api.openai.com/v1
PPT_SYSTEM_CHAT_<CONFIG_ID>_OPENAI_COMPATIBLE_API_KEY=sk-xxx

# 图像模型
PPT_SYSTEM_IMAGE_<CONFIG_ID>_OPENAI_COMPATIBLE_BASE_URL=https://api.openai.com/v1
PPT_SYSTEM_IMAGE_<CONFIG_ID>_OPENAI_COMPATIBLE_API_KEY=sk-xxx
```

### 测试

```bash
python -m pytest -q
```
