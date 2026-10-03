"use strict";

const { contextBridge } = require("electron");

// 最小桥接：渲染进程（Flask 页面）可检测桌面外壳，暂不暴露任何特权 API。
contextBridge.exposeInMainWorld("ePubTsuyaku", {
  isDesktop: true,
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
  },
});
