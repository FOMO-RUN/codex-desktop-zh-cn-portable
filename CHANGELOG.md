# Changelog

## 0.1.0 - 2026-04-27

- 初始发布。
- 生成 Windows Codex Desktop 中文便携副本。
- 复用官方 `zh-CN` 资源，并补丁 File/Edit/View/Window/Help 菜单残留英文。
- 设置独立 `CODEX_ELECTRON_USER_DATA_PATH`，避免和官方版争用单实例锁。
- 同步更新 ASAR integrity 与 `Codex.exe` 内的 ASAR header hash。
- 创建桌面和开始菜单快捷方式。
