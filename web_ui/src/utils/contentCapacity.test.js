import test from 'node:test';
import assert from 'node:assert/strict';
import { analyzeContentCapacity } from './contentCapacity.js';

test('短结构化内容保持克制页数建议', () => {
  const analysis = analyzeContentCapacity(
    [
      '项目背景：介绍自动化测试平台建设目标。',
      '当前进展：已完成规则配置和脚本绑定。',
      '后续安排：补充回归验证和问题闭环。',
    ].join('\n'),
    { pageCount: 3, maxPages: 12 },
  );

  assert.equal(analysis.hasContent, true);
  assert.ok(analysis.recommendedPageCount <= 3);
  assert.equal(analysis.riskLevel, 'none');
});

test('长段高密度内容在页数过低时提示风险并推荐合理页数', () => {
  const content = [
    '本次两款产品按自动化急速测试方案执行，承保覆盖率100%通过率92.06%，核保覆盖率100%通过率91.61%，保全覆盖率100%通过率100%，理赔覆盖率100%通过率33.33%，精算覆盖率50%通过率88.88%。',
    '缺陷包括录单界面无法定位、身份信息校验新增弹窗阻断流程、初审任务分配未完成输入即触发检索、基础数据未同步、调用下游系统接口失败、撤保界面未识别保单号、立案界面缓冲时间不足未生成报案号。',
    '后续需要分析根因，明确操作系统缺陷、自动化平台脚本异常处理、案例生成规则、需求同步机制之间的责任边界，并建立响应机制和预防措施，避免后续类似问题反复发生。',
    '响应安排包括建立问题分级、执行前校验规则、案例生成抽检、脚本异常弹窗处理、环境可用性检查、需求变更同步确认、失败案例复跑策略和日报追踪闭环。',
    '业务侧还需要在执行前确认需求冻结状态、基础数据同步状态、产品规则下发状态、脚本版本状态和环境健康状态；平台侧需要补充异常弹窗识别、输入完成等待、按钮定位稳定性、接口失败重试边界和失败原因分类沉淀。',
    '管理汇报中还要覆盖本次执行未达预期的影响、自动化方案适用边界、手工测试补位范围、缺陷解决时效、跨团队协同卡点以及下一批产品上线前的准入条件。',
  ].join('');

  const analysis = analyzeContentCapacity(content, { pageCount: 1, maxPages: 12 });

  assert.ok(analysis.recommendedPageCount >= 4);
  assert.ok(analysis.recommendedPageCount <= 8);
  assert.equal(analysis.riskLevel, 'high');
  assert.equal(analysis.isUnstructuredLong, true);
  assert.ok(analysis.outlineItems.length >= 3);
  assert.equal(new Set(analysis.outlineItems.map((item) => item.text)).size, analysis.outlineItems.length);
});

test('最大页数配置会限制推荐页数', () => {
  const repeated = Array.from({ length: 60 }, (_, index) => `问题${index + 1}：执行失败，通过率${80 + (index % 10)}%，原因待分析。`).join('\n');
  const analysis = analyzeContentCapacity(repeated, { pageCount: 2, maxPages: 5 });

  assert.equal(analysis.recommendedPageCount, 5);
  assert.equal(analysis.recommendedMax, 5);
});
