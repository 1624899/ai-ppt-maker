(function attachGenerationResultPresenter(globalScope) {
  // 统一封装右侧流程状态卡，聚合阶段进度、当前说明与最终交付入口。
  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    })[char]);
  }

  function getStageLabel(stageKey) {
    const map = {
      queued: "等待执行",
      planning: "模型规划",
      reference_generation: "参考图生成",
      elements_generation: "元素图生成",
      ppt_export: "PPT 组装",
      completed: "全部完成",
    };
    return map[String(stageKey || "").trim()] || "处理中";
  }

  function getStatusLabel(status) {
    const map = {
      pending: "等待中",
      queued: "等待中",
      running: "进行中",
      stopping: "已暂停",
      interrupted: "已暂停",
      skipped: "已跳过",
      completed: "已完成",
      error: "失败",
    };
    return map[String(status || "").trim()] || "处理中";
  }

  function getStatusTone(status) {
    if (status === "completed") {
      return "completed";
    }
    if (status === "error") {
      return "error";
    }
    if (status === "interrupted") {
      return "interrupted";
    }
    if (status === "running" || status === "stopping") {
      return "running";
    }
    return "pending";
  }

  function getActiveStage(job) {
    const stages = Array.isArray(job?.stages) ? job.stages : [];
    const currentStageKey = String(job?.current_stage || "").trim();
    if (!currentStageKey) {
      return null;
    }
    return stages.find((stage) => stage.key === currentStageKey) || null;
  }

  function getStageProgress(stages) {
    const safeStages = Array.isArray(stages) ? stages : [];
    const total = safeStages.length;
    if (!total) {
      return {
        completed: 0,
        total: 0,
        percent: 0,
      };
    }
    const completed = safeStages.filter((stage) => stage?.status === "completed").length;
    return {
      completed,
      total,
      percent: Math.max(6, Math.min(100, Math.round((completed / total) * 100))),
    };
  }

  function getStageSummary(job, activeStage, exportStage) {
    const isReferenceOnly = job?.job_meta?.job_target === "reference_only";
    if (job?.status === "completed") {
      if (isReferenceOnly) {
        return exportStage?.summary || "参考图与图片版 PPT 已完成，可继续转为可编辑 PPT。";
      }
      return exportStage?.summary || "PPT 已组装完成，可以直接下载。";
    }
    if (job?.status === "error") {
      return job?.error || exportStage?.summary || "任务执行失败，请查看错误日志。";
    }
    if (job?.status === "interrupted") {
      return "任务已暂停，可继续从当前进度恢复。";
    }
    if (job?.status === "stopping") {
      return "任务已暂停，可继续从当前进度恢复。";
    }
    if (activeStage?.key === "queued") {
      return "任务已创建，等待进入执行队列。";
    }
    if (activeStage?.key === "planning") {
      return "正在拆解内容并规划页面结构。";
    }
    if (activeStage?.key === "reference_generation") {
      return "正在生成带文字参考图。";
    }
    if (activeStage?.status === "skipped") {
      return activeStage?.summary || "当前输出模式不需要执行该阶段。";
    }
    if (activeStage?.key === "elements_generation") {
      return "正在生成去文字元素图。";
    }
    if (activeStage?.key === "ppt_export") {
      return activeStage?.summary || exportStage?.summary || "正在后处理并组装 PPT。";
    }
    return "等待进入下一阶段。";
  }

  function buildActions(exportResult) {
    const actions = [];
    if (exportResult?.pptx_url) {
      actions.push({
        kind: "primary",
        label: exportResult?.delivery_mode === "reference_only" ? "下载图片版 PPT" : "下载 PPT",
        href: exportResult.pptx_url,
      });
    }
    if (exportResult?.project_url) {
      actions.push({
        kind: "secondary",
        label: "查看快照",
        href: exportResult.project_url,
      });
    }
    return actions;
  }

  function buildStageDots(stages, currentStageKey) {
    const safeStages = Array.isArray(stages) ? stages : [];
    return safeStages.map((stage) => {
      const tone =
        stage?.status === "completed"
          ? "completed"
          : stage?.status === "error"
            ? "error"
            : stage?.key === currentStageKey || stage?.status === "running"
              ? "running"
              : stage?.status === "interrupted"
                ? "interrupted"
                : "pending";
      return {
        label: getStageLabel(stage?.key),
        tone,
      };
    });
  }

  function buildFlowCard(job) {
    const exportStage = (job?.stages || []).find((stage) => stage.key === "ppt_export") || {};
    const exportResult = job?.result?.export || {};
    const activeStage = getActiveStage(job);
    const progress = getStageProgress(job?.stages);
    return {
      tone: getStatusTone(job?.status),
      title: "流程状态",
      statusLabel: getStatusLabel(job?.status),
      progressText: progress.total ? `${progress.completed}/${progress.total} 阶段` : "等待开始",
      progressPercent: progress.percent,
      currentStageLabel: getStageLabel(activeStage?.key || job?.current_stage || job?.status),
      summary: getStageSummary(job, activeStage, exportStage),
      allowErrorLog: job?.status === "error",
      stageDots: buildStageDots(job?.stages, job?.current_stage),
      actions: buildActions(exportResult),
    };
  }

  function renderLinks(linksContainer) {
    if (!linksContainer) {
      return;
    }
    linksContainer.hidden = true;
    linksContainer.innerHTML = "";
  }

  function renderCard(container, card) {
    if (!container) {
      return;
    }
    const stageDotsHtml = card.stageDots
      .map((item) => {
        return `
          <span class="flow-stage-dot is-${escapeHtml(item.tone)}">${escapeHtml(item.label)}</span>
        `;
      })
      .join("");
    const actionHtml = card.actions
      .map((action) => {
        const actionClass = action.kind === "primary" ? "primary-button" : "secondary-button";
        return `
          <a class="flow-card-action ${actionClass}" href="${escapeHtml(action.href)}" target="_blank" rel="noreferrer">
            ${escapeHtml(action.label)}
          </a>
        `;
      })
      .join("");
    const errorActionHtml = card.allowErrorLog
      ? `<button class="secondary-button compact-button" type="button" data-action="open-error-log">查看错误日志</button>`
      : "";
    container.innerHTML = `
      <section class="result-stage-overview flow-card is-${escapeHtml(card.tone)}">
        <div class="result-stage-overview-head">
          <div class="result-stage-overview-head-main">
            <span class="result-stage-overview-kicker">${escapeHtml(card.title)}</span>
            <h3 class="flow-card-stage">${escapeHtml(card.currentStageLabel)}</h3>
          </div>
          <div class="result-stage-overview-side">
            ${errorActionHtml}
            <span class="stage-status is-${escapeHtml(card.tone)}">${escapeHtml(card.statusLabel)}</span>
          </div>
        </div>
        <div class="flow-progress-block">
          <div class="flow-progress-meta">
            <span>${escapeHtml(card.progressText)}</span>
            <strong>${escapeHtml(String(card.progressPercent))}%</strong>
          </div>
          <div class="flow-progress-track" aria-hidden="true">
            <div class="flow-progress-bar is-${escapeHtml(card.tone)}" style="width: ${escapeHtml(String(card.progressPercent))}%;"></div>
          </div>
          <div class="flow-stage-dots">${stageDotsHtml}</div>
        </div>
        <div class="result-stage-overview-summary${card.allowErrorLog ? " is-bounded" : ""}">${escapeHtml(card.summary)}</div>
        <div class="flow-card-actions">${actionHtml}</div>
      </section>
    `;
  }

  globalScope.PptGenerationResult = {
    buildFlowCard,
    render({ container, linksContainer, job }) {
      renderCard(container, buildFlowCard(job));
      renderLinks(linksContainer);
    },
  };
})(window);
