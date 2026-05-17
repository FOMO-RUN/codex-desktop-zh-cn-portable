#!/usr/bin/env python3
"""
Windows zh-CN portable patcher for Codex Desktop.

This tool creates a writable portable copy of the official Windows packaged
Codex Desktop app, then patches native menu strings that are still hardcoded in
English. It does not modify the protected WindowsApps installation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import stat
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any


APPX_NAME = "OpenAI.Codex"
LANG_CODE = "zh-CN"
TOOL_NAME = "CodexZhCN"


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check)


def local_app_data() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    return Path(value) if value else Path.home() / "AppData/Local"


def roaming_app_data() -> Path:
    value = os.environ.get("APPDATA")
    return Path(value) if value else Path.home() / "AppData/Roaming"


def tool_root() -> Path:
    return local_app_data() / TOOL_NAME


def default_target_dir() -> Path:
    return tool_root() / "Codex"


def launcher_path() -> Path:
    return tool_root() / "launch_codex_zh_cn.vbs"


def powershell_exe() -> str:
    return "powershell.exe"


def ps_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def app_exe(app_dir: Path) -> Path | None:
    for name in ["Codex.exe", "codex.exe"]:
        exe = app_dir / name
        if exe.exists():
            return exe
    return None


def app_asar(app_dir: Path) -> Path:
    return app_dir / "resources" / "app.asar"


def app_version(app_dir: Path) -> str | None:
    version_file = app_dir / "version"
    if version_file.exists():
        version = version_file.read_text(encoding="utf-8", errors="ignore").strip()
        if version:
            return version

    exe = app_exe(app_dir)
    if not exe:
        return None
    script = f"(Get-Item -LiteralPath {ps_single_quote(str(exe))}).VersionInfo.ProductVersion"
    result = run([powershell_exe(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], check=False)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines[0] if lines else None


def find_appx_install_location() -> Path | None:
    script = (
        f"Get-AppxPackage -Name {APPX_NAME} -ErrorAction SilentlyContinue | "
        "Sort-Object Version -Descending | "
        "Select-Object -First 1 -ExpandProperty InstallLocation"
    )
    result = run([powershell_exe(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], check=False)
    for line in result.stdout.splitlines():
        value = line.strip()
        if not value:
            continue
        path = Path(value)
        if path.exists():
            return path
    return None


def normalize_app_dir(source: Path) -> Path:
    source = source.expanduser()
    if source.is_file() and source.name.lower() == "codex.exe":
        source = source.parent

    candidates = [
        source,
        source / "app",
    ]
    for candidate in candidates:
        if (candidate / "Codex.exe").exists() and app_asar(candidate).exists():
            return candidate
        if (candidate / "codex.exe").exists() and app_asar(candidate).exists():
            return candidate
    raise SystemExit(f"无法识别 Codex Desktop 应用目录：{source}")


def find_source_app_dir() -> Path | None:
    location = find_appx_install_location()
    if location:
        try:
            return normalize_app_dir(location)
        except SystemExit:
            pass

    candidates = [
        local_app_data() / "Programs" / "Codex",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Codex",
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                return normalize_app_dir(candidate)
            except SystemExit:
                continue
    return None


def resolve_source(args: argparse.Namespace) -> Path:
    if args.source:
        return normalize_app_dir(args.source)
    source = find_source_app_dir()
    if source:
        return source
    raise SystemExit("未找到官方 Codex Desktop。请先安装 Codex Desktop，或通过 --source 指定应用目录。")


def is_within(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
        resolved_root = root.resolve()
    except OSError:
        resolved = path.absolute()
        resolved_root = root.absolute()
    return resolved == resolved_root or resolved_root in resolved.parents


def make_writable(path: Path) -> None:
    if not path.exists():
        return
    for child in path.rglob("*"):
        try:
            mode = stat.S_IREAD | stat.S_IWRITE
            if child.is_dir():
                mode |= stat.S_IEXEC
            os.chmod(child, mode)
        except OSError:
            pass
    try:
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
    except OSError:
        pass


def copy_app_dir(source: Path, target: Path, *, rebuild: bool) -> Path:
    source = normalize_app_dir(source)
    target = target.expanduser()
    if target.exists():
        if not rebuild:
            print(f"复用现有便携版：{target}")
            make_writable(target)
            return target
        if not is_within(target, tool_root()):
            raise SystemExit(f"拒绝删除工具目录之外的目标目录：{target}")
        backup = target.with_name(f"{target.name}.bak-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}")
        if backup.exists():
            shutil.rmtree(backup)
        make_writable(target)
        target.rename(backup)
        print(f"已备份旧便携版：{backup}")

    print(f"复制 Codex Desktop：{source} -> {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, symlinks=True)
    make_writable(target)
    print(f"已创建便携版：{target}")
    return target


def shortcut_paths() -> dict[str, Path]:
    return {
        "桌面": Path.home() / "Desktop" / "Codex zh-CN.lnk",
        "开始菜单": roaming_app_data() / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Codex zh-CN.lnk",
    }


def create_launcher(target_dir: Path) -> Path:
    exe = app_exe(target_dir.expanduser())
    if not exe:
        raise SystemExit(f"未找到 Codex.exe：{target_dir}")

    launcher = launcher_path()
    launcher.parent.mkdir(parents=True, exist_ok=True)
    user_data_dir = tool_root() / "userData"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    exe_path = str(exe).replace('"', '""')
    working_dir = str(exe.parent).replace('"', '""')
    user_data = str(user_data_dir).replace('"', '""')
    content = f'''Set shell = CreateObject("WScript.Shell")
Set env = shell.Environment("PROCESS")
env("CODEX_ELECTRON_USER_DATA_PATH") = "{user_data}"
shell.CurrentDirectory = "{working_dir}"
shell.Run """" & "{exe_path}" & """ --lang={LANG_CODE}", 1, False
'''
    launcher.write_text(content, encoding="utf-8")
    print(f"已创建启动器：{launcher}")
    return launcher


def create_windows_shortcut(
    shortcut: Path,
    target: Path,
    description: str,
    *,
    arguments: str | None = None,
    working_directory: Path | None = None,
    icon: Path | None = None,
) -> None:
    shortcut.parent.mkdir(parents=True, exist_ok=True)
    script = f"""
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut({ps_single_quote(str(shortcut))})
$link.TargetPath = {ps_single_quote(str(target))}
$link.WorkingDirectory = {ps_single_quote(str(working_directory or target.parent))}
$link.IconLocation = {ps_single_quote(str(icon or target) + ',0')}
$link.Description = {ps_single_quote(description)}
{f"$link.Arguments = {ps_single_quote(arguments)}" if arguments else ""}
$link.Save()
"""
    result = run([powershell_exe(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], check=False)
    if result.returncode != 0:
        raise SystemExit(result.stdout.strip() or f"创建快捷方式失败：{shortcut}")


def create_shortcuts(target_dir: Path) -> int:
    exe = app_exe(target_dir.expanduser())
    if not exe:
        raise SystemExit(f"未找到 Codex.exe：{target_dir}")

    launcher = create_launcher(target_dir)
    wscript = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wscript.exe"
    for label, shortcut in shortcut_paths().items():
        create_windows_shortcut(
            shortcut,
            wscript,
            "Codex Desktop zh-CN",
            arguments=f'"{launcher}"',
            working_directory=launcher.parent,
            icon=exe,
        )
        print(f"已创建{label}快捷方式：{shortcut}")
    return 0


def launch(app_dir: Path) -> None:
    exe = app_exe(app_dir.expanduser())
    if not exe:
        raise SystemExit(f"未找到 Codex.exe：{app_dir}")
    print(f"启动 Codex：{exe}")
    user_data_dir = tool_root() / "userData"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["CODEX_ELECTRON_USER_DATA_PATH"] = str(user_data_dir)
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [str(exe), f"--lang={LANG_CODE}"],
        cwd=str(exe.parent),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creationflags,
    )


def parse_asar(data: bytes) -> tuple[int, int, int, dict[str, Any]]:
    if len(data) < 16:
        raise ValueError("ASAR 文件过小。")
    header_size = struct.unpack_from("<I", data, 4)[0]
    json_size = struct.unpack_from("<I", data, 12)[0]
    json_start = data.index(b'{"files"', 0, 64)
    json_end = json_start + json_size
    content_base = 8 + header_size
    header = json.loads(data[json_start:json_end].decode("utf-8"))
    if not isinstance(header, dict):
        raise ValueError("ASAR header 不是 JSON object。")
    return json_start, json_end, content_base, header


def asar_file_entries(header: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    entries: list[tuple[str, dict[str, Any]]] = []

    def walk(node: dict[str, Any], prefix: str = "") -> None:
        files = node.get("files")
        if isinstance(files, dict):
            for name, child in files.items():
                if isinstance(child, dict):
                    walk(child, f"{prefix}/{name}" if prefix else name)
            return
        if "offset" in node and "size" in node:
            entries.append((prefix, node))

    walk(header)
    return entries


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def asar_header_hash(data: bytes) -> str:
    json_start, json_end, _, _ = parse_asar(data)
    return sha256_hex(data[json_start:json_end])


def sha256_blocks(data: bytes, block_size: int) -> list[str]:
    if block_size <= 0:
        return [sha256_hex(data)]
    if not data:
        return [sha256_hex(data)]
    return [sha256_hex(data[index : index + block_size]) for index in range(0, len(data), block_size)]


def align4(value: int) -> int:
    return (value + 3) & ~3


def nonempty_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def backup_file(path: Path, reason: str) -> Path:
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak-{reason}-{timestamp}")
    shutil.copy2(path, backup)
    return backup


def exact_width(source: str, target: str) -> tuple[bytes, bytes]:
    source_bytes = source.encode("utf-8")
    target_bytes = target.encode("utf-8")
    if len(target_bytes) > len(source_bytes):
        raise ValueError(f"替换文本过长：{target!r} > {source!r}")
    return source_bytes, target_bytes + (b" " * (len(source_bytes) - len(target_bytes)))


def codex_menu_replacements() -> list[tuple[bytes, bytes]]:
    specs = [
        ("label:`Settings…`", "label:`设置…`"),
        ("label:`New Chat`", "label:`新建`"),
        ("label:`Quick Chat`", "label:`快聊`"),
        ("label:`New Window`", "label:`新窗口`"),
        ("label:`Open Folder…`", "label:`文件夹…`"),
        ("label:`Log Out`", "label:`登出`"),
        ("label:`Command Menu…`", "label:`命令菜单…`"),
        ("label:`Search Files…`", "label:`搜索文件…`"),
        ("label:`Search Chats…`", "label:`搜索聊天…`"),
        ("label:`Copy conversation path`", "label:`复制会话路径`"),
        ("label:`Pin/unpin chat`", "label:`固定聊天`"),
        ("label:`Rename chat`", "label:`重命名`"),
        ("label:`Archive chat`", "label:`归档聊天`"),
        ("label:`Copy working directory`", "label:`复制工作目录`"),
        ("label:`Copy session id`", "label:`复制会话 ID`"),
        ("label:`Copy deeplink`", "label:`复制深链`"),
        ("label:`About ${n.app.getName()}`", "label:`关于${n.app.getName()}`"),
        ("title:`About ${e}`", "title:`关于${e}`"),
        ("label:`Toggle Sidebar`", "label:`侧边栏`"),
        ("label:`Toggle Terminal`", "label:`切换终端`"),
        ("label:`Toggle File Tree`", "label:`切换文件树`"),
        ("label:`Toggle Browser Panel`", "label:`浏览器面板`"),
        ("label:`Reload Window`", "label:`重载窗口`"),
        ("label:`Toggle Diff Panel`", "label:`差异面板`"),
        ("label:`Find`", "label:`找`"),
        ("label:`Previous Chat`", "label:`上个聊天`"),
        ("label:`Next Chat`", "label:`下个`"),
        ("label:`Toggle Debug Menu`", "label:`调试菜单`"),
        ("label:`Open Deeplink from Clipboard`", "label:`从剪贴板打开深链`"),
        ("title:`Invalid Deeplink`", "title:`无效深链`"),
        ("label:`Toggle Query Devtools`", "label:`查询开发工具`"),
        ("label:`Back`", "label:`退`"),
        ("label:`Forward`", "label:`前进`"),
        ("label:`Check for Updates…`", "label:`检查更新…`"),
        ("title:`Updates Unavailable`", "title:`更新不可用`"),
        ("label:`Zoom In`", "label:`放大`"),
        ("label:`Zoom Out`", "label:`缩小`"),
        ("label:`Actual Size`", "label:`实际`"),
        ("label:`Codex Documentation`", "label:`Codex 文档`"),
        ("label:`What's new`", "label:`新功能`"),
        ("label:`Automations`", "label:`自动化`"),
        ("label:`Local Environments`", "label:`本地环境`"),
        ("label:`Worktrees`", "label:`工作树`"),
        ("label:`Skills`", "label:`技能`"),
        ("label:`Model Context Protocol`", "label:`模型上下文协议`"),
        ("label:`Troubleshooting`", "label:`故障排除`"),
        ("label:`Send Feedback`", "label:`发送反馈`"),
        ("label:`Keyboard Shortcuts`", "label:`键盘快捷键`"),
        ("`Start Performance Trace`", "`性能跟踪`"),
        ("`Stop Performance Trace`", "`停止跟踪`"),
        ("`Waiting to Start Trace…`", "`等待开始跟踪…`"),
        ("`Saving Trace…`", "`保存中…`"),
        ("`Waiting for Trace Details…`", "`等待跟踪详情…`"),
        ("`Uploading Trace…`", "`上传跟踪…`"),
        (
            "let e=B.items.findIndex(e=>e.role===`quit`);e>=0?B.insert(e,new n.MenuItem(T)):(B.append(new n.MenuItem(T)),B.append(new n.MenuItem({role:`quit`})))",
            "let e=B.items.findIndex(e=>e.role===`quit`);B.items[e].label=`退出`,B.insert(e,new n.MenuItem(T))",
        ),
    ]
    return [exact_width(source, target) for source, target in specs]


MAIN_JS_REL_FALLBACK = ".vite/build/main-BBYeJ7_G.js"
MAIN_MENU_MARKERS = [
    "Menu.buildFromTemplate",
    "getMenuItemById",
    "role:`quit`",
    "Codex Documentation",
    "],Ge=n.Menu.buildFromTemplate(We),B=Ge.getMenuItemById(e.It.file)?.submenu;",
    "Qe(Ge,e.It.edit,[[0,`撤销`]",
    "],Qe=n.Menu.buildFromTemplate(Ze),$e=Qe.getMenuItemById(e.Qt.file)?.submenu;",
    "n.Menu.setApplicationMenu(Qe)",
]


def asar_entry(header: dict[str, Any], path: str) -> dict[str, Any]:
    node: dict[str, Any] = header
    for part in path.split("/"):
        files = node.get("files")
        if not isinstance(files, dict) or part not in files:
            raise KeyError(path)
        child = files[part]
        if not isinstance(child, dict):
            raise KeyError(path)
        node = child
    return node


def find_codex_main_menu_js(
    header: dict[str, Any],
    data: bytes,
    content_base: int,
) -> tuple[str, dict[str, Any], str]:
    candidates = []
    try:
        candidates.append((MAIN_JS_REL_FALLBACK, asar_entry(header, MAIN_JS_REL_FALLBACK)))
    except KeyError:
        pass
    candidates.extend(
        (path, entry)
        for path, entry in asar_file_entries(header)
        if path.startswith(".vite/build/main-") and path.endswith(".js") and not entry.get("unpacked")
    )

    seen: set[str] = set()
    for path, entry in candidates:
        if path in seen:
            continue
        seen.add(path)
        try:
            offset = content_base + int(entry["offset"])
            size = int(entry["size"])
        except (KeyError, TypeError, ValueError):
            continue
        try:
            text = data[offset : offset + size].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if sum(1 for marker in MAIN_MENU_MARKERS if marker in text) >= 3:
            return path, entry, text

    return "", {}, ""


def find_webview_locale_js(
    header: dict[str, Any],
    data: bytes,
    content_base: int,
) -> tuple[str, dict[str, Any], str]:
    candidates = [
        (path, entry)
        for path, entry in asar_file_entries(header)
        if path.startswith("webview/assets/app-main-") and path.endswith(".js") and not entry.get("unpacked")
    ]
    for path, entry in candidates:
        try:
            offset = content_base + int(entry["offset"])
            size = int(entry["size"])
        except (KeyError, TypeError, ValueError):
            continue
        try:
            text = data[offset : offset + size].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if "codex_i18n_locale_resolved" in text and "locale_source" in text and "LOCALE_OVERRIDE" in text:
            return path, entry, text
    return "", {}, ""


def apply_webview_locale_force_patch(text: str) -> tuple[str, int]:
    changes = 0
    replacements = [
        ("(0,Q.useMemo)(()=>n?.get(`enable_i18n`,!1),[n])", "(0,Q.useMemo)(()=>!0,[n])"),
        (
            "(0,Q.useMemo)(()=>a||(i===`SYSTEM`?s:i===`FIRST_AVAILABLE`?o!==void 0&&!gh(o)?o:s!==void 0&&!gh(s)?s:void 0:o),[o,a,i,s])",
            "(0,Q.useMemo)(()=>a??`zh-CN`,[a])",
        ),
    ]
    for source, target in replacements:
        count = text.count(source)
        if count:
            text = text.replace(source, target)
            changes += count
    return text, changes


def find_webview_js_by_markers(
    header: dict[str, Any],
    data: bytes,
    content_base: int,
    *,
    startswith: str,
    markers: list[str],
) -> tuple[str, dict[str, Any], str]:
    candidates = [
        (path, entry)
        for path, entry in asar_file_entries(header)
        if path.startswith(startswith) and path.endswith(".js") and not entry.get("unpacked")
    ]
    for path, entry in candidates:
        try:
            offset = content_base + int(entry["offset"])
            size = int(entry["size"])
        except (KeyError, TypeError, ValueError):
            continue
        try:
            text = data[offset : offset + size].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if all(marker in text for marker in markers):
            return path, entry, text
    return "", {}, ""


def apply_webview_ui_string_patch(text: str, replacements: list[tuple[str, str]]) -> tuple[str, int]:
    changes = 0
    for source, target in replacements:
        count = text.count(source)
        if count:
            text = text.replace(source, target)
            changes += count
    return text, changes


def apply_codex_main_menu_logic_patch(text: str) -> tuple[str, int]:
    changes = 0

    replacements = [
        ("label:`新建`", "label:`新聊天`"),
        ("label:`快聊`", "label:`快速聊天`"),
        ("label:`文件夹…`", "label:`打开文件夹…`"),
        ("label:`登出`", "label:`退出登录`"),
        ("label:`侧边栏`", "label:`切换侧边栏`"),
        ("label:`浏览器面板`", "label:`切换浏览器面板`"),
        ("label:`差异面板`", "label:`切换差异面板`"),
        ("label:`找`", "label:`查找`"),
        ("label:`下个`", "label:`下个聊天`"),
        ("label:`调试菜单`", "label:`切换调试菜单`"),
        ("label:`退`", "label:`后退`"),
        ("label:`实际`", "label:`实际大小`"),
        ("label:_.formatMessage({messageId:e.Fn,defaultMessage:e.Pn})", "label:`打开浏览器标签页`"),
        ("label:_.formatMessage({messageId:e.Ln,defaultMessage:e.In})", "label:`重新加载浏览器页面`"),
        ("label:_.formatMessage({messageId:e.Nn,defaultMessage:e.Mn})", "label:`强制重新加载浏览器页面`"),
        ("{role:`togglefullscreen`}", "{label:`切换全屏`,role:`togglefullscreen`}"),
    ]

    for source, target in replacements:
        count = text.count(source)
        if count:
            text = text.replace(source, target)
            changes += count

    legacy_marker = "],Ge=n.Menu.buildFromTemplate(We),B=Ge.getMenuItemById(e.It.file)?.submenu;"
    legacy_injection = (
        "],Ge=n.Menu.buildFromTemplate(We),Qe=(t,r,i)=>{let a=t.getMenuItemById(r)?.submenu;"
        "if(a)for(let[t,r]of i){let i=a.items[t];i&&(i.label=r)}};"
        "Qe(Ge,e.It.edit,[[0,`撤销`],[1,`重做`],[3,`剪切`],[4,`复制`],[5,`粘贴`],[6,`删除`],[8,`全选`]]);"
        "Qe(Ge,e.It.window,[[0,`最小化`],[1,`缩放`],[2,`关闭`]]);"
        "B=Ge.getMenuItemById(e.It.file)?.submenu;"
    )
    if legacy_marker in text and "Qe(Ge,e.It.edit,[[0,`撤销`]" not in text:
        text = text.replace(legacy_marker, legacy_injection, 1)
        changes += 1

    current_marker = "],Qe=n.Menu.buildFromTemplate(Ze),$e=Qe.getMenuItemById(e.Qt.file)?.submenu;"
    current_injection = (
        "],Qe=n.Menu.buildFromTemplate(Ze),$z=(t,r,i)=>{let a=t.getMenuItemById(r)?.submenu;"
        "if(a)for(let[t,r]of i){let i=a.items[t];i&&(i.label=r)}};"
        "$z(Qe,e.Qt.edit,[[0,`撤销`],[1,`重做`],[3,`剪切`],[4,`复制`],[5,`粘贴`],[6,`删除`],[8,`全选`]]);"
        "$z(Qe,e.Qt.window,[[0,`最小化`],[1,`缩放`],[2,`关闭`]]);"
        "$e=Qe.getMenuItemById(e.Qt.file)?.submenu;"
    )
    if current_marker in text and "$z(Qe,e.Qt.edit,[[0,`撤销`]" not in text:
        text = text.replace(current_marker, current_injection, 1)
        changes += 1

    zh_label_map = {
        "File": "文件",
        "Edit": "编辑",
        "View": "视图",
        "Window": "窗口",
        "Help": "帮助",
        "Settings…": "设置…",
        "Settings...": "设置...",
        "New Chat": "新聊天",
        "Quick Chat": "快速聊天",
        "New Window": "新窗口",
        "Open Folder…": "打开文件夹…",
        "Open Folder...": "打开文件夹...",
        "Log Out": "退出登录",
        "Exit": "退出",
        "Quit Codex": "退出 Codex",
        "About Codex": "关于 Codex",
        "Command Menu…": "命令菜单…",
        "Command Menu...": "命令菜单...",
        "Open command menu": "打开命令菜单",
        "Search Files…": "搜索文件…",
        "Search Files...": "搜索文件...",
        "Search Chats…": "搜索聊天…",
        "Search Chats...": "搜索聊天...",
        "Copy conversation path": "复制会话路径",
        "Copy working directory": "复制工作目录",
        "Copy session id": "复制会话 ID",
        "Copy deeplink": "复制深链",
        "Pin/unpin chat": "固定/取消固定聊天",
        "Rename chat": "重命名聊天",
        "Archive chat": "归档聊天",
        "Undo": "撤销",
        "Redo": "重做",
        "Cut": "剪切",
        "Copy": "复制",
        "Paste": "粘贴",
        "Delete": "删除",
        "Select All": "全选",
        "Toggle Sidebar": "切换侧边栏",
        "Toggle Side Panel": "切换侧边栏",
        "Toggle Terminal": "切换终端",
        "Toggle File Tree": "切换文件树",
        "Toggle Browser Panel": "切换浏览器面板",
        "Open Browser Tab": "打开浏览器标签页",
        "Focus Browser Address Bar": "聚焦浏览器地址栏",
        "Reload Browser Page": "重新加载浏览器页面",
        "Hard Reload Browser Page": "强制重新加载浏览器页面",
        "Toggle Diff Panel": "切换差异面板",
        "Find": "查找",
        "Previous Chat": "上个聊天",
        "Next Chat": "下个聊天",
        "Back": "后退",
        "Forward": "前进",
        "Reload Window": "重载窗口",
        "Toggle Debug Menu": "切换调试菜单",
        "Open Deeplink from Clipboard": "从剪贴板打开深链",
        "Invalid Deeplink": "无效深链",
        "Toggle Query Devtools": "切换查询开发工具",
        "Zoom In": "放大",
        "Zoom Out": "缩小",
        "Actual Size": "实际大小",
        "Toggle Full Screen": "切换全屏",
        "Minimize": "最小化",
        "Zoom": "缩放",
        "Close": "关闭",
        "Check for Updates…": "检查更新…",
        "Updates Unavailable": "更新不可用",
        "Codex Documentation": "Codex 文档",
        "What's new": "新功能",
        "Automations": "自动化",
        "Local Environments": "本地环境",
        "Worktrees": "工作树",
        "Skills": "技能",
        "Model Context Protocol": "模型上下文协议",
        "Troubleshooting": "故障排除",
        "Send Feedback": "发送反馈",
        "Keyboard Shortcuts": "键盘快捷键",
        "Start Trace Recording": "开始跟踪记录",
        "Stop Trace Recording": "停止跟踪记录",
        "Start Performance Trace": "开始性能跟踪",
        "Stop Performance Trace": "停止性能跟踪",
        "Waiting to Start Trace…": "等待开始跟踪…",
        "Saving Trace…": "保存跟踪…",
        "Waiting for Trace Details…": "等待跟踪详情…",
        "Uploading Trace…": "上传跟踪…",
    }
    label_map_js = json.dumps(zh_label_map, ensure_ascii=False, separators=(",", ":"))
    normalizer_expr = (
        "globalThis.__codexZhCNMenuLabels=1,"
        "((m,l)=>{let walk=i=>{if(!i)return;let label=l[i.label];"
        "if(label)i.label=label;let items=i.submenu?.items;"
        "if(Array.isArray(items))items.forEach(walk)};m.items?.forEach(walk)})"
        f"(__MENU__,{label_map_js})"
    )

    app_menu_markers = [
        ("n.Menu.setApplicationMenu(Ke),aT(h)", "Ke"),
        ("n.Menu.setApplicationMenu(Ge)", "Ge"),
        ("n.Menu.setApplicationMenu(Qe)", "Qe"),
    ]
    if "__codexZhCNMenuLabels" not in text:
        for marker_text, menu_var in app_menu_markers:
            if marker_text in text:
                injected = ";" + normalizer_expr.replace("__MENU__", menu_var) + "," + marker_text
                text = text.replace(marker_text, injected, 1)
                changes += 1
                break

    return text, changes


def patch_asar_embedded_file(
    asar: Path,
    path: str,
    new_content: bytes,
) -> tuple[bool, str, str]:
    data = bytearray(asar.read_bytes())
    json_start, json_end, content_base, header = parse_asar(bytes(data))
    old_header_hash = sha256_hex(bytes(data[json_start:json_end]))
    entry = asar_entry(header, path)
    if entry.get("unpacked"):
        raise SystemExit(f"拒绝改写 unpacked ASAR 文件：{path}")

    try:
        old_offset = int(entry["offset"])
        old_size = int(entry["size"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"ASAR 条目缺少 offset/size：{path}") from exc

    old_start = content_base + old_offset
    old_end = old_start + old_size
    if bytes(data[old_start:old_end]) == new_content:
        return False, old_header_hash, old_header_hash

    delta = len(new_content) - old_size
    if delta:
        for _, candidate in asar_file_entries(header):
            if candidate is entry or candidate.get("unpacked"):
                continue
            try:
                candidate_offset = int(candidate["offset"])
            except (KeyError, TypeError, ValueError):
                continue
            if candidate_offset > old_offset:
                candidate["offset"] = str(candidate_offset + delta)

    entry["size"] = len(new_content)
    integrity = entry.get("integrity")
    if not isinstance(integrity, dict):
        raise SystemExit(f"ASAR 条目缺少 integrity：{path}")
    block_size = int(integrity.get("blockSize") or 4194304)
    integrity["algorithm"] = "SHA256"
    integrity["hash"] = sha256_hex(new_content)
    integrity["blockSize"] = block_size
    integrity["blocks"] = sha256_blocks(new_content, block_size)

    content = bytearray(data[content_base:])
    content[old_offset : old_offset + old_size] = new_content
    header_bytes = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    json_size = len(header_bytes)
    pickle_size = align4(4 + json_size)
    header_size = 4 + pickle_size
    padding = b"\0" * (pickle_size - 4 - json_size)
    rebuilt = bytearray()
    rebuilt.extend(struct.pack("<IIII", 4, header_size, pickle_size, json_size))
    rebuilt.extend(header_bytes)
    rebuilt.extend(padding)
    rebuilt.extend(content)

    new_header_hash = sha256_hex(header_bytes)
    tmp = asar.with_suffix(asar.suffix + ".tmp")
    tmp.write_bytes(rebuilt)
    try:
        os.replace(tmp, asar)
    except PermissionError:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise SystemExit(
            "无法写入 app.asar，通常是 Codex zh-CN 便携版仍在运行。"
            "请完全退出便携版后再运行补丁。"
        )
    return True, old_header_hash, new_header_hash


def patch_codex_main_menu_logic(app_dir: Path, dry_run: bool = False) -> tuple[int, str | None, str | None]:
    asar = app_asar(app_dir.expanduser())
    data = asar.read_bytes()
    _, _, content_base, header = parse_asar(data)
    main_js_rel, _, old_text = find_codex_main_menu_js(header, data, content_base)
    if not main_js_rel:
        print("未定位到 Codex 主菜单逻辑文件，已跳过额外逻辑补丁。")
        return 0, None, None
    new_text, changes = apply_codex_main_menu_logic_patch(old_text)

    if dry_run:
        print(f"[dry-run] Codex 主菜单逻辑文件：{main_js_rel}")
        print(f"[dry-run] Codex 主菜单逻辑补丁还需处理 {changes} 处。")
        return changes, None, None

    if changes == 0:
        print("Codex 主菜单逻辑补丁已应用，或当前版本不需要。")
        return 0, None, None

    backup = backup_file(asar, "before-menu-logic-zh-CN")
    try:
        changed, old_hash, new_hash = patch_asar_embedded_file(asar, main_js_rel, new_text.encode("utf-8"))
    except Exception:
        if backup.exists():
            shutil.copy2(backup, asar)
        raise

    if not changed:
        print("Codex 主菜单逻辑补丁无需写入。")
        return 0, None, None

    print(f"已备份 app.asar：{backup}")
    print(f"已补丁 Codex 主菜单逻辑：{changes} 处")
    return changes, old_hash, new_hash


def patch_webview_locale_force(app_dir: Path, dry_run: bool = False) -> tuple[int, str | None, str | None]:
    asar = app_asar(app_dir.expanduser())
    data = asar.read_bytes()
    _, _, content_base, header = parse_asar(data)
    js_rel, _, old_text = find_webview_locale_js(header, data, content_base)
    if not js_rel:
        print("未定位到 WebView 语言逻辑文件，已跳过界面中文强制补丁。")
        return 0, None, None
    new_text, changes = apply_webview_locale_force_patch(old_text)

    if dry_run:
        print(f"[dry-run] WebView 语言逻辑文件：{js_rel}")
        print(f"[dry-run] WebView 中文强制补丁还需处理 {changes} 处。")
        return changes, None, None

    if changes == 0:
        print("WebView 中文强制补丁已应用，或当前版本不需要。")
        return 0, None, None

    backup = backup_file(asar, "before-webview-locale-zh-CN")
    try:
        changed, old_hash, new_hash = patch_asar_embedded_file(asar, js_rel, new_text.encode("utf-8"))
    except Exception:
        if backup.exists():
            shutil.copy2(backup, asar)
        raise

    if not changed:
        print("WebView 中文强制补丁无需写入。")
        return 0, None, None

    print(f"已备份 app.asar：{backup}")
    print(f"已补丁 WebView 中文强制逻辑：{changes} 处")
    return changes, old_hash, new_hash


def patch_webview_ui_strings(app_dir: Path, dry_run: bool = False) -> tuple[int, list[str], list[str]]:
    asar = app_asar(app_dir.expanduser())
    data = asar.read_bytes()
    _, _, content_base, header = parse_asar(data)

    specs = [
        {
            "name": "外观-减少动画",
            "startswith": "webview/assets/general-settings-",
            "markers": [
                "settings.general.appearance.reducedMotion.label",
                "Reduce motion",
                "Reduce animations or match your system",
            ],
            "replacements": [
                ("defaultMessage:`Reduce motion`", "defaultMessage:`减少动画`"),
                ("defaultMessage:`Reduce animations or match your system`", "defaultMessage:`减少动画或跟随系统`"),
                ("defaultMessage:`System`", "defaultMessage:`系统`"),
                ("defaultMessage:`On`", "defaultMessage:`开启`"),
                ("defaultMessage:`Off`", "defaultMessage:`关闭`"),
            ],
        },
        {
            "name": "钩子空状态",
            "startswith": "webview/assets/hooks-settings-",
            "markers": [
                "settings.hooks.emptyHooks.label",
                "No hooks found",
                "Projects with configured hooks will appear here",
            ],
            "replacements": [
                ("defaultMessage:`No hooks found`", "defaultMessage:`未找到钩子`"),
                (
                    "defaultMessage:`Projects with configured hooks will appear here`",
                    "defaultMessage:`已配置钩子的项目会显示在这里`",
                ),
            ],
        },
        {
            "name": "侧边栏命令标题",
            "startswith": "webview/assets/keyboard-shortcuts-search-input-",
            "markers": [
                "codex.command.toggleSidePanel",
                "Toggle Side Panel",
                "Focus Browser Address Bar",
            ],
            "replacements": [
                ("defaultMessage:`Toggle side panel`", "defaultMessage:`切换侧边栏`"),
                ("defaultMessage:`Toggle Side Panel`", "defaultMessage:`切换侧边栏`"),
                ("defaultMessage:`Toggle Browser Panel`", "defaultMessage:`切换浏览器面板`"),
                ("defaultMessage:`Focus browser address bar`", "defaultMessage:`聚焦浏览器地址栏`"),
                ("defaultMessage:`Focus Browser Address Bar`", "defaultMessage:`聚焦浏览器地址栏`"),
            ],
        },
    ]

    total_changes = 0
    old_hashes: list[str] = []
    new_hashes: list[str] = []

    for spec in specs:
        js_rel, _, old_text = find_webview_js_by_markers(
            header,
            data,
            content_base,
            startswith=spec["startswith"],
            markers=spec["markers"],
        )
        if not js_rel:
            print(f"未定位到 {spec['name']} 文件，已跳过。")
            continue
        new_text, changes = apply_webview_ui_string_patch(old_text, spec["replacements"])

        if dry_run:
            print(f"[dry-run] {spec['name']} 文件：{js_rel}")
            print(f"[dry-run] {spec['name']} 还需处理 {changes} 处。")
            total_changes += changes
            continue

        if changes == 0:
            print(f"{spec['name']} 补丁已应用，或当前版本不需要。")
            continue

        backup = backup_file(asar, f"before-{spec['name']}-zh-CN")
        try:
            changed, old_hash, new_hash = patch_asar_embedded_file(asar, js_rel, new_text.encode("utf-8"))
        except Exception:
            if backup.exists():
                shutil.copy2(backup, asar)
            raise

        if not changed:
            print(f"{spec['name']} 补丁无需写入。")
            continue

        print(f"已备份 app.asar：{backup}")
        print(f"已补丁 {spec['name']}：{changes} 处")
        total_changes += changes
        old_hashes.append(old_hash)
        new_hashes.append(new_hash)
        data = asar.read_bytes()
        _, _, content_base, header = parse_asar(data)

    return total_changes, old_hashes, new_hashes

def count_asar_tokens(asar: Path, tokens: list[bytes]) -> dict[bytes, int]:
    data = asar.read_bytes()
    _, _, content_base, header = parse_asar(data)
    counts = {token: 0 for token in tokens}
    for _, entry in asar_file_entries(header):
        if entry.get("unpacked"):
            continue
        try:
            offset = content_base + int(entry["offset"])
            size = int(entry["size"])
        except (KeyError, TypeError, ValueError):
            continue
        chunk = data[offset : offset + size]
        for token in tokens:
            counts[token] += chunk.count(token)
    return counts


def patch_asar_file_content_and_integrity(
    asar: Path,
    old_token: bytes,
    new_token: bytes,
) -> tuple[int, int, str, str]:
    if len(old_token) != len(new_token):
        raise ValueError("ASAR 原地替换必须保持字节长度一致。")

    data = bytearray(asar.read_bytes())
    json_start, json_end, content_base, header = parse_asar(bytes(data))
    old_header_hash = sha256_hex(bytes(data[json_start:json_end]))
    header_bytes = bytearray(data[json_start:json_end])
    patched_files = 0
    patched_tokens = 0

    for _, entry in asar_file_entries(header):
        if entry.get("unpacked"):
            continue
        try:
            offset = content_base + int(entry["offset"])
            size = int(entry["size"])
        except (KeyError, TypeError, ValueError):
            continue

        chunk = bytes(data[offset : offset + size])
        token_count = chunk.count(old_token)
        if token_count == 0:
            continue

        integrity = entry.get("integrity")
        if not isinstance(integrity, dict):
            raise SystemExit("目标 ASAR 文件缺少 integrity 元数据，拒绝补丁。")
        old_hash = nonempty_string(integrity.get("hash"))
        if not old_hash:
            raise SystemExit("目标 ASAR 文件缺少 integrity hash，拒绝补丁。")
        old_blocks = integrity.get("blocks")
        if not isinstance(old_blocks, list):
            old_blocks = []
        block_size = int(integrity.get("blockSize") or 4194304)

        patched_chunk = chunk.replace(old_token, new_token)
        data[offset : offset + size] = patched_chunk
        new_hash = sha256_hex(patched_chunk)
        new_blocks = sha256_blocks(patched_chunk, block_size)
        header_bytes = header_bytes.replace(old_hash.encode("ascii"), new_hash.encode("ascii"))
        for old_block, new_block in zip(old_blocks, new_blocks, strict=False):
            if isinstance(old_block, str):
                header_bytes = header_bytes.replace(old_block.encode("ascii"), new_block.encode("ascii"))

        patched_files += 1
        patched_tokens += token_count

    if patched_files:
        if len(header_bytes) != json_end - json_start:
            raise SystemExit("拒绝写入 ASAR：integrity header 大小发生变化。")
        data[json_start:json_end] = header_bytes
        new_header_hash = sha256_hex(bytes(header_bytes))
        tmp = asar.with_suffix(asar.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, asar)
    else:
        new_header_hash = old_header_hash

    return patched_files, patched_tokens, old_header_hash, new_header_hash


def backup_header_hashes(asar: Path, reason_prefix: str) -> list[str]:
    hashes: list[str] = []
    for backup in sorted(asar.parent.glob(f"{asar.name}.bak-{reason_prefix}-*"), reverse=True):
        try:
            header_hash = asar_header_hash(backup.read_bytes())
        except Exception:
            continue
        if header_hash not in hashes:
            hashes.append(header_hash)
    return hashes


def patch_exe_asar_header_hash(app_dir: Path, expected_hash: str, old_hashes: list[str], reason: str) -> None:
    exe = app_exe(app_dir)
    if not exe:
        raise SystemExit(f"未找到 Codex.exe：{app_dir}")

    data = exe.read_bytes()
    expected_token = expected_hash.encode("ascii")
    if expected_token in data:
        print(f"Codex.exe ASAR header hash 已是最新：{exe}")
        return

    for old_hash in old_hashes:
        old_token = old_hash.encode("ascii")
        if old_token not in data:
            continue
        backup = backup_file(exe, reason)
        tmp = exe.with_suffix(exe.suffix + ".tmp")
        tmp.write_bytes(data.replace(old_token, expected_token, 1))
        os.replace(tmp, exe)
        print(f"已备份 Codex.exe：{backup}")
        print(f"已更新 Codex.exe ASAR header hash：{exe}")
        return

    raise SystemExit("无法在 Codex.exe 中找到旧 ASAR header hash。请强制重建便携版后再试。")


def patch_codex_menu_strings(app_dir: Path, dry_run: bool = False) -> int:
    asar = app_asar(app_dir.expanduser())
    if not asar.exists():
        raise SystemExit(f"未找到 app.asar：{asar}")

    replacements = codex_menu_replacements()
    counts = count_asar_tokens(asar, [source for source, _ in replacements])
    total = sum(counts.values())
    if dry_run:
        print(f"[dry-run] 将检查 Codex 菜单英文硬编码：{asar}")
        for source, _ in replacements:
            print(f"  {source.decode('utf-8', 'replace')}: {counts[source]}")
        print(f"[dry-run] 共可替换 {total} 处。")
        patch_codex_main_menu_logic(app_dir, dry_run=True)
        patch_webview_locale_force(app_dir, dry_run=True)
        patch_webview_ui_strings(app_dir, dry_run=True)
        return 0

    old_header_hashes: list[str] = []
    final_header_hash = asar_header_hash(asar.read_bytes())
    patched_total = 0
    patched_file_ops = 0

    if total == 0:
        print(f"Codex 等长菜单字符串已补丁，或当前版本未找到旧字符串：{asar}")
    else:
        backup = backup_file(asar, "before-menu-zh-CN")
        try:
            for source, target in replacements:
                patched_files, patched_tokens, old_header_hash, new_header_hash = patch_asar_file_content_and_integrity(
                    asar,
                    source,
                    target,
                )
                if patched_tokens:
                    old_header_hashes.append(old_header_hash)
                    final_header_hash = new_header_hash
                    patched_total += patched_tokens
                    patched_file_ops += patched_files
        except Exception:
            if backup.exists():
                shutil.copy2(backup, asar)
            raise

        print(f"已备份 app.asar：{backup}")
        print(f"已补丁 Codex 菜单字符串：{patched_total} 处，文件补丁操作 {patched_file_ops} 次")
        patch_exe_asar_header_hash(
            app_dir,
            final_header_hash,
            [*old_header_hashes, *backup_header_hashes(asar, "before-menu-zh-CN")],
            "before-menu-zh-CN",
        )

    logic_changes, logic_old_hash, logic_new_hash = patch_codex_main_menu_logic(app_dir, dry_run=False)
    if logic_changes and logic_old_hash and logic_new_hash:
        patch_exe_asar_header_hash(
            app_dir,
            logic_new_hash,
            [logic_old_hash, *backup_header_hashes(asar, "before-menu-logic-zh-CN")],
            "before-menu-logic-zh-CN",
        )

    webview_changes, webview_old_hash, webview_new_hash = patch_webview_locale_force(app_dir, dry_run=False)
    if webview_changes and webview_old_hash and webview_new_hash:
        patch_exe_asar_header_hash(
            app_dir,
            webview_new_hash,
            [webview_old_hash, *backup_header_hashes(asar, "before-webview-locale-zh-CN")],
            "before-webview-locale-zh-CN",
        )

    webview_ui_changes, webview_ui_old_hashes, webview_ui_new_hashes = patch_webview_ui_strings(app_dir, dry_run=False)
    if webview_ui_changes and webview_ui_old_hashes and webview_ui_new_hashes:
        patch_exe_asar_header_hash(
            app_dir,
            webview_ui_new_hashes[-1],
            [*webview_ui_old_hashes, *backup_header_hashes(asar, "before-外观-减少动画-zh-CN"), *backup_header_hashes(asar, "before-钩子空状态-zh-CN"), *backup_header_hashes(asar, "before-侧边栏命令标题-zh-CN")],
            "before-webview-ui-zh-CN",
        )

    if total == 0 and logic_changes == 0 and webview_changes == 0 and webview_ui_changes == 0:
        current_hash = asar_header_hash(asar.read_bytes())
        patch_exe_asar_header_hash(
            app_dir,
            current_hash,
            [
                *backup_header_hashes(asar, "before-menu-zh-CN"),
                *backup_header_hashes(asar, "before-menu-logic-zh-CN"),
                *backup_header_hashes(asar, "before-webview-locale-zh-CN"),
                *backup_header_hashes(asar, "before-外观-减少动画-zh-CN"),
                *backup_header_hashes(asar, "before-钩子空状态-zh-CN"),
                *backup_header_hashes(asar, "before-侧边栏命令标题-zh-CN"),
            ],
            "before-menu-zh-CN",
        )
    return 0


def show_paths(target_dir: Path) -> int:
    print("Codex zh-CN 工具路径：")
    source = find_source_app_dir()
    print(f"  官方安装目录：{source or '未找到'}")
    print(f"  便携版目录：{target_dir.expanduser()}")
    print(f"  启动器：{launcher_path()}")
    for label, path in shortcut_paths().items():
        print(f"  {label}快捷方式：{path}")
    if source:
        print(f"  官方版本：{app_version(source) or 'unknown'}")
    if target_dir.expanduser().exists():
        print(f"  便携版版本：{app_version(target_dir.expanduser()) or 'unknown'}")
    return 0


def full_clean(target_dir: Path, yes: bool) -> int:
    targets = [
        target_dir.expanduser(),
        launcher_path(),
        *shortcut_paths().values(),
    ]
    print("将删除以下 Codex zh-CN 便携版文件（不删除账号/配置数据）：")
    for path in targets:
        print(f"  {'[存在]' if path.exists() else '[缺失]'} {path}")

    if not yes:
        answer = input("输入 DELETE 继续：").strip()
        if answer != "DELETE":
            print("已取消。")
            return 0

    allowed_roots = [
        tool_root(),
        Path.home() / "Desktop",
        roaming_app_data() / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]
    removed = 0
    for path in targets:
        if not path.exists():
            continue
        if not any(is_within(path, root) for root in allowed_roots):
            raise SystemExit(f"拒绝删除允许目录之外的路径：{path}")
        if path.is_dir():
            make_writable(path)
            shutil.rmtree(path)
        else:
            path.unlink()
        print(f"已删除：{path}")
        removed += 1
    print(f"完成，删除 {removed} 项。")
    return 0


def prepare_app(args: argparse.Namespace) -> Path:
    target_dir = args.target_dir.expanduser()
    source = resolve_source(args)
    return copy_app_dir(source, target_dir, rebuild=args.rebuild)


def interactive_menu() -> int:
    actions: dict[str, tuple[str, list[str]]] = {
        "1": ("生成 / 补丁 / 启动中文便携版", ["--launch"]),
        "2": ("强制重建中文便携版", ["--rebuild", "--launch"]),
        "3": ("仅补丁现有便携版菜单", ["--patch-menu"]),
        "4": ("创建快捷方式", ["--create-shortcuts"]),
        "5": ("启动现有便携版", ["--launch-existing"]),
        "6": ("显示路径和版本", ["--show-paths"]),
        "7": ("完全清理便携版文件", ["--full-clean"]),
        "8": ("Dry-run 检查可补丁菜单字符串", ["--dry-run"]),
    }

    while True:
        print()
        print("Codex Desktop zh-CN 便携中文化工具")
        print()
        for key in ["1", "2", "3", "4", "5", "6", "7", "8"]:
            print(f"{key}. {actions[key][0]}")
        print("0. 退出")
        print()
        try:
            choice = input("请选择：").strip()
        except EOFError:
            return 0
        if choice == "0":
            return 0
        action = actions.get(choice)
        if not action:
            print("无效选择。")
            continue

        _, args = action
        print()
        code = main([*args])
        print()
        if code != 0:
            print(f"命令失败，退出码：{code}")
        try:
            input("按 Enter 返回菜单")
        except EOFError:
            return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Patch Codex Desktop for Windows zh-CN portable use.")
    parser.add_argument("--menu", action="store_true", help="打开交互菜单")
    parser.add_argument("--source", type=Path, help="官方 Codex app 目录、包根目录或 Codex.exe")
    parser.add_argument("--target-dir", type=Path, default=default_target_dir(), help="便携版 Codex 目录")
    parser.add_argument("--rebuild", action="store_true", help="强制从官方安装目录重建便携版")
    parser.add_argument("--patch-menu", action="store_true", help="只补丁现有便携版菜单")
    parser.add_argument("--create-shortcuts", action="store_true", help="创建桌面和开始菜单快捷方式")
    parser.add_argument("--launch-existing", action="store_true", help="启动现有便携版")
    parser.add_argument("--launch", action="store_true", help="补丁完成后启动便携版")
    parser.add_argument("--show-paths", action="store_true", help="显示官方和便携版路径")
    parser.add_argument("--full-clean", action="store_true", help="删除便携版、启动器和快捷方式")
    parser.add_argument("--yes", action="store_true", help="跳过清理确认")
    parser.add_argument("--dry-run", action="store_true", help="只检查官方安装目录中可补丁字符串，不写入文件")
    args = parser.parse_args(argv)

    if args.menu:
        return interactive_menu()

    target_dir = args.target_dir.expanduser()

    if args.show_paths:
        return show_paths(target_dir)
    if args.full_clean:
        return full_clean(target_dir, args.yes)
    if args.dry_run:
        return patch_codex_menu_strings(resolve_source(args), dry_run=True)
    if args.patch_menu:
        app_dir = prepare_app(args) if args.rebuild else target_dir
        patch_codex_menu_strings(app_dir, dry_run=False)
        return 0
    if args.create_shortcuts:
        return create_shortcuts(target_dir)
    if args.launch_existing:
        launch(target_dir)
        return 0

    app_dir = prepare_app(args)
    patch_codex_menu_strings(app_dir, dry_run=False)
    create_shortcuts(app_dir)
    if args.launch:
        launch(app_dir)
    print(f"完成。Codex zh-CN 便携版位于：{app_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
