# Changelog

## 0.1.3 - 2026-07-09

- 更新中文修复适配说明，覆盖 OpenAI 在 7月9日 发布的 ChatGPT、Work 和 Codex 三合一的全新桌面端。
- 说明新版统一桌面端下先运行菜单 `8` 检查可补丁字符串，再按需使用菜单 `2` 重建便携版。
- 保留旧 Codex Desktop 菜单补丁兼容路径，降低官方安装目录变化带来的重建成本。

## 0.1.2 - 2026-05-05

- 修复新版 Codex 中 `View` / `Window` 子菜单仍显示英文的问题。
- 在 `Menu.setApplicationMenu(...)` 前注入菜单 label 映射，覆盖 Electron role 菜单和运行时生成的菜单项。
- 修复 `--rebuild --patch-menu` 组合不会实际重建便携版的问题。
- 已通过 `--rebuild --launch` 完整脚本路径验证，不依赖手工修改。

## 0.1.1 - 2026-05-05

- 修复 Windows PowerShell 5.1 将无 BOM UTF-8 `.ps1` 按 ANSI 解析导致双击入口闪退的问题。
- 将中文交互菜单移动到 Python 主脚本，PowerShell wrapper 保持 ASCII-only。
- `.bat` 入口在异常退出时保留窗口，方便用户看到错误信息。
- 动态识别 `.vite/build/main-*.js` 菜单文件，避免官方构建 hash 变化导致 dry-run 报错。
- 直接从菜单启动便携版时也设置独立 `CODEX_ELECTRON_USER_DATA_PATH`。
- 已在 Windows PowerShell 5.1 下测试 `.bat` 菜单入口、路径显示和 dry-run。

## 0.1.0 - 2026-04-27

- 初始发布。
- 生成 Windows Codex Desktop 中文便携副本。
- 复用官方 `zh-CN` 资源，并补丁 File/Edit/View/Window/Help 菜单残留英文。
- 设置独立 `CODEX_ELECTRON_USER_DATA_PATH`，避免和官方版争用单实例锁。
- 同步更新 ASAR integrity 与 `Codex.exe` 内的 ASAR header hash。
- 创建桌面和开始菜单快捷方式。
