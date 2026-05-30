# 前端元素编辑页开发清单

## 目标

为现有 PPT 生成系统新增一个独立的前端编辑页，允许用户在任务生成完成后，对每页切分元素进行二次编辑，并在重新导出 PPT 后看到对应视觉效果。

第一阶段只解决以下需求：

- 在前端单独页面中查看某个任务的所有可编辑页
- 选中单页中的切分元素
- 对元素执行换色、透明度调整、渐变叠加
- 保存编辑结果并支持再次打开继续编辑
- 基于编辑结果重新导出 PPT，并保证 PPT 打开后能看到相应效果

第一阶段暂不追求以下能力：

- 元素在 PPT 内继续以原生 shape 形式可编辑
- SVG 真矢量化输出
- 局部笔刷、任意蒙版、多断点复杂渐变、混合模式系统化编辑
- 完整撤销重做历史


## 现状分析

当前系统已经具备“元素级导出”的基础，但还没有“元素级前端编辑”的链路。

现有关键基础：

- `ppt_system/image/splitter.py`
  - 已能把透明元素图按连通域切分为多个 `asset_xxx.png`
  - 已输出 `assets.json`，包含元素位置、尺寸、面积等元数据
- `ppt_system/export/direct_project_script.py`
  - 已按页准备分割资产
  - 已将资产清单用于后续导出
- `ppt_system/export/text_script_runtime.py`
  - 当前通过 `add_assets(...)` 将分割后的 PNG 资产逐个放入 PPT
- `ppt_system/web/`
  - 已具备任务详情、任务历史、导出结果、任务操作、Agent 草案和图片编辑候选接口
  - 当前尚未暴露“某页元素资产清单”和“编辑结果保存”接口
- `web_ui/`
  - 当前 React/Vite 前端已有任务创建、结果查看、对话/编辑工作区和图片标注编辑，没有独立元素样式编辑页

当前能力边界：

- 文字是可编辑文本框
- 图形元素本质是图片资产，不是原生矢量 shape
- 因此前端编辑最适合先落在“位图元素样式编辑”上


## 总体方案

建议新增一个独立的前端编辑页，而不是把编辑器直接塞进当前首页。

页面组织建议：

- `/`
  - 现有任务创建与结果查看页
- `/editor/<job_id>`
  - 新增任务级元素编辑页
- `/editor/<job_id>?page=2`
  - 可选，用于默认打开指定页

整体思路：

1. 保留当前导出过程中生成的原始切分资产，不直接修改原图文件
2. 为每一页新增一份“元素编辑参数”文件
3. 前端编辑时只修改“参数”，不改原始资产
4. 后端基于“原始资产 + 编辑参数”实时合成预览图
5. 重新导出 PPT 时，后端按相同规则处理元素，再写入 PPT

这样做的收益：

- 保证原始切分资产可回溯
- 编辑结果可重复打开、继续修改
- 后续可继续扩展位置、缩放、显隐、层级、阴影、描边等参数
- 不与当前生成链路强耦合


## 第一阶段范围

### 必做

- 独立编辑页路由与前端页面
- 任务页跳转到编辑页
- 读取某页资产清单
- 元素列表展示
- 元素属性编辑
  - 显示/隐藏
  - 透明度
  - 纯色换色
  - 双色线性渐变
- 编辑结果保存
- 后端生成预览图
- 基于编辑结果重新导出 PPT

### 可延后

- 多选批量编辑
- 拖拽改变位置
- 缩放、旋转
- 图层顺序调整
- 撤销/重做
- 模板化样式复用
- 向 SVG 或原生 shape 演进


## 目录与文件建议

遵循“优先新增文件、模块解耦”的原则，建议新增以下文件：

### 前端

- `web_ui/src/components/ElementEditor/ElementEditorPage.jsx`
  - 编辑页主体
- `web_ui/src/components/ElementEditor/ElementCanvas.jsx`
  - 画布预览与元素选中
