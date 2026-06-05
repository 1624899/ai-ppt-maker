from __future__ import annotations

import unittest

from ppt_system.generation.content_agent import build_planning_prompt, fallback_style_guide, normalize_content_plan
from ppt_system.generation.source_content_anchors import build_source_content_anchors, resolve_page_source_anchors


class SourceContentAnchorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.style_guide = fallback_style_guide("蓝白科技汇报", has_reference_images=False)

    def test_structured_report_keeps_source_facts_when_model_rewrites_numbers(self) -> None:
        content = """
一、本阶段工作总体情况
本阶段围绕保全测试智能助手的落地应用，重点推进了保全事项梳理接入、公司环境部署验证、演示效果优化、知识库建设和核心能力完善等工作。

二、保全事项覆盖持续扩大
截至当前，已沉淀 19 份保全业务文档，覆盖 4大类 类保全事项，主要包括：
退保类：一般退保、犹豫期撤保、减保、简单减保、高利率退保、死亡退保、万能账户余额部分提取
给付类：红利给付
贷还款类：保单贷款、保单还款
变更类：复效、减额交清、保单垫交还款、强制终止、合同转换、合并客户、保险期间变更、保全业务回退

三、业务功能更加贴近使用场景
能快速回答“某项保全怎么办、下一步做什么、对应规则怎么理解”等高频问题。
""".strip()
        result = {
            "pages": [
                {
                    "page_no": 1,
                    "title": "阶段工作总览",
                    "summary": "模型改写后的概览",
                    "bullets": ["模型自由发挥的概览"],
                    "source_anchor_ids": ["S01"],
                    "layout_family": "grid_n_x_m",
                },
                {
                    "page_no": 2,
                    "title": "保全事项覆盖",
                    "summary": "突出 19 份业务文档、18 类保全事项以及多系统办理场景支撑。",
                    "bullets": [
                        "已沉淀 19 份保全业务文档，覆盖 18 类保全事项",
                        "覆盖退保类、给付类、贷还款类、变更类等主要保全场景",
                    ],
                    "source_anchor_ids": ["S02"],
                    "layout_family": "split_left_right",
                },
                {
                    "page_no": 3,
                    "title": "业务能力",
                    "summary": "辅助开展保全测试和业务核验",
                    "bullets": ["自由发挥内容"],
                    "source_anchor_ids": ["S03"],
                    "layout_family": "process_horizontal",
                },
            ]
        }

        plan = normalize_content_plan(
            result,
            content=content,
            page_count=3,
            image_width=2048,
            image_height=1152,
            style_notes="蓝白科技汇报",
            style_guide=self.style_guide,
            has_reference_images=False,
            generation_options={"include_cover_page": False},
        )

        page_two = plan["pages"][1]
        joined = "\n".join([page_two["summary"], *page_two["bullets"]])
        self.assertIn("覆盖 4大类 类保全事项", joined)
        self.assertIn("退保类：一般退保、犹豫期撤保、减保、简单减保、高利率退保、死亡退保、万能账户余额部分提取", joined)
        self.assertIn("变更类：复效、减额交清、保单垫交还款、强制终止、合同转换、合并客户、保险期间变更、保全业务回退", joined)
        self.assertNotIn("18 类保全事项", joined)
        self.assertEqual(page_two["source_anchor_ids"], ["S02"])
        body_text = "\n".join(str(item.get("text", "")) for item in page_two["texts"])
        self.assertIn("覆盖 4大类 类保全事项", body_text)
        self.assertNotIn("18 类保全事项", body_text)
        self.assertIn("覆盖 4大类 类保全事项", page_two["image_prompt"])
        self.assertNotIn("18 类保全事项", page_two["image_prompt"])

    def test_unstructured_paragraph_still_anchors_facts_and_allows_model_page_selection(self) -> None:
        content = (
            "本阶段完成支付网关灰度验证，覆盖 3 个核心渠道，日均处理 120 万笔交易。"
            "监控侧新增 12 个告警指标，并把异常定位时间从 30 分钟压缩到 8 分钟。"
            "客服侧同步上线知识检索入口，首周解决率达到 82%。"
            "下一阶段计划扩展到跨境支付和批量退款两个场景。"
        )
        result = {
            "pages": [
                {
                    "page_no": 1,
                    "title": "运行成效",
                    "summary": "模型把 3 个渠道改成 5 个渠道。",
                    "bullets": ["支付网关覆盖 5 个渠道", "日均 150 万笔交易"],
                    "source_anchor_ids": ["S01", "S02"],
                    "layout_family": "grid_n_x_m",
                },
                {
                    "page_no": 2,
                    "title": "后续计划",
                    "summary": "模型自由扩写跨境、风控和清算。",
                    "bullets": ["扩展到三个新场景"],
                    "source_anchor_ids": ["S03", "S04"],
                    "layout_family": "process_horizontal",
                },
            ]
        }

        plan = normalize_content_plan(
            result,
            content=content,
            page_count=2,
            image_width=2048,
            image_height=1152,
            style_notes="",
            style_guide={},
            has_reference_images=False,
            generation_options={"include_cover_page": False},
        )

        first_page_text = "\n".join([plan["pages"][0]["summary"], *plan["pages"][0]["bullets"]])
        second_page_text = "\n".join([plan["pages"][1]["summary"], *plan["pages"][1]["bullets"]])
        self.assertIn("覆盖 3 个核心渠道", first_page_text)
        self.assertIn("日均处理 120 万笔交易", first_page_text)
        self.assertIn("12 个告警指标", first_page_text)
        self.assertIn("跨境支付和批量退款两个场景", second_page_text)
        self.assertNotIn("5 个渠道", first_page_text)
        self.assertNotIn("150 万笔", first_page_text)
        self.assertNotIn("三个新场景", second_page_text)

    def test_planning_prompt_exposes_source_anchor_ids_for_model_page_planning(self) -> None:
        content = "一、覆盖情况\n已完成 6 个系统验证。\n二、后续计划\n继续推进 2 个场景。"
        anchors = build_source_content_anchors(content, page_count=2)

        prompt = build_planning_prompt(
            content=content,
            page_count=2,
            image_width=2048,
            image_height=1152,
            style_notes="",
            style_image_count=0,
            style_guide=self.style_guide,
            source_anchors=anchors,
            generation_options={"include_cover_page": False},
        )

        self.assertIn("源文事实锚点", prompt)
        self.assertIn("S01｜覆盖情况", prompt)
        self.assertIn("S02｜后续计划", prompt)
        self.assertIn('"source_anchor_ids": ["S01"]', prompt)
        self.assertIn("可以一页承载一个或多个锚点", prompt)
        self.assertIn("内容把控规则", prompt)
        self.assertIn("输入偏长时做重点突出和语义总结", prompt)

    def test_long_source_content_is_summarized_by_richness_without_inventing_facts(self) -> None:
        content = """
一、项目推进情况
本阶段完成需求梳理、接口联调、环境部署、演示优化、知识库整理、测试工具接入、规则核验、权限校验、日志观察、问题复盘。
已覆盖 4 个业务域，沉淀 26 条测试关注点，验证 3 套环境，并形成 5 类通用操作资料。
后续重点围绕新增事项接入、测试闭环完善、使用反馈收集和知识更新机制建设。
""".strip()
        result = {
            "pages": [
                {
                    "page_no": 1,
                    "title": "阶段成果",
                    "summary": "模型声称扩展为 9 个业务域和 80 条测试点",
                    "bullets": ["新增 9 个业务域", "沉淀 80 条测试关注点", "覆盖 6 套环境"],
                    "source_anchor_ids": ["S01"],
                    "layout_family": "grid_n_x_m",
                    "page_richness": "high",
                }
            ]
        }

        plan = normalize_content_plan(
            result,
            content=content,
            page_count=1,
            image_width=2048,
            image_height=1152,
            style_notes="",
            style_guide=self.style_guide,
            has_reference_images=False,
            generation_options={"include_cover_page": False, "page_richness_default": "high"},
        )

        page = plan["pages"][0]
        joined = "\n".join([page["summary"], *page["bullets"]])
        self.assertLessEqual(len(page["bullets"]), 6)
        self.assertIn("已覆盖 4 个业务域", joined)
        self.assertIn("沉淀 26 条测试关注点", joined)
        self.assertIn("验证 3 套环境", joined)
        self.assertNotIn("9 个业务域", joined)
        self.assertNotIn("80 条测试关注点", joined)
        self.assertIn("长内容页", page["style_constraints"])

    def test_short_source_content_only_adds_light_layout_support_when_richness_is_high(self) -> None:
        content = "本阶段完成短信电子签名认证指引。"
        result = {
            "pages": [
                {
                    "page_no": 1,
                    "title": "电子签名",
                    "summary": "模型补充覆盖 12 个渠道并节省 40% 时间",
                    "bullets": ["覆盖 12 个渠道", "节省 40% 时间"],
                    "source_anchor_ids": ["S01"],
                    "layout_family": "split_left_right",
                    "page_richness": "high",
                }
            ]
        }

        plan = normalize_content_plan(
            result,
            content=content,
            page_count=1,
            image_width=2048,
            image_height=1152,
            style_notes="",
            style_guide=self.style_guide,
            has_reference_images=False,
            generation_options={"include_cover_page": False, "page_richness_default": "high"},
        )

        page = plan["pages"][0]
        joined = "\n".join([page["summary"], *page["bullets"]])
        self.assertIn("本阶段完成短信电子签名认证指引", joined)
        self.assertIn("围绕上述信息组织页面表达", joined)
        self.assertNotIn("12 个渠道", joined)
        self.assertNotIn("40% 时间", joined)
        self.assertLessEqual(len(page["bullets"]), 2)
        self.assertIn("短内容页", page["style_constraints"])

    def test_markdown_page_headings_do_not_leak_into_previous_page(self) -> None:
        content = """
### 第一页：本阶段重点工作综述

**总体定位**
本阶段实现保全测试智能助手从技术原型向业务可用阶段跨越。

- **保全事项覆盖持续扩大**
  沉淀19份业务文档，覆盖4大类保全场景。

---

### 第二页：保全知识库建设与资产化

**建设目标**
构建可查询、可复用、可维护的知识资产体系。
""".strip()
        anchors = build_source_content_anchors(content, page_count=2)
        self.assertEqual([(item["id"], item.get("page_no")) for item in anchors], [("S01", 1), ("S02", 2)])

        selected = resolve_page_source_anchors(
            {"source_anchor_ids": ["S01", "S02"]},
            page_index=0,
            page_count=2,
            anchors=anchors,
        )
        self.assertEqual([item["id"] for item in selected], ["S01"])

        compact_content = "第一页：本阶段重点工作综述 总体定位：完成A。第二页：知识库建设 建设目标：形成资产。"
        compact_anchors = build_source_content_anchors(compact_content, page_count=2)
        self.assertEqual([item.get("page_no") for item in compact_anchors], [1, 2])
        self.assertNotIn("第二页", "\n".join(compact_anchors[0]["facts"]))

        plan = normalize_content_plan(
            {
                "pages": [
                    {
                        "page_no": 1,
                        "title": "本阶段重点综述",
                        "summary": "第一页：本阶段重点工作综述 第二页：保全知识库建设与资产化",
                        "bullets": ["第一页：本阶段重点工作综述", "第二页：保全知识库建设与资产化"],
                        "source_anchor_ids": ["S01", "S02"],
                        "layout_family": "grid_n_x_m",
                    },
                    {
                        "page_no": 2,
                        "title": "知识库资产化",
                        "summary": "第二页：保全知识库建设与资产化",
                        "bullets": ["建设目标"],
                        "source_anchor_ids": ["S02"],
                        "layout_family": "split_left_right",
                    },
                ]
            },
            content=content,
            page_count=2,
            image_width=2048,
            image_height=1152,
            style_notes="",
            style_guide=self.style_guide,
            has_reference_images=False,
            generation_options={"include_cover_page": False},
        )

        page_one_text = "\n".join([plan["pages"][0]["summary"], *plan["pages"][0]["bullets"], plan["pages"][0]["image_prompt"]])
        self.assertIn("沉淀19份业务文档，覆盖4大类保全场景", page_one_text)
        self.assertNotIn("第二页：保全知识库建设与资产化", page_one_text)
        self.assertNotIn("第一页：本阶段重点工作综述", page_one_text)
        self.assertNotIn("**", page_one_text)
        self.assertNotIn("*保全事项覆盖持续扩大", page_one_text)

    def test_page_scoped_anchor_overrides_wrong_model_selection(self) -> None:
        content = (
            "第一页：阶段综述 第一页事实：完成公司环境部署验证。"
            "第二页：知识库建设 第二页事实：形成三类知识资产。"
        )
        anchors = build_source_content_anchors(content, page_count=2)

        selected = resolve_page_source_anchors(
            {"source_anchor_ids": ["S02"]},
            page_index=0,
            page_count=2,
            anchors=anchors,
        )

        self.assertEqual([item["id"] for item in selected], ["S01"])
        self.assertIn("第一页事实", "\n".join(selected[0]["facts"]))
        self.assertNotIn("第二页事实", "\n".join(selected[0]["facts"]))

    def test_markdown_emphasis_is_removed_inside_fact_lines(self) -> None:
        content = """
### 第一页：功能清单

- **智能问答**：快速回答高频问题
- __业务辅助定位__：辅助查找页面、操作步骤与参考资料
""".strip()
        anchors = build_source_content_anchors(content, page_count=1)
        facts = "\n".join(anchors[0]["facts"])

        self.assertIn("智能问答：快速回答高频问题", facts)
        self.assertIn("业务辅助定位：辅助查找页面、操作步骤与参考资料", facts)
        self.assertNotIn("**", facts)
        self.assertNotIn("__", facts)

    def test_inline_page_headings_are_split_before_model_planning(self) -> None:
        content = (
            "第一页：本阶段重点工作综述 总体定位：完成保全事项接入。"
            "核心工作：沉淀19份业务文档，覆盖4大类保全场景。"
            " 第二页：保全知识库建设 建设目标：形成可查询、可复用的知识资产。"
            "构成：保全业务知识、通用操作知识、测试辅助资料。"
        )
        anchors = build_source_content_anchors(content, page_count=2)
        self.assertEqual([item.get("page_no") for item in anchors], [1, 2])
        self.assertEqual(anchors[0]["title"], "本阶段重点工作综述")
        self.assertEqual(anchors[1]["title"], "保全知识库建设")
        self.assertNotIn("第二页", "\n".join(anchors[0]["facts"]))

        selected = resolve_page_source_anchors(
            {"source_anchor_ids": ["S01", "S02"]},
            page_index=0,
            page_count=2,
            anchors=anchors,
        )
        self.assertEqual([item["id"] for item in selected], ["S01"])

    def test_inline_page_heading_with_plain_body_keeps_title_short(self) -> None:
        content = (
            "第一页：阶段综述 本阶段完成保全事项梳理接入，支撑业务测试。"
            "第二页：建设计划 后续完善知识运营闭环，提升命中率。"
        )
        anchors = build_source_content_anchors(content, page_count=2)

        self.assertEqual(anchors[0]["title"], "阶段综述")
        self.assertIn("本阶段完成保全事项梳理接入，支撑业务测试", "\n".join(anchors[0]["facts"]))
        self.assertEqual(anchors[1]["title"], "建设计划")
        self.assertIn("后续完善知识运营闭环，提升命中率", "\n".join(anchors[1]["facts"]))
        self.assertNotIn("第二页", "\n".join(anchors[0]["facts"]))

    def test_page_scoped_sections_keep_internal_numbered_items_on_same_page(self) -> None:
        content = """
第一页：阶段成果
总体定位
完成智能助手从技术原型到业务可用的跨越。

第二页：后续发展计划
一、知识运营平台升级
新增知识运营看板，建立知识治理闭环。

二、保全事项覆盖全面达成
实现常用保全项覆盖进度100%。

三、深度集成与推广
形成“问题输入 → 规则匹配 → 步骤提示 → 结果校验”的测试闭环。
""".strip()
        anchors = build_source_content_anchors(content, page_count=2)

        self.assertEqual([(item["id"], item.get("page_no")) for item in anchors], [("S01", 1), ("S02", 2)])
        second_page_facts = "\n".join(anchors[1]["facts"])
        self.assertIn("知识运营平台升级：新增知识运营看板，建立知识治理闭环", second_page_facts)
        self.assertIn("保全事项覆盖全面达成：实现常用保全项覆盖进度100%", second_page_facts)
        self.assertIn("深度集成与推广：形成“问题输入 → 规则匹配 → 步骤提示 → 结果校验”的测试闭环", second_page_facts)

    def test_structured_page_summary_keeps_all_core_work_modules(self) -> None:
        content = """
第一页：本阶段重点工作综述
总体定位
本阶段实现保全测试智能助手从技术原型向业务可用跨越。

保全事项覆盖持续扩大
完成退保、给付、贷还款、变更等4大类保全场景梳理。

业务功能贴近使用场景
实现高频问题回答、页面辅助定位和主动澄清。

公司环境验证与演示优化
完成内网联调部署验证，优化演示流畅性。

知识库由资料堆积转向可用资产
形成保全业务知识、通用操作知识、测试辅助资料三类内容。
""".strip()

        plan = normalize_content_plan(
            {
                "pages": [
                    {
                        "page_no": 1,
                        "title": "本阶段重点工作综述",
                        "summary": "模型只提覆盖",
                        "bullets": ["保全事项覆盖持续扩大"],
                        "source_anchor_ids": ["S01"],
                        "layout_family": "grid_n_x_m",
                        "page_richness": "medium",
                    }
                ]
            },
            content=content,
            page_count=1,
            image_width=2048,
            image_height=1152,
            style_notes="",
            style_guide=self.style_guide,
            has_reference_images=False,
            generation_options={"include_cover_page": False, "page_richness_default": "medium"},
        )

        page = plan["pages"][0]
        joined = "\n".join([page["summary"], *page["bullets"], page["image_prompt"]])
        self.assertIn("总体定位", joined)
        self.assertIn("保全事项覆盖持续扩大", joined)
        self.assertIn("业务功能贴近使用场景", joined)
        self.assertIn("公司环境验证与演示优化", joined)
        self.assertIn("知识库由资料堆积转向可用资产", joined)

    def test_many_structured_modules_are_grouped_without_silent_omission(self) -> None:
        facts = [f"模块{i}：事实{i}说明。" for i in range(1, 11)]
        content = "第一页：多模块综述\n" + "\n".join(
            f"模块{i}\n事实{i}说明。" for i in range(1, 11)
        )

        plan = normalize_content_plan(
            {
                "pages": [
                    {
                        "page_no": 1,
                        "title": "多模块综述",
                        "source_anchor_ids": ["S01"],
                        "layout_family": "grid_n_x_m",
                        "page_richness": "medium",
                    }
                ]
            },
            content=content,
            page_count=1,
            image_width=2048,
            image_height=1152,
            style_notes="",
            style_guide=self.style_guide,
            has_reference_images=False,
            generation_options={"include_cover_page": False, "page_richness_default": "medium"},
        )

        page = plan["pages"][0]
        joined = "\n".join([page["summary"], *page["bullets"], page["image_prompt"]])
        for fact in facts[:7]:
            self.assertIn(fact, joined)
        self.assertIn("其他要点", joined)
        self.assertIn("模块10：事实10", joined)
        self.assertIn("其他要点", page["image_prompt"])
        self.assertIn("模块10：事实10", page["image_prompt"])
        body_text = "\n".join(str(item.get("text", "")) for item in page["texts"])
        self.assertIn("其他要点", body_text)
        self.assertIn("模块10", body_text)

    def test_comma_separated_short_fact_is_not_treated_as_heading(self) -> None:
        content = """
第一页：知识库建设
资产化价值
新增保全事项时，优先通过补充知识库实现能力扩展
为新人学习、测试支持、日常答疑提供统一入口
知识可维护、可复用，降低长期运营成本
""".strip()
        anchors = build_source_content_anchors(content, page_count=1)
        facts = "\n".join(anchors[0]["facts"])

        self.assertIn("为新人学习、测试支持、日常答疑提供统一入口", facts)
        self.assertIn("知识可维护、可复用，降低长期运营成本", facts)
        self.assertNotIn("为新人学习、测试支持、日常答疑提供统一入口：知识可维护", facts)

    def test_flat_paragraph_allows_ai_information_architecture_but_keeps_facts_grounded(self) -> None:
        content = (
            "本阶段完成保全事项梳理接入，沉淀19份业务文档，覆盖退保类、给付类、贷还款类、变更类4大类保全场景，"
            "完成公司环境联调和部署验证，确认系统在内网可稳定运行，Demo经过多轮优化，回答展示、会话管理、追问建议和结果展示更加清晰，"
            "知识库沉淀保全业务知识、通用操作知识和测试辅助资料三类内容，系统能快速回答保全怎么办、下一步做什么、规则怎么理解等问题，并辅助定位页面和操作步骤"
        )
        anchors = build_source_content_anchors(content, page_count=3)
        self.assertGreaterEqual(len(anchors), 3)
        self.assertTrue(all(item.get("page_no") is None for item in anchors))

        plan = normalize_content_plan(
            {
                "pages": [
                    {
                        "page_no": 1,
                        "title": "业务覆盖与验证",
                        "summary": "模型规划第一页讲覆盖和环境，额外写覆盖率100%",
                        "bullets": ["覆盖率100%", "新增10个模块"],
                        "source_anchor_ids": ["S01", "S02"],
                        "layout_family": "grid_n_x_m",
                    },
                    {
                        "page_no": 2,
                        "title": "演示与知识库",
                        "summary": "模型规划第二页讲演示和知识库",
                        "bullets": ["模型发挥"],
                        "source_anchor_ids": ["S03", "S04"],
                        "layout_family": "split_left_right",
                    },
                    {
                        "page_no": 3,
                        "title": "业务问答支撑",
                        "summary": "模型规划第三页讲问答支撑",
                        "bullets": ["模型发挥"],
                        "source_anchor_ids": ["S05"],
                        "layout_family": "process_horizontal",
                    },
                ]
            },
            content=content,
            page_count=3,
            image_width=2048,
            image_height=1152,
            style_notes="",
            style_guide=self.style_guide,
            has_reference_images=False,
            generation_options={"include_cover_page": False},
        )

        first_page_text = "\n".join([plan["pages"][0]["summary"], *plan["pages"][0]["bullets"], plan["pages"][0]["image_prompt"]])
        self.assertIn("沉淀19份业务文档", first_page_text)
        self.assertIn("内网可稳定运行", first_page_text)
        self.assertNotIn("覆盖率100%", first_page_text)
        self.assertNotIn("新增10个模块", first_page_text)


if __name__ == "__main__":
    unittest.main()
