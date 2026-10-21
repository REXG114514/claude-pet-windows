"""Install / uninstall Claude Pet for Windows.

  py install.py                 install (or update) and start the pet
  py install.py --startup       also start the pet at Windows login
                                (by default it starts together with Claude Code)
  py install.py --uninstall     remove hooks, shortcuts and program files
  py install.py --uninstall --purge   also delete ~/.claude-pet (stats, settings)
"""

import json
import os
import shutil
import subprocess
import sys
import time

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
INSTALL_DIR = os.path.join(os.environ["LOCALAPPDATA"], "ClaudePet")
CLAUDE_SETTINGS = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
DATA_DIR = os.path.join(os.path.expanduser("~"), ".claude-pet")
QUIT_FLAG = os.path.join(DATA_DIR, "quit.flag")
START_MENU_LINK = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu",
                               "Programs", "Claude Pet.lnk")
FILES = ["pet.py", "platforms.py", "i18n.py", "claude_pet_hook.py", "install.py", "README.md", "uninstall.bat"]
MARK = "claude_pet_hook.py"
EVENTS = ["SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse",
          "Notification", "Stop", "PreCompact"]
TOOL_EVENTS = {"PreToolUse", "PostToolUse"}

MSG = {
    "zh": {
        "store_python": "请用真正安装的 Python 运行（例如 `py install.py`），不要用 Microsoft Store 的占位 python。",
        "stopping": "● 停止正在运行的桌宠…", "copying": "● 复制程序到", "hooks": "● 写入 Claude Code hooks →",
        "start_menu": "● 创建开始菜单快捷方式", "startup": "● 设置开机自启（右键桌宠可关闭）",
        "launch": "● 启动桌宠",
        "done": "\n装好啦！以后每次打开 Claude Code，桌宠都会自动跟着启动（已经开着的会话需要重开一下）。\n"
                "右键桌宠可以调大小、开关溜达/气泡/提示音；左键拖动它，单击摸摸它，双击喂零食。",
        "u_stop": "● 停止桌宠", "u_hooks": "● 移除 Claude Code hooks", "u_links": "● 删除快捷方式",
        "u_files": "● 删除程序文件", "u_data": "● 删除数据", "u_done": "\n已卸载。",
    },
    "en": {
        "store_python": "Please run this with a real Python install (e.g. `py install.py`), "
                        "not the Microsoft Store placeholder.",
        "stopping": "● Stopping the running pet…", "copying": "● Copying files to",
        "hooks": "● Adding Claude Code hooks →", "start_menu": "● Creating Start menu shortcut",
        "startup": "● Starting with Windows (you can turn this off from the right-click menu)",
        "launch": "● Launching the pet",
        "done": "\nAll set! The pet now starts whenever Claude Code starts (restart sessions that are already open).\n"
                "Right-click it for settings; drag it around, click to pet it, double-click to feed it.",
        "u_stop": "● Stopping the pet", "u_hooks": "● Removing Claude Code hooks", "u_links": "● Removing shortcuts",
        "u_files": "● Removing program files", "u_data": "● Removing data", "u_done": "\nUninstalled.",
    },
}


def msg(key):
    try:
        sys.path.insert(0, SRC_DIR)
        import i18n
        with open(os.path.join(DATA_DIR, "config.json"), encoding="utf-8") as f:
            setting = json.load(f).get("lang", "auto")
    except Exception:
        setting = "auto"
    try:
        lang = i18n.detect(setting)
    except Exception:
        lang = "en"
    return MSG.get(lang, MSG["en"])[key]



def python_exe():
    exe = sys.executable
    if os.path.basename(exe).lower() == "pythonw.exe":
        exe = os.path.join(os.path.dirname(exe), "python.exe")
    return exe


def pythonw_exe():
    w = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return w if os.path.exists(w) else sys.executable


def stop_running_pet():
    os.makedirs(DATA_DIR, exist_ok=True)
    open(QUIT_FLAG, "w").close()
    for _ in range(15):          # the pet checks every 0.4 s
        if not os.path.exists(QUIT_FLAG):
            time.sleep(0.3)
            return True
        time.sleep(0.2)
    try:
        os.remove(QUIT_FLAG)     # nobody picked it up: pet wasn't running
    except OSError:
        pass
    return False