- `web_ui/src/components/ElementEditor/ElementPropertyPanel.jsx`
  - 元素属性面板
- `web_ui/src/hooks/useElementEditor.js`
  - 编辑页数据加载、保存、预览和导出编排
- `web_ui/src/utils/elementEditorApi.js`
  - 编辑页 API 访问封装
- `web_ui/src/utils/elementEditorState.js`
  - 编辑模型默认值、选中态和脏状态处理

### 后端

- `ppt_system/web/services/editor_manifest_service.py`
  - 负责把现有 `assets.json` 转换为前端可消费的编辑清单
- `ppt_system/web/services/editor_store.py`
  - 负责编辑结果的读写
- `ppt_system/web/services/editor_models.py`
  - 负责编辑数据结构归一化、校验与默认值补全
- `ppt_system/web/services/editor_preview.py`
  - 负责根据元素编辑参数渲染单页预览图
- `ppt_system/web/services/editor_export.py`
  - 负责基于编辑结果生成导出所需的处理后资产

### 可能复用的现有模块

- `ppt_system/image/splitter.py`
- `ppt_system/export/export_pipeline.py`
- `ppt_system/export/direct_project_script.py`
- `ppt_system/export/text_script_runtime.py`


## 任务目录落地建议

建议在每个任务目录下新增 `editor/` 子目录，用来保存编辑期数据，避免污染现有导出物。

建议结构：

```text
output/<job_id>/
  status.json
  job.json
  01_reference_pages/
  02_elements_pages/
  03_ppt_build/
    page_01/
      assets/
        assets.json
        asset_001.png
        asset_002.png
  editor/
    page_01.edits.json
    page_02.edits.json
    previews/
      page_01_preview.png
      page_02_preview.png
    export_cache/
      page_01/
        asset_001.rendered.png
        asset_002.rendered.png
```

说明：

- `03_ppt_build/page_xx/assets/` 保持当前导出切分结果，不改
- `editor/page_xx.edits.json` 保存用户编辑参数
- `editor/previews/` 保存前端调用预览接口后生成的预览图
- `editor/export_cache/` 保存导出前按编辑参数渲染后的资产缓存


## 数据模型设计

第一阶段推荐以“页级清单 + 元素级样式参数”的方式组织。

### 页级编辑清单

```json
{
  "job_id": "abc123",
  "page_no": 1,
  "canvas": {
    "width": 2000,
    "height": 1125
  },
  "assets": [
    {
      "asset_id": "1",
      "source_file": "asset_001.png",
      "name": "asset_001.png",
      "visible": true,
      "z_index": 1,
      "position": {
        "left": 120,
        "top": 80,
        "width": 300,
        "height": 180
      },
      "style": {
        "opacity": 1.0,
        "tint": {
          "enabled": false,
          "color": "#2F6DF6",
          "strength": 0.85
        },
        "gradient": {
          "enabled": false,
          "type": "linear",
          "angle": 45,
          "stops": [
            {
              "offset": 0.0,
              "color": "#2F6DF6",
              "alpha": 1.0
            },
            {
              "offset": 1.0,
              "color": "#7CC6FF",
              "alpha": 1.0
            }
          ]
        }
      }
    }
  ]
}
```

### 设计原则

- `position` 第一阶段先从原始资产复制，先不开放拖拽改位置时也能复用
- `style` 中每个字段都应有默认值，便于前后端稳定处理
- `asset_id` 建议直接使用切分清单中的 `index`，避免额外映射成本
- 后续如果支持 `vector` 元素，可扩展为：
  - `asset_type: "raster" | "vector"`


## 接口设计

建议新增一组编辑专用接口，不改现有任务生成主接口。

### 页面入口

- `GET /editor/<job_id>`
  - 返回独立编辑页模板

### 任务页概览

- `GET /api/jobs/<job_id>/editable-pages`
  - 返回该任务有哪些页可编辑
  - 响应字段建议：
    - `job_id`
    - `pages[]`
      - `page_no`
      - `title`
      - `reference_image`
      - `elements_image`
      - `asset_count`
      - `preview_image`

