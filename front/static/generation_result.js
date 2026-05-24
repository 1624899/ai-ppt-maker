(function attachGenerationResultPresenter(globalScope) {
  // 统一封装“最终交付结果”任务，避免页面各处直接依赖后端导出字段细节。
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
    return map[stageKey] || "处理中";
  }

  function getActiveStage(job) {
    const stages = Array.isArray(job?.stages) ? job.stages : [];
    const currentStageKey = String(job?.current_stage || "").trim();
    if (!currentStageKey) {
      return {};
    }
    return stages.find((stage) => stage.key === currentStageKey) || {
      key: currentStageKey,
      label: getStageLabel(currentStageKey),
      status: job?.status || "pending",
      summary: "",
    };
  }

  function normalizeStatus(job, activeStage, exportStage) {
    if (job?.status === "completed") {
      return "completed";
    }
    if (job?.status === "error") {
      return "error";
    }
    if (job?.status === "interrupted") {
      return "interrupted";
    }
    if (job?.status === "stopping") {
      return "running";
    }
    if (job?.status === "running") {
      return "running";
    }
    if (activeStage?.status === "running") {
      return "running";
    }
    if (activeStage?.status === "completed" && exportStage?.status !== "completed") {
      return "running";
    }
    return exportStage?.status || "pending";
  }

  function getStatusLabel(status) {
    const map = {
      pending: "等待中",
      running: "进行中",
      completed: "已完成",
      error: "失败",
      interrupted: "已暂停",
    };
    return map[status] || "处理中";
  }

  function getStageSummary(job, activeStage, exportStage) {
    if (job?.status === "completed") {
      return exportStage?.summary || "可编辑 PPTX 已组装完成";
    }
    if (job?.status === "error") {
      return job?.error || exportStage?.summary || "导出失败，请查看阶段日志";
    }
    if (job?.status === "interrupted") {
      return "导出链路已暂停，可继续从当前进度恢复";
    }
    if (job?.status === "stopping") {
      return "已收到停止请求，等待当前页处理完成后暂停";
    }
    if (activeStage?.key === "queued") {
      return "任务已创建，等待开始执行整条生成与导出链路";
    }
    if (activeStage?.key === "planning") {
      return "正在进行模型规划，完成后会继续生成参考图、元素图，并自动进入 PPT 组装";
    }
    if (activeStage?.key === "reference_generation") {
      return "正在生成带文字参考图，完成后会继续生成去文字元素图";
    }
    if (activeStage?.key === "elements_generation") {
      return "正在生成去文字元素图，完成后会自动进入 CLI 后处理与 PPT 组装";
    }
    if (activeStage?.key === "ppt_export") {
      return activeStage?.summary || exportStage?.summary || "正在执行图像后处理并导出 PPTX";
    }
    return exportStage?.summary || "等待进入 CLI 后处理与 PPT 组装";
  }

  function sumAssetCount(assetPages) {
    return assetPages.reduce((total, item) => total + Number(item?.asset_count || 0), 0);
  }

  function buildActions(exportResult) {
    const actions = [];
    if (exportResult?.pptx_url) {
      actions.push({
        kind: "primary",
        label: "下载组装好的 PPT",
        href: exportResult.pptx_url,
      });
    }
    if (exportResult?.project_url) {
      actions.push({
        kind: "secondary",
        label: "查看项目快照",
        href: exportResult.project_url,
      });
    }
    return actions;
  }

  function getDeliveryType(job, exportResult, activeStage) {
    if (exportResult?.pptx_url) {
      return "可编辑 PPTX";
    }
    if (activeStage?.key === "ppt_export") {
      return "PPT 组装中";
    }
    if (job?.status === "interrupted") {
      return "已暂停";
    }
    if (job?.status === "error") {
      return "导出失败";
    }
    return "前置生成中";
  }

  function buildMetrics(job, exportResult, activeStage) {
    const assetPages = Array.isArray(exportResult?.assets?.pages) ? exportResult.assets.pages : [];
    const pageCount = Number(exportResult?.page_count || job?.reference_pages?.length || job?.pages?.length || 0);
    const currentStage = activeStage?.label || getStageLabel(job?.current_stage);
    const deliveryType = getDeliveryType(job, exportResult, activeStage);
    const assetCount = sumAssetCount(assetPages);
    return [
      {label: "最终交付", value: deliveryType},
      {label: "交付页数", value: pageCount > 0 ? `${pageCount} 页` : "待生成"},
      {label: "后处理素材", value: assetCount > 0 ? `${assetCount} 个元素` : "待处理"},
      {label: "当前阶段", value: currentStage},
    ];
  }

  function buildGenerationResultTask(job) {
    const exportStage = (job?.stages || []).find((stage) => stage.key === "ppt_export") || {};
    const exportResult = job?.result?.export || {};
    const activeStage = getActiveStage(job);
    const status = normalizeStatus(job, activeStage, exportStage);
    return {
      status,
      title: "最终交付",
      description: "前端内容规划与生图完成后，系统会自动进入 CLI 后处理组装层，最终直接交付可编辑 PPTX。",
      summary: getStageSummary(job, activeStage, exportStage),
      metrics: buildMetrics(job, exportResult, activeStage),
      actions: buildActions(exportResult),
    };
  }

  function renderLinks(linksContainer, actions) {
    if (!linksContainer) {
      return;
    }
    const links = actions.map((action) => {
      return `<a href="${escapeHtml(action.href)}" target="_blank" rel="noreferrer">${escapeHtml(action.label)}</a>`;
    });
    linksContainer.hidden = links.length === 0;
    linksContainer.innerHTML = links.join(" · ");
  }

  function renderCard(container, task) {
    if (!container) {
      return;
    }
    const metricHtml = task.metrics
      .map((item) => {
        return `
          <div class="delivery-metric">
            <span>${escapeHtml(item.label)}</span>
            <strong>${escapeHtml(item.value)}</strong>
          </div>
        `;
      })
      .join("");
    const actionHtml = task.actions
      .map((action) => {
        const actionClass = action.kind === "primary" ? "primary-button" : "secondary-button";
        return `
          <a class="delivery-action ${actionClass}" href="${escapeHtml(action.href)}" target="_blank" rel="noreferrer">
            ${escapeHtml(action.label)}
          </a>
        `;
      })
      .join("");
    container.innerHTML = `
      <section class="delivery-card is-${escapeHtml(task.status)}">
        <div class="delivery-card-head">
          <div class="delivery-copy">
            <div class="delivery-head-top">
              <h3>${escapeHtml(task.title)}</h3>
              <span class="stage-status is-${escapeHtml(task.status)}">${escapeHtml(getStatusLabel(task.status))}</span>
            </div>
            <p>${escapeHtml(task.description)}</p>
            <p class="delivery-summary">${escapeHtml(task.summary)}</p>
          </div>
        </div>
        <div class="delivery-metrics">${metricHtml}</div>
        <div class="delivery-actions">${actionHtml}</div>
      </section>
    `;
  }

  globalScope.PptGenerationResult = {
    buildGenerationResultTask,
    render({container, linksContainer, job}) {
      const task = buildGenerationResultTask(job);
      renderCard(container, task);
      renderLinks(linksContainer, task.actions);
    },
  };
})(window);