def load_settings():
    if not os.path.exists(CLAUDE_SETTINGS):
        return {}
    with open(CLAUDE_SETTINGS, encoding="utf-8-sig") as f:
        text = f.read().strip()
    return json.loads(text) if text else {}


def save_settings(settings):
    os.makedirs(os.path.dirname(CLAUDE_SETTINGS), exist_ok=True)
    if os.path.exists(CLAUDE_SETTINGS):
        backup = CLAUDE_SETTINGS + ".bak-claude-pet"
        if not os.path.exists(backup):
            shutil.copy2(CLAUDE_SETTINGS, backup)
    tmp = CLAUDE_SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, CLAUDE_SETTINGS)


def strip_pet_hooks(settings):
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return
    for event in list(hooks):
        groups = hooks[event] if isinstance(hooks[event], list) else []
        kept = []
        for group in groups:
            inner = [h for h in group.get("hooks", []) if MARK not in str(h.get("command", ""))]
            if inner:
                kept.append(dict(group, hooks=inner))
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        del settings["hooks"]


def add_pet_hooks(settings, command):
    hooks = settings.setdefault("hooks", {})
    for event in EVENTS:
        entry = {"hooks": [{"type": "command", "command": command, "timeout": 5}]}
        if event in TOOL_EVENTS:
            entry = {"matcher": "*", **entry}
        hooks.setdefault(event, []).append(entry)


def install(startup=False):
    if "WindowsApps" in sys.executable:
        sys.exit(msg("store_python"))
    sys.path.insert(0, SRC_DIR)
    from pet import STARTUP_LINK, make_shortcut  # noqa: E402

    print(msg("stopping"))
    stop_running_pet()

    print(msg("copying"), INSTALL_DIR)
    os.makedirs(INSTALL_DIR, exist_ok=True)
    for name in FILES:
        src = os.path.join(SRC_DIR, name)
        if os.path.exists(src) and os.path.abspath(src) != os.path.join(INSTALL_DIR, name):
            shutil.copy2(src, os.path.join(INSTALL_DIR, name))

    hook = os.path.join(INSTALL_DIR, "claude_pet_hook.py").replace("\\", "/")
    command = '"%s" "%s"' % (python_exe().replace("\\", "/"), hook)
    print(msg("hooks"), CLAUDE_SETTINGS)
    settings = load_settings()
    strip_pet_hooks(settings)
    add_pet_hooks(settings, command)
    save_settings(settings)

    pet = os.path.join(INSTALL_DIR, "pet.py")
    print(msg("start_menu"))
    make_shortcut(START_MENU_LINK, pythonw_exe(), '"%s"' % pet, INSTALL_DIR)
    if startup:
        print(msg("startup"))
        make_shortcut(STARTUP_LINK, pythonw_exe(), '"%s"' % pet, INSTALL_DIR)
    else:
        try:
            os.remove(STARTUP_LINK)
        except OSError:
            pass

    print(msg("launch"))
    subprocess.Popen([pythonw_exe(), pet], cwd=INSTALL_DIR, close_fds=True,
                     creationflags=0x00000008 | 0x00000200)  # DETACHED | NEW_PROCESS_GROUP
    print(msg("done"))


def uninstall(purge=False):
    print(msg("u_stop"))
    stop_running_pet()
    print(msg("u_hooks"))
    if os.path.exists(CLAUDE_SETTINGS):
        settings = load_settings()
        strip_pet_hooks(settings)
        save_settings(settings)
    print(msg("u_links"))
    startup = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu",
                           "Programs", "Startup", "Claude Pet.lnk")
    for link in (START_MENU_LINK, startup):
        try:
            os.remove(link)
        except OSError:
            pass
    print(msg("u_files"), INSTALL_DIR)
    shutil.rmtree(INSTALL_DIR, ignore_errors=True)
    if purge:
        print(msg("u_data"), DATA_DIR)
        shutil.rmtree(DATA_DIR, ignore_errors=True)
    print(msg("u_done"))


if __name__ == "__main__":
    if "--uninstall" in sys.argv:
        uninstall(purge="--purge" in sys.argv)
    else:
        install(startup="--startup" in sys.argv)