### 单页资产读取

- `GET /api/jobs/<job_id>/pages/<page_no>/assets`
  - 返回：
    - 原始资产清单
    - 已保存编辑参数
    - 合并后的前端编辑模型

### 保存编辑结果

- `PUT /api/jobs/<job_id>/pages/<page_no>/edits`
  - 请求体：
    - 单页完整编辑模型，或仅 `assets[]` 编辑部分
  - 行为：
    - 执行字段校验与默认值补全
    - 落盘到 `editor/page_xx.edits.json`

### 实时预览

- `POST /api/jobs/<job_id>/pages/<page_no>/preview`
  - 请求体：
    - 当前页编辑模型
  - 行为：
    - 后端基于编辑参数合成预览图
    - 返回预览图 URL 和版本号

### 重新导出

- `POST /api/jobs/<job_id>/export-from-edits`
  - 行为：
    - 读取所有页编辑结果
    - 生成处理后资产
    - 重新走导出链路
    - 产出新的 PPT 文件

### 可选扩展接口

- `POST /api/jobs/<job_id>/pages/<page_no>/reset-edits`
  - 将单页恢复到默认样式
- `POST /api/jobs/<job_id>/reset-all-edits`
  - 将整个任务恢复到默认样式


## 前端页面设计

建议使用三栏布局。

### 左栏：页列表

展示内容：

- 所有可编辑页
- 页缩略图
- 页标题
- 当前页是否已保存
- 当前页是否存在未保存修改

交互：

- 点击切换页
- 支持根据 URL 参数直接定位当前页

### 中栏：画布预览区

展示内容：

- 当前页完整合成预览
- 可选显示原稿图 / 去文字元素图 / 编辑后效果 三种视图切换

交互：

- 点击元素选中
- 鼠标悬停高亮元素边框
- 后续可扩展拖拽和缩放

### 右栏：属性面板

第一阶段只放以下控件：

- 元素名称
- 显示开关
- 透明度滑杆
- 换色开关
- 颜色选择器
- 染色强度滑杆
- 渐变开关
- 渐变角度
- 渐变起点颜色
- 渐变终点颜色
- 保存按钮
- 重新导出按钮


## 前端状态拆分建议

建议不要把编辑页逻辑全部塞进一个 `editor.js`，而是拆成几个职责明确的模块。

### `editor_state.js`

负责：

- 当前任务信息
- 当前页编号
- 当前页资产清单
- 当前选中元素
- 未保存状态
- 预览版本号

### `editor_api.js`

负责：

- 请求页列表
- 请求单页资产
- 保存单页编辑结果
- 请求预览图
- 触发重新导出

### `editor_renderer.js`

负责：

- 渲染页列表
- 渲染预览画布
- 渲染元素列表
- 渲染属性面板
- 绑定用户交互

### `editor.js`

负责：

- 页面初始化
- URL 参数解析
- 模块编排


## 后端实现建议

### 1. 清单归一化层

新增 `ppt_system/editor_manifest.py`

职责：

- 读取 `03_ppt_build/page_xx/assets/assets.json`
- 将原始资产清单转换成前端编辑模型
- 将原始资产和用户已保存编辑结果合并

输出要求：

- 字段完整
- 默认值稳定
- 不依赖前端补默认值

### 2. 编辑结果存储层

新增 `ppt_system/editor_store.py`

职责：

- 定位任务下 `editor/` 目录
- 读写 `page_xx.edits.json`
- 管理预览图与导出缓存路径

注意点：

- 读写都要容忍文件尚不存在
- 保存时避免只存前端局部字段导致后续字段缺失

### 3. 数据模型层

新增 `ppt_system/editor_models.py`

职责：

- 定义默认编辑模型
- 归一化布尔值、数值范围、颜色值
- 校验渐变数据结构

重点校验规则：

