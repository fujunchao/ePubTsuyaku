"use strict";

const { app, BrowserWindow, Menu, dialog, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const http = require("http");
const net = require("net");

const BACKEND_EXE_NAME = "ePubTsuyaku-backend.exe";
const DEV_BACKEND_URL = process.env.EPUB_TSUYAKU_DEV_URL || "http://127.0.0.1:7860";
const HEALTH_TIMEOUT_MS = 120000; // onefile exe 首次解压 + 杀软扫描可能较慢，给足时间

let mainWindow = null;
let backendProcess = null;
let backendPort = 0;
let quitting = false;

function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
  });
}

function backendExePath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "backend", BACKEND_EXE_NAME);
  }
  // 开发模式下可通过环境变量指定一个已构建的后端 exe 来调试外壳
  return process.env.EPUB_TSUYAKU_BACKEND_EXE || "";
}

function waitUntilHealthy(port, timeoutMs) {
  const startedAt = Date.now();
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const req = http.get(
        { host: "127.0.0.1", port, path: "/api/status", timeout: 2000 },
        (res) => {
          res.resume();
          if (res.statusCode === 200) {
            resolve();
            return;
          }
          retry();
        }
      );
      req.on("error", retry);
      req.on("timeout", () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      if (quitting) {
        reject(new Error("backend health check aborted: app is quitting"));
        return;
      }
      if (Date.now() - startedAt > timeoutMs) {
        reject(new Error(`backend did not become healthy within ${timeoutMs}ms`));
        return;
      }
      setTimeout(attempt, 400);
    };
    attempt();
  });
}

function spawnBackend(port) {
  const exe = backendExePath();
  if (!exe || !fs.existsSync(exe)) {
    throw new Error(`后端程序不存在: ${exe || "(未指定)"}`);
  }

  const dataDir = app.getPath("userData"); // 上传缓存 + 进度文件
  const outputDir = path.join(app.getPath("documents"), "ePubTsuyaku", "epubOutput");
  const booksDir = path.join(app.getPath("documents"), "ePubTsuyaku");
  fs.mkdirSync(dataDir, { recursive: true });
  fs.mkdirSync(outputDir, { recursive: true });
  fs.mkdirSync(booksDir, { recursive: true });

  backendProcess = spawn(exe, ["--port", String(port)], {
    cwd: path.dirname(exe),
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      EPUB_TSUYAKU_DATA_DIR: dataDir,
      EPUB_TSUYAKU_OUTPUT_DIR: outputDir,
      EPUB_TSUYAKU_BOOKS_DIR: booksDir,
    },
  });

  backendProcess.stdout.on("data", (chunk) => process.stdout.write(`[backend] ${chunk}`));
  backendProcess.stderr.on("data", (chunk) => process.stderr.write(`[backend] ${chunk}`));
  backendProcess.on("exit", (code) => {
    backendProcess = null;
    if (!quitting) {
      dialog.showErrorBox(
        "ePubTsuyaku",
        `翻译服务进程意外退出（code=${code ?? "unknown"}），应用即将关闭。`
      );
      app.quit();
    }
  });
}

function killBackend() {
  if (!backendProcess) return;
  const pid = backendProcess.pid;
  if (process.platform === "win32") {
    // onefile exe 有 bootloader 子进程，按进程树杀，避免残留
    try {
      spawn("taskkill", ["/pid", String(pid), "/T", "/F"], { windowsHide: true });
    } catch (error) {
      console.error("taskkill failed:", error);
    }
  } else {
    try {
      backendProcess.kill();
    } catch (error) {
      console.error("backend kill failed:", error);
    }
  }
  backendProcess = null;
}

function createWindow(url) {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 880,
    minWidth: 960,
    minHeight: 640,
    autoHideMenuBar: true,
    backgroundColor: "#f5efe4",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      spellcheck: false,
    },
  });

  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.loadURL(url);

  mainWindow.webContents.setWindowOpenHandler(({ url: target }) => {
    const backendOrigin = `http://127.0.0.1:${backendPort}`;
    if (/^https?:/i.test(target) && !target.startsWith(backendOrigin)) {
      shell.openExternal(target);
      return { action: "deny" };
    }
    return { action: "allow" };
  });

  // 下载输出 EPUB 时弹出系统保存对话框
  mainWindow.webContents.session.on("will-download", (_event, item) => {
    const result = dialog.showSaveDialogSync(mainWindow, {
      defaultPath: path.join(app.getPath("downloads"), item.getFilename()),
    });
    if (!result) {
      item.cancel();
      return;
    }
    item.setSavePath(result);
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

async function start() {
  try {
    Menu.setApplicationMenu(null);

    let url;
    const shouldSpawn = app.isPackaged || !!process.env.EPUB_TSUYAKU_BACKEND_EXE;
    if (shouldSpawn) {
      backendPort = await getFreePort();
      spawnBackend(backendPort);
      await waitUntilHealthy(backendPort, HEALTH_TIMEOUT_MS);
      url = `http://127.0.0.1:${backendPort}/`;
    } else {
      // 开发模式：期望开发者已手动运行 `python webui.py`
      url = DEV_BACKEND_URL;
    }
    createWindow(url);
  } catch (error) {
    handleFatalError(error);
  }
}

function handleFatalError(error) {
  const message = (error && error.message) || String(error);
  console.error(message);
  dialog.showErrorBox("ePubTsuyaku 启动失败", message);
  app.quit();
}

const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(start);

  app.on("before-quit", () => {
    quitting = true;
  });

  app.on("will-quit", () => {
    killBackend();
  });

  app.on("window-all-closed", () => {
    app.quit();
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0 && !quitting) {
      start();
    }
  });
}
