# 发布清单

发布前请确认：

```powershell
python -m py_compile .\codex_desktop_zh_cn_windows.py
python .\codex_desktop_zh_cn_windows.py --dry-run
```

检查仓库中不得包含：

- 官方 Codex Desktop 安装包或复制出的应用目录。
- `.asar`、`.exe`、`.dll`、`.pak` 等官方运行时文件。
- `%LOCALAPPDATA%\CodexZhCN` 中的运行时内容。
- 账号数据、访问令牌、API key、日志、本地配置。

建议发布步骤：

```powershell
git init
git add .
git commit -m "Initial release"
git branch -M main
git remote add origin https://github.com/<user>/<repo>.git
git push -u origin main
```

如果要发布 release，只打包脚本和文档，不要打包官方应用副本。