- `opacity` 取值范围 `0 ~ 1`
- `tint.strength` 取值范围 `0 ~ 1`
- `gradient.stops` 至少两个点
- `offset` 取值范围 `0 ~ 1`
- 颜色统一规范为 `#RRGGBB`

### 4. 预览渲染层

新增 `ppt_system/editor_preview.py`

职责：

- 读取单个原始元素 PNG
- 按编辑参数处理颜色、透明度、渐变
- 将处理后的元素重新叠加成整页预览图

建议实现顺序：

1. 支持显隐
2. 支持透明度
3. 支持单色染色
4. 支持双色线性渐变

渲染原则：

- 尽量复用原始 alpha
- 不直接改原文件
- 预览逻辑和导出逻辑尽量共用

### 5. 导出接入层

新增 `ppt_system/editor_export.py`

职责：

- 读取所有页的编辑模型
- 将每个元素渲染成处理后的 PNG
- 生成新的资产目录或缓存目录
- 在重新导出时替换原始资产路径

推荐接入点：

- 尽量不要改动 `splitter.py`
- 优先在 `export_pipeline.py` 或 `direct_project_script.py` 的资产准备阶段加一个“编辑结果覆盖层”


## 导出链路改造建议

第一阶段不建议推翻现有导出链路，只做一层增强。

推荐方案：

1. 保持 `03_ppt_build/page_xx/assets/assets.json` 作为原始切分结果
2. 在重新导出时，为每页生成一份“渲染后资产缓存”
3. 导出脚本读取缓存后的 PNG，而不是原始 PNG
4. 元素位置仍沿用原始清单中的位置数据

推荐实现方式：

- 在 `editor_export.py` 中输出：
  - `rendered_assets.json`
  - `asset_001.rendered.png`
  - `asset_002.rendered.png`
- 导出时把 manifest 路径切换到渲染后版本

这样可以保证：

- 普通任务导出链路不受影响
- 编辑后重新导出可以复用同一套 PPT 组装逻辑


## 效果实现建议

### 换色

推荐使用“保留原始明暗关系的染色”而不是简单纯色覆盖。

建议方式：

- 读取 RGBA
- 使用 alpha 作为有效区域
- 保留亮度或灰度结构
- 将目标色按 `strength` 与原始亮度信息混合

收益：

- 比简单覆盖更自然
- 对一类图形元素更通用，不依赖某张特定图

### 透明度

直接对 alpha 通道整体乘以 `opacity`。

优点：

- 实现简单
- 与 PPT 最终效果一致性高

### 渐变

第一阶段建议只支持“双色线性渐变”。

建议方式：

- 生成与元素 bbox 同尺寸的渐变层
- 用 alpha 作为蒙版，仅在元素有效区域内混合
- 支持角度参数

不建议第一阶段做：

- 多断点渐变
- 径向渐变
- 复杂混合模式


## 与现有代码的接入点

### `ppt_system/web/`

需要新增：

- 编辑页前端路由兜底或入口跳转
- 编辑专用 API 路由

建议保持原则：

- 不影响现有任务生成接口
- 不改现有首页接口响应结构
- 编辑接口全部单独命名

### `ppt_system/export/text_script_runtime.py`

当前 `add_assets(...)` 按 manifest 逐个读取 PNG 并放入 PPT。

这个能力本身可以继续复用，建议只让它读取“编辑后生成的资产 manifest”。

### `ppt_system/export/direct_project_script.py`

当前负责按页准备资产。

重新导出时可考虑新增一个“编辑模式资产准备”分支：

- 普通任务导出：仍走原始资产
- 编辑后导出：优先读取编辑渲染缓存


## 开发阶段拆分

### 阶段 1：页面和读取链路打通

交付目标：

- 可以从首页跳到编辑页
- 编辑页可加载任务页列表
- 可以查看单页资产列表

任务清单：

