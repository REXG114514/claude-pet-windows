"""Claude Code hook for Claude Pet.

Claude Code pipes one JSON event to stdin per hook call. We turn it into a
small per-session state file under ~/.claude-pet/sessions that the pet polls.
This script must be fast and must never fail or print anything: Claude Code
would surface errors to the user.
"""

import json
import os
import re
import sys
import time
from datetime import date
from urllib.parse import urlparse

DATA_DIR = os.path.join(os.path.expanduser("~"), ".claude-pet")
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
STATS_DIR = os.path.join(DATA_DIR, "stats")

MAX_DETAIL = 40

READ_TOOLS = {"Read", "NotebookRead"}
EDIT_TOOLS = {"Edit", "MultiEdit", "NotebookEdit"}
RUN_TOOLS = {"Bash", "PowerShell"}
AGENT_TOOLS = {"Task", "Agent"}
PLAN_TOOLS = {"TodoWrite", "ExitPlanMode", "EnterPlanMode"}


def short(text, limit=MAX_DETAIL):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def base(path):
    return os.path.basename(str(path or "").replace("\\", "/").rstrip("/")) or "?"


def describe_tool(name, inp):
    """Map a tool call to (pet state, action, argument).

    The pet turns action + argument into a sentence in the user's language
    (see i18n.py, keys "act_<action>").
    """
    inp = inp if isinstance(inp, dict) else {}
    if name in READ_TOOLS:
        return "reading", "read", base(inp.get("file_path") or inp.get("notebook_path"))
    if name == "Grep":
        return "reading", "grep", short(inp.get("pattern"), 24)
    if name == "Glob":
        return "reading", "glob", short(inp.get("pattern"), 26)
    if name == "LS":
        return "reading", "ls", ""
    if name in EDIT_TOOLS:
        return "editing", "edit", base(inp.get("file_path") or inp.get("notebook_path"))
    if name == "Write":
        return "editing", "write", base(inp.get("file_path"))
    if name in RUN_TOOLS:
        cmd = str(inp.get("command") or "").strip().splitlines()
        return "running", "run", short(cmd[0] if cmd else "", 30)
    if name in ("BashOutput", "KillShell", "KillBash"):
        return "running", "output", ""
    if name == "WebSearch":
        return "browsing", "websearch", short(inp.get("query"), 30)
    if name == "WebFetch":
        return "browsing", "webfetch", urlparse(str(inp.get("url") or "")).netloc or "web"
    if name in AGENT_TOOLS:
        return "delegating", "agent", short(inp.get("description") or "", 30)
    if name in PLAN_TOOLS:
        return "planning", "plan", ""
    if name == "Skill":
        return "working", "skill", short(inp.get("skill") or inp.get("command"), 30)
    if name.startswith("mcp__"):
        parts = name.split("__")
        server = parts[1] if len(parts) > 1 else "mcp"
        tool = parts[-1] if len(parts) > 2 else ""
        return "working", "mcp", short(server + (" · " + tool if tool else ""))
    return "working", "tool", short(name, 30)


def write_json_atomic(path, data):
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    # The pet may be reading the file at this instant; Windows then refuses
    # the replace, so retry briefly.
    for _ in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.02)
    try:
        os.remove(tmp)
    except OSError:
        pass


def bump_stat(char):
    os.makedirs(STATS_DIR, exist_ok=True)
    with open(os.path.join(STATS_DIR, date.today().isoformat() + ".log"), "ab") as f:
        f.write(char)


def pet_running():
    import ctypes
    k32 = ctypes.windll.kernel32
    handle = k32.OpenMutexW(0x00100000, False, "Local\\ClaudePetSingleton")  # SYNCHRONIZE
    if handle:
        k32.CloseHandle(handle)
        return True
    return False


def launch_pet():
    """Start the pet alongside Claude Code if it isn't running yet."""
    import subprocess
    if pet_running():
        return
    here = os.path.dirname(os.path.abspath(__file__))
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    # Detached, own process group, and no inherited pipes: Claude Code waits
    # for the hook's stdout to close, so the pet must not hold on to it.
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    kwargs = dict(cwd=here, close_fds=True, stdin=subprocess.DEVNULL,
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cmd = [pythonw, os.path.join(here, "pet.py")]
    try:
        # Break out of Claude Code's job object so closing one terminal
        # doesn't take the pet down with it.
        subprocess.Popen(cmd, creationflags=flags | 0x01000000, **kwargs)
    except OSError:
        subprocess.Popen(cmd, creationflags=flags, **kwargs)


def handle(ev):
    event = ev.get("hook_event_name") or ""
    sid = re.sub(r"[^A-Za-z0-9_.-]", "_", str(ev.get("session_id") or "default"))[:80]
    path = os.path.join(SESSIONS_DIR, sid + ".json")

    if event == "SessionEnd":
        try:
            os.remove(path)
        except OSError:
            pass
        return

    arg = ""
    if event == "SessionStart":
        state, action = "greet", "greet"
        try:
            launch_pet()
        except Exception:
            pass
    elif event == "UserPromptSubmit":
        state, action = "thinking", "prompt"
        bump_stat(b"p")
    elif event == "PreToolUse":
        state, action, arg = describe_tool(str(ev.get("tool_name") or ""), ev.get("tool_input"))
        bump_stat(b"t")
    elif event == "PostToolUse":
        state, action = "thinking", "think"
    elif event == "Notification":
        msg = str(ev.get("message") or "")
        kind = str(ev.get("notification_type") or "")
        if "permission" in kind or "permission" in msg.lower():
            m = re.search(r"to use (\S+)", msg)
            state, action, arg = "waiting", "permission" if m else "permission_any", m.group(1) if m else ""
        else:
            state, action = "idle", "idle_input"
    elif event == "Stop":
        state, action = "done", "done"
    elif event == "PreCompact":
        state, action = "compacting", "compact"
    else:
        return

    cwd = str(ev.get("cwd") or "")
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    write_json_atomic(path, {
        "state": state,
        "action": action,
        "arg": short(arg),
        "event": event,
        "cwd": cwd,
        "project": base(cwd) if cwd else "",
        "ts": time.time(),
    })


def main():
    try:
        raw = sys.stdin.buffer.read()
        ev = json.loads(raw.decode("utf-8", "replace") or "{}")
        if isinstance(ev, dict):
            handle(ev)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
