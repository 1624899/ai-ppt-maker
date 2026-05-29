(function attachErrorLogDialog(globalScope) {
  const dialog = document.querySelector("#errorLogDialog");
  const titleNode = document.querySelector("#errorLogTitle");
  const subtitleNode = document.querySelector("#errorLogSubtitle");
  const contentNode = document.querySelector("#errorLogContent");
  const closeButton = document.querySelector("#closeErrorLogButton");

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

  function normalizeText(value, fallback = "") {
    const text = String(value || "").trim();
    return text || fallback;
  }

  function buildStageLogSections(job) {
    const stages = Array.isArray(job?.stages) ? job.stages : [];
    return stages
      .map((stage) => {
        const logs = Array.isArray(stage?.logs)
          ? stage.logs.map((item) => normalizeText(item)).filter(Boolean)
          : [];
        const summary = normalizeText(stage?.summary);
        if (!logs.length && !summary && stage?.status !== "error") {
          return "";
        }
        const lines = [];
        lines.push(`[${getStageLabel(stage?.key)} | ${normalizeText(stage?.status, "unknown")}]`);
        if (summary) {
          lines.push(`摘要：${summary}`);
        }
        if (logs.length) {
          lines.push("日志：");
          for (const log of logs) {
            lines.push(`- ${log}`);
          }
        }
        return lines.join("\n");
      })
      .filter(Boolean);
  }

  function buildJobErrorText(job, fallbackMessage = "") {
    const lines = [];
    if (job?.job_id) {
      lines.push(`任务 ID：${job.job_id}`);
    }
    if (job?.current_stage) {
      lines.push(`失败阶段：${getStageLabel(job.current_stage)}`);
    }
    if (job?.status) {
      lines.push(`任务状态：${normalizeText(job.status)}`);
    }
    const summary = normalizeText(job?.error, normalizeText(fallbackMessage, "未提供详细错误信息。"));
    lines.push("");
    lines.push("错误摘要：");
    lines.push(summary);
    const stageSections = buildStageLogSections(job);
    if (stageSections.length) {
      lines.push("");
      lines.push("阶段日志：");
      lines.push(stageSections.join("\n\n"));
    }
    return lines.join("\n");
  }

  function open(payload) {
    if (!dialog || !titleNode || !subtitleNode || !contentNode) {
      return;
    }
    titleNode.textContent = normalizeText(payload?.title, "错误日志");
    subtitleNode.textContent = normalizeText(payload?.subtitle, "这里集中展示当前任务的失败摘要与阶段日志。");
    contentNode.textContent = normalizeText(payload?.content, "暂无错误日志");
    if (!dialog.open) {
      dialog.showModal();
    }
  }

  function openForJob(job, fallbackMessage = "") {
    open({
      title: job?.job_id ? `任务 ${job.job_id} 错误日志` : "错误日志",
      subtitle: job?.current_stage
        ? `失败阶段：${getStageLabel(job.current_stage)}`
        : "这里集中展示当前任务的失败摘要与阶段日志。",
      content: buildJobErrorText(job, fallbackMessage),
    });
  }

  function close() {
    if (dialog?.open) {
      dialog.close();
    }
  }

  closeButton?.addEventListener("click", close);

  globalScope.PptErrorLogDialog = {
    close,
    open,
    openForJob,
  };
})(window);
