# ePubTsuyaku Desktop（Electron 外壳）

Electron 只做两件事：开一个原生窗口，并启动/守护 Python 翻译后端。

## 结构

- `main.js`：主进程。打包后自动启动 PyInstaller 产出的后端 sidecar（`ePubTsuyaku-backend.exe`，随机空闲端口），轮询 `/api/status` 健康检查后加载页面；应用退出时按进程树杀掉后端。
- `preload.js`：最小 contextBridge（仅暴露 `isDesktop` 标记，备用）。
- `package.json`：electron-builder 配置（NSIS 安装包 + 便携 zip），后端 exe 经 `extraResources` 打进 `resources/backend/`。

## 目录约定（打包运行时）

| 内容 | 位置 |
|---|---|
| 上传缓存、进度文件（`.webui/`） | `%APPDATA%/ePubTsuyaku` |
| 输出 EPUB | `文档/ePubTsuyaku/epubOutput` |
| 图书扫描目录（下拉框可选） | `文档/ePubTsuyaku`（把书放这里即可） |

这些位置由主进程通过 `EPUB_TSUYAKU_DATA_DIR` / `EPUB_TSUYAKU_OUTPUT_DIR` / `EPUB_TSUYAKU_BOOKS_DIR` 环境变量注入，后端在 `translator/webapp.py` 中读取。

## 本地开发

```bash
# 仓库根目录：安装 Python 依赖并启动后端
pip install -r requirements.txt
python webui.py                # http://127.0.0.1:7860

# 另开终端
cd desktop
npm install
npm start
```

想用已构建的后端 exe 调试外壳时：

```bash
set EPUB_TSUYAKU_BACKEND_EXE=path\to\ePubTsuyaku-backend.exe
npm start
```

## 构建

不在本地构建，交给 GitHub Actions（`.github/workflows/build.yml`）：

- 手动触发（workflow_dispatch）→ 产出 artifact（NSIS 安装包 + 便携 zip）
- 推送 `v*` tag → 自动附到 GitHub Release

流水线步骤：Python 单测 → PyInstaller 打后端 exe（含冒烟测试）→ electron-builder 打壳。
