const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const TARGET_URL = "http://127.0.0.1:7860/";
const OUTPUT_DIR = path.resolve(__dirname, "..", "output", "playwright");

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

async function collectShellMetrics(page, name) {
  return page.evaluate((viewportName) => {
    function rectOf(selector) {
      const node = document.querySelector(selector);
      if (!node) {
        return null;
      }
      const rect = node.getBoundingClientRect();
      return {
        selector,
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        right: Math.round(rect.right),
        bottom: Math.round(rect.bottom),
      };
    }

    function overflowState(rect) {
      if (!rect) {
        return "missing";
      }
      const overflowX = rect.x < 0 || rect.right > window.innerWidth;
      const overflowY = rect.y < 0 || rect.bottom > window.innerHeight;
      return {
        overflowX,
        overflowY,
      };
    }

    return {
      viewport: viewportName,
      window: {
        innerWidth: window.innerWidth,
        innerHeight: window.innerHeight,
      },
      document: {
        clientWidth: document.documentElement.clientWidth,
        clientHeight: document.documentElement.clientHeight,
        scrollWidth: document.documentElement.scrollWidth,
        scrollHeight: document.documentElement.scrollHeight,
        canScrollX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
        canScrollY: document.documentElement.scrollHeight > document.documentElement.clientHeight,
      },
      regions: {
        topbar: rectOf(".app-topbar"),
        workspace: rectOf(".workspace-shell"),
        historyPanel: rectOf(".history-panel"),
        controlPanel: rectOf(".control-panel"),
        resultPanel: rectOf(".result-panel"),
      },
      overflow: {
        topbar: overflowState(rectOf(".app-topbar")),
        workspace: overflowState(rectOf(".workspace-shell")),
        historyPanel: overflowState(rectOf(".history-panel")),
        controlPanel: overflowState(rectOf(".control-panel")),
        resultPanel: overflowState(rectOf(".result-panel")),
      },
      state: {
        modeText: document.querySelector("#modeText")?.textContent?.trim() || "",
        configText: document.querySelector("#configText")?.textContent?.trim() || "",
        historyCount: document.querySelectorAll(".history-item").length,
        topbarActionCount: document.querySelectorAll(".topbar-actions > *").length,
      },
    };
  }, name);
}

async function captureDialogState(page, triggerSelector, dialogSelector, name) {
  await page.click(triggerSelector);
  await page.waitForFunction((selector) => {
    const dialog = document.querySelector(selector);
    return Boolean(dialog && dialog.open);
  }, dialogSelector);

  const metrics = await page.evaluate(({ selector, viewportName }) => {
    const dialog = document.querySelector(selector);
    const rect = dialog?.getBoundingClientRect();
    const shell = dialog?.firstElementChild?.getBoundingClientRect?.();
    return {
      viewport: viewportName,
      dialog: rect
        ? {
            x: Math.round(rect.x),
            y: Math.round(rect.y),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            right: Math.round(rect.right),
            bottom: Math.round(rect.bottom),
          }
        : null,
      shell: shell
        ? {
            x: Math.round(shell.x),
            y: Math.round(shell.y),
            width: Math.round(shell.width),
            height: Math.round(shell.height),
            right: Math.round(shell.right),
            bottom: Math.round(shell.bottom),
          }
        : null,
      viewportSize: {
        innerWidth: window.innerWidth,
        innerHeight: window.innerHeight,
      },
    };
  }, { selector: dialogSelector, viewportName: name });

  await page.screenshot({
    path: path.join(OUTPUT_DIR, `${name}-${dialogSelector.replace(/[#.]/g, "")}.png`),
    fullPage: false,
  });

  await page.keyboard.press("Escape");
  await page.waitForFunction((selector) => {
    const dialog = document.querySelector(selector);
    return Boolean(dialog && !dialog.open);
  }, dialogSelector);

  return metrics;
}

async function exerciseInteractiveState(page, name) {
  await page.click("#settingsButton");
  await page.waitForFunction(() => document.querySelector("#settingsDialog")?.open);
  await page.click('[data-model-type="image"]');
  await page.waitForTimeout(200);
  const settingsState = await page.evaluate(() => ({
    activeTab: document.querySelector(".tab-button.is-active")?.textContent?.trim() || "",
    imageFieldsVisible: Array.from(document.querySelectorAll(".image-fields")).some(
      (node) => getComputedStyle(node).display !== "none"
    ),
    chatFieldsVisible: Array.from(document.querySelectorAll(".chat-fields")).some(
      (node) => getComputedStyle(node).display !== "none"
    ),
  }));
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector("#settingsDialog")?.open);

  await page.click("#editContentButton");
  await page.waitForFunction(() => document.querySelector("#contentDialog")?.open);
  await page.fill("#contentEditor", "移动端交互冒烟测试内容");
  const contentState = await page.evaluate(() => ({
    editorLength: document.querySelector("#contentEditor")?.value?.length || 0,
    saveButtonVisible: Boolean(document.querySelector("#saveContentButton")),
  }));
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector("#contentDialog")?.open);

  return {
    viewport: name,
    settingsState,
    contentState,
  };
}

async function auditViewport(browser, config) {
  const context = await browser.newContext(config.contextOptions);
  const page = await context.newPage();
  await page.goto(TARGET_URL, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".workspace-shell");
  await page.waitForTimeout(1200);

  const shellMetrics = await collectShellMetrics(page, config.name);
  await page.screenshot({
    path: path.join(OUTPUT_DIR, `${config.name}-home.png`),
    fullPage: false,
  });

  const dialogs = [];
  dialogs.push(await captureDialogState(page, "#settingsButton", "#settingsDialog", config.name));
  dialogs.push(await captureDialogState(page, "#editContentButton", "#contentDialog", config.name));
  const interactions = await exerciseInteractiveState(page, config.name);

  await context.close();
  return {
    shellMetrics,
    dialogs,
    interactions,
  };
}

async function main() {
  ensureDir(OUTPUT_DIR);

  const browser = await chromium.launch({ headless: true });
  try {
    const desktop = await auditViewport(browser, {
      name: "desktop",
      contextOptions: {
        viewport: { width: 1600, height: 900 },
      },
    });

    const mobile = await auditViewport(browser, {
      name: "mobile",
      contextOptions: {
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    });

    const result = { desktop, mobile };
    fs.writeFileSync(
      path.join(OUTPUT_DIR, "ui-audit.json"),
      JSON.stringify(result, null, 2),
      "utf8"
    );
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
