(function attachWorkspaceStatusPresenter(globalScope) {
  // 统一封装工作台状态摘要，避免页面脚本分散拼接桌面端提示文案。
  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    })[char]);
  }

  function summarizeContent(value) {
    const text = String(value || "").trim().replace(/\s+/g, " ");
    if (!text) {
      return {
        title: "尚未填写正文",
        preview: "先打开内容编辑器补充汇报正文，系统会基于正文自动拆页并生成每页参考图。",
      };
    }
    return {
      title: text.slice(0, 28) + (text.length > 28 ? "..." : ""),
      preview: text.slice(0, 96) + (text.length > 96 ? "..." : ""),
    };
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
      queued: "等待中",
      running: "进行中",
      stopping: "暂停中",
      interrupted: "已暂停",
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

  function getStageProgress(stages) {
    const safeStages = Array.isArray(stages) ? stages : [];
    if (!safeStages.length) {
      return {
        completedCount: 0,
        totalCount: 0,
        ratio: 0,
      };
    }
    const completedCount = safeStages.filter((stage) => stage?.status === "completed").length;
    return {
      completedCount,
      totalCount: safeStages.length,
      ratio: completedCount / safeStages.length,
    };
  }

  function formatProgressLabel(job) {
    const progress = getStageProgress(job?.stages);
    if (!progress.totalCount) {
      return "等待开始";
    }
    if (job?.status === "completed") {
      return `已完成 ${progress.totalCount}/${progress.totalCount} 阶段`;
    }
    return `已完成 ${progress.completedCount}/${progress.totalCount} 阶段`;
  }

  function findActiveStage(job) {
    const stages = Array.isArray(job?.stages) ? job.stages : [];
    const currentStage = String(job?.current_stage || "").trim();
    if (!currentStage) {
      return null;
    }
    return stages.find((stage) => stage.key === currentStage) || null;
  }

  function buildResultHeadMeta(job) {
    if (!job?.job_id) {
      return [];
    }
    const meta = job.job_meta || {};
    const preset = meta.image_preset?.label || meta.image_preset?.name || "未指定尺寸";
    const quality = meta.image_quality || "medium";
    const stage = getStageLabel(job.current_stage || job.status);
    return [
      { label: "任务 ID", value: job.job_id },
      { label: "当前阶段", value: stage },
      { label: "输出规格", value: `${preset} · ${quality}` },
    ];
  }

  function buildTaskContext(config, job) {
    if (!job?.job_id) {
      return {
        tone: "empty",
        kicker: "新任务工作台",
        title: "先补充正文，再确认输出规格",
        description: "左侧历史区保留已完成和处理中任务；当前参数区用于准备下一次生成。",
        summary: summarizeContent(""),
        metrics: [
          { label: "默认页数", value: config?.default_pages ? `${config.default_pages} 页` : "待加载" },
          { label: "当前尺寸", value: config?.image_size || "待加载" },
          { label: "风格图", value: "可选" },
        ],
      };
    }

    const meta = job.job_meta || {};
    const summary = summarizeContent(meta.content || "");
    const pageCount = Number(meta.page_count || job.pages?.length || 0);
    const preset = meta.image_preset?.label || meta.image_preset?.name || "未指定尺寸";
    const styleCount = Array.isArray(meta.style_reference_images) ? meta.style_reference_images.length : 0;
    const statusTone = getStatusTone(job.status);
    return {
      tone: statusTone,
      kicker: `当前任务 ${job.job_id}`,
      title: summary.title,
      description: summary.preview,
      summary,
      metrics: [
        { label: "目标页数", value: pageCount > 0 ? `${pageCount} 页` : "待设置" },
        { label: "输出尺寸", value: preset },
        { label: "参考风格图", value: styleCount > 0 ? `${styleCount} 张` : "未绑定" },
      ],
    };
  }

  function buildStageOverview(job) {
    if (!job?.job_id) {
      return {
        tone: "pending",
        title: "结果总览",
        description: "提交任务后，这里会集中展示当前阶段、完成进度和下一步动作。",
        statusLabel: "等待中",
        progressText: "等待开始",
        activeStageLabel: "尚未开始",
        activeStageSummary: "提交任务后，系统会依次执行规划、参考图生成、元素图生成和 PPT 组装。",
      };
    }

    const activeStage = findActiveStage(job);
    const statusTone = getStatusTone(job.status);
    return {
      tone: statusTone,
      title: "结果总览",
      description: "这块用于快速判断任务是否在推进、卡在哪一步，以及右侧内容当前最值得关注的区域。",
      statusLabel: getStatusLabel(job.status),
      progressText: formatProgressLabel(job),
      activeStageLabel: getStageLabel(activeStage?.key || job.current_stage || job.status),
      activeStageSummary:
        activeStage?.summary ||
        (job.status === "error"
          ? job.error || "任务执行失败，请查看阶段详情。"
          : "任务正在执行中，阶段详情会随着流式状态持续刷新。"),
    };
  }

  function renderTaskContext(container, context) {
    if (!container) {
      return;
    }
    const metricHtml = context.metrics
      .map((item) => {
        return `
          <div class="task-context-metric">
            <span>${escapeHtml(item.label)}</span>
            <strong>${escapeHtml(item.value)}</strong>
          </div>
        `;
      })
      .join("");
    container.className = `task-context-card is-${escapeHtml(context.tone)}`;
    container.innerHTML = `
      <div class="task-context-head">
        <span class="task-context-kicker">${escapeHtml(context.kicker)}</span>
        <h3>${escapeHtml(context.title)}</h3>
        <p>${escapeHtml(context.description)}</p>
      </div>
      <div class="task-context-metrics">${metricHtml}</div>
    `;
  }

  function renderResultHeadMeta(container, items) {
    if (!container) {
      return;
    }
    if (!items.length) {
      container.innerHTML = "";
      return;
    }
    container.innerHTML = items
      .map((item) => {
        return `
          <span class="result-head-chip">
            <strong>${escapeHtml(item.label)}</strong>
            <span>${escapeHtml(item.value)}</span>
          </span>
        `;
      })
      .join("");
  }

  function renderStageOverview(container, overview) {
    if (!container) {
      return;
    }
    const tone = escapeHtml(overview.tone);
    container.className = `result-stage-overview is-${tone}`;
    container.innerHTML = `
      <div class="result-stage-overview-head">
        <div>
          <span class="result-stage-overview-kicker">${escapeHtml(overview.title)}</span>
          <p>${escapeHtml(overview.description)}</p>
        </div>
        <span class="stage-status is-${tone}">${escapeHtml(overview.statusLabel)}</span>
      </div>
      <div class="result-stage-overview-body">
        <div class="overview-progress-card">
          <span>阶段进度</span>
          <strong>${escapeHtml(overview.progressText)}</strong>
        </div>
        <div class="overview-progress-card">
          <span>当前聚焦</span>
          <strong>${escapeHtml(overview.activeStageLabel)}</strong>
        </div>
      </div>
      <div class="result-stage-overview-summary">${escapeHtml(overview.activeStageSummary)}</div>
    `;
  }

  globalScope.PptWorkspaceStatus = {
    render({ config, job, taskContextContainer, resultHeadMetaContainer, stageOverviewContainer }) {
      renderTaskContext(taskContextContainer, buildTaskContext(config, job));
      renderResultHeadMeta(resultHeadMetaContainer, buildResultHeadMeta(job));
      renderStageOverview(stageOverviewContainer, buildStageOverview(job));
    },
  };
})(window);
