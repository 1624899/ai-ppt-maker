(function attachWorkspaceStatusPresenter(globalScope) {
  // 统一封装工作台状态摘要，避免页面脚本分散拼接桌面端提示文案。
  const pageRichnessHelpers = globalScope.PptPageRichness || null;

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
      ppt_export: "可编辑元素生成",
      completed: "全部完成",
    };
    return map[String(stageKey || "").trim()] || "处理中";
  }

  function formatPageRichnessLabel(value, fallback = "medium") {
    if (pageRichnessHelpers?.formatLabel) {
      return pageRichnessHelpers.formatLabel(value, fallback);
    }
    return String(value || fallback || "medium");
  }

  function buildTaskContext(config, job) {
    if (!job?.job_id) {
      return {
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
    const richnessDefault = formatPageRichnessLabel(
      meta.generation_options?.page_richness_default,
      "medium"
    );
    const targetLabel = String(meta.job_target_label || (meta.job_target === "reference_only" ? "图片版 PPT" : "可编辑元素"));
    return {
      kicker: `当前任务 ${job.job_id}`,
      title: summary.title,
      description: summary.preview,
      summary,
      metrics: [
        { label: "目标页数", value: pageCount > 0 ? `${pageCount} 页` : "待设置" },
        { label: "输出模式", value: targetLabel },
        { label: "输出尺寸", value: preset },
        { label: "默认丰富度", value: richnessDefault },
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
        activeStageSummary: "提交任务后，系统会依次执行规划、参考图生成、元素图生成和可编辑元素生成。",
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
      allowErrorLog: job.status === "error",
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
    container.className = "task-context-card";
    container.innerHTML = `
      <div class="task-context-head">
        <span class="task-context-kicker">${escapeHtml(context.kicker)}</span>
        <h3>${escapeHtml(context.title)}</h3>
        <p>${escapeHtml(context.description)}</p>
      </div>
      <div class="task-context-metrics">${metricHtml}</div>
    `;
  }

  globalScope.PptWorkspaceStatus = {
    render({ config, job, taskContextContainer }) {
      renderTaskContext(taskContextContainer, buildTaskContext(config, job));
    },
  };
})(window);