- 新增 `web_ui/src/components/ElementEditor/ElementEditorPage.jsx`
- 新增编辑页组件、hook 与 API 封装
- 新增前端路由入口或复用 Flask SPA 兜底承载 `/editor/<job_id>`
- 新增 `GET /api/jobs/<job_id>/editable-pages`
- 新增 `GET /api/jobs/<job_id>/pages/<page_no>/assets`

验收标准：

- 任务完成后可进入编辑页
- 至少能看到每页元素数量和元素名称

### 阶段 2：编辑参数保存

交付目标：

- 可修改元素参数并保存
- 刷新页面后编辑结果仍存在

任务清单：

- 新增 `editor_store.py`
- 新增 `editor_models.py`
- 新增 `PUT /api/jobs/<job_id>/pages/<page_no>/edits`

验收标准：

- 修改透明度或颜色后可保存
- 再次打开页面能恢复保存结果

### 阶段 3：实时预览

交付目标：

- 改完参数后能在编辑页预览最终视觉效果

任务清单：

- 新增 `editor_preview.py`
- 新增 `POST /api/jobs/<job_id>/pages/<page_no>/preview`

验收标准：

- 透明度、换色、渐变三项都能在预览中看到效果

### 阶段 4：重新导出 PPT

交付目标：

- 基于编辑结果重新导出 PPT
- 打开 PPT 能看到前端编辑后的效果

任务清单：

- 新增 `editor_export.py`
- 新增 `POST /api/jobs/<job_id>/export-from-edits`
- 将导出链路接到编辑后资产

验收标准：

- 导出的 PPT 中元素颜色、透明度、渐变符合前端预览


## 测试建议

要避免只针对某一张图生效，测试必须覆盖相似变体。

### 单元测试

建议新增：

- `tests/test_editor_models.py`
  - 校验默认值补全、颜色规范化、渐变参数校验
- `tests/test_editor_store.py`
  - 校验编辑文件读写
- `tests/test_editor_preview.py`
  - 校验透明度、换色、渐变的渲染结果
- `tests/test_editor_export.py`
  - 校验编辑后资产清单生成

### 变体测试

至少覆盖以下场景：

- 单元素图
- 多元素图
- 面积很小的元素
- 半透明元素
- 深色元素换浅色
- 浅色元素换深色
- 细长元素上的线性渐变
- 同页多个元素同时编辑

### 集成测试

建议补一个端到端回归：

1. 读取已有任务资产
2. 写入编辑参数
3. 生成预览
4. 重新导出 PPT
5. 断言输出文件存在，且编辑后资产缓存已生成


## 风险与注意事项

### 风险 1：前端预览和 PPT 最终效果不一致

应对：

- 前端尽量显示后端生成的预览图，不只靠浏览器 CSS 假渲染
- 预览逻辑和导出逻辑尽量复用

### 风险 2：渐变实现过早复杂化

应对：

- 第一阶段只支持双色线性渐变
- 数据结构先留扩展位，不立即实现所有变体

### 风险 3：直接改原始资产导致回滚困难

应对：

- 原始切分结果只读
- 所有编辑结果都单独存储

### 风险 4：导出链路和普通任务链路互相污染

应对：

- 编辑后导出走独立接口
- 编辑缓存和普通导出产物分目录存放


## MVP 验收标准

满足以下条件即可认为第一阶段完成：

- 首页能跳转到某个任务的独立编辑页
- 编辑页能查看任务所有页及其元素
- 能对单个元素改颜色、调透明度、加双色线性渐变
- 编辑结果可保存并重新打开恢复
- 能重新导出 PPT
- 打开导出的 PPT 后，能看到前端对应的视觉效果


## 后续演进方向

第一阶段完成后，可按以下顺序演进：

1. 加入拖拽、缩放、显隐、层级调整
2. 批量编辑同类元素
3. 增加阴影、描边、发光等通用样式
4. 支持更多渐变类型
5. 引入 `vector` 元素类型
6. 独立矢量化模块，探索 SVG 输出与 shape 化导出
