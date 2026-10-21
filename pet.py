"""Claude Pet for Windows.

A little pixel Claude that lives on your desktop and reacts to what Claude
Code is doing. Claude Code hooks (claude_pet_hook.py) write per-session state
files to ~/.claude-pet/sessions; this window polls them and animates.

Run:  pythonw pet.py            (normal)
      pythonw pet.py --demo     (cycle through every state, no Claude needed)
"""

import ctypes
import ctypes.wintypes as wt
import json
import math
import os
import random
import subprocess
import sys
import time
import tkinter as tk
from datetime import date, datetime, timedelta

import i18n
import platforms

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.expanduser("~"), ".claude-pet")
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
STATS_DIR = os.path.join(DATA_DIR, "stats")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
QUIT_FLAG = os.path.join(DATA_DIR, "quit.flag")
STARTUP_LINK = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                            "Start Menu", "Programs", "Startup", "Claude Pet.lnk")

TICK_MS = 50      # physics / particles; pixel-art frames advance every 2 ticks
KEY = "#fe01fe"   # transparent color key; never used in the art
COLORS = {
    "O": "#D97757",  # Claude orange
    "D": "#B4553A",  # body shade
    "E": "#1E1E1E",  # eyes
    "P": "#F2A3A3",  # blush
    "K": "#2B2B2B",  # icon outline
    "G": "#3DDC84",  # green
    "Y": "#F5C542",  # yellow
    "R": "#E5484D",  # red
    "B": "#4A90D9",  # blue
    "L": "#7FB77E",  # land green
    "W": "#8A9099",  # gray
    "H": "#F05A7E",  # heart pink
    "Z": "#7A8BA8",  # zzz
    "S": "#FFC83D",  # gold / sparkle
    "C": "#D9A35B",  # cookie
    "F": "#F4F4F4",  # white fluff
    "N": "#3B5BA9",  # nightcap blue
}

GW, GH = 20, 14   # sprite grid
HEAD = 8          # grid rows of headroom above the sprite for icons
SIZES = [("small", 4), ("medium", 5), ("large", 7), ("huge", 9)]

ACTIVE = {"thinking", "reading", "editing", "running", "browsing",
          "delegating", "planning", "working", "compacting"}
PRIORITY = {"waiting": 5, "thinking": 3, "done": 2, "greet": 2, "idle": 1}
PRIORITY.update({s: 4 for s in ACTIVE - {"thinking"}})

LEVELS = [0, 20, 60, 150, 400, 1000]   # affection needed per level (names in i18n.py)
OUTFITS = ["none", "party", "bow", "shades", "crown", "santa"]
OUTFIT_ART = {   # (grid x, grid y, rows) drawn on top of the body
    "party": (7, -2, ["..SS..", "..RB..", "..BR..", ".RBRB.", "RBRBRB"]),
    "bow": (12, 1, ["HH.HH", "HHHHH", "HH.HH"]),
    "shades": (5, 4, ["KKKKKKKKKK", ".WKK..WKK.", ".KKK..KKK."]),
    "crown": (7, 0, ["S.SS.S", "SSSSSS", "SRSSBS"]),
    "santa": (5, -1, ["...RRRR..", "..RRRRRRR", ".RRRRRR.F", "FFFFFFFFF"]),
    "nightcap": (5, -1, ["...NNNN..", "..NNNNNNN", ".NNNNNN.S", "FFFFFFFFF"]),
}
ANTICS = {"stretch": 1.6, "yawn": 1.8, "dance": 3.2, "wave": 1.6, "jump": 0.9, "sit": 4.0}
SHOW_MENU = ["dance", "stretch", "yawn", "sit", "jump", "eat", "confetti"]
REMINDERS = {12: "stretch", 18: "stretch", 23: "yawn", 1: "yawn"}   # hour -> antic

DEMO_STEPS = [   # (state, action, argument) as the hook would write them
    ("greet", "greet", ""), ("thinking", "prompt", ""), ("reading", "read", "pet.py"),
    ("editing", "edit", "App.tsx"), ("running", "run", "npm test"),
    ("browsing", "websearch", "tkinter"), ("delegating", "agent", "explore"),
    ("planning", "plan", ""), ("waiting", "permission", "Bash"), ("done", "done", ""),
    ("compacting", "compact", ""), ("@dance", "", ""), ("@eat", "", ""), ("@rub", "", ""),
    ("@dizzy", "", ""), ("@confetti", "", ""), ("@sit", "", ""), ("idle", "", ""), ("sleeping", "", ""),
]

ICONS = {
    "reading": [".WWW..", "WB..W.", "W...W.", ".WWW..", "....W.", ".....W"],
    "editing": ["....R", "...Y.", "..Y..", ".Y...", "K...."],
    "running": ["KKKKKKK", "KGKKKKK", "KKGKKKK", "KGKKGGK", "KKKKKKK"],
    "browsing": [".BBB.", "BLLBB", "BBLLB", "BLBBB", ".BBB."],
    "working": ["W.W.W", ".WWW.", "WW.WW", ".WWW.", "W.W.W"],
    "planning": ["GWWWW", ".....", "GWWWW", ".....", "GWWWW"],
    "delegating": [".OOO.", "OEOEO", ".O.O."],
    "compacting": ["Z...Z", ".Z.Z.", "..Z..", "Z...Z", ".Z.Z.", "..Z.."],
}
HEART = [".H.H.", "HHHHH", "HHHHH", ".HHH.", "..H.."]
BANG = ["RR", "RR", "RR", "..", "RR"]
ZED = ["ZZZZ", "..Z.", ".Z..", "ZZZZ"]
SPARK = [".S.", "SSS", ".S."]
COOKIE = [".CC.", "CKCC", "CCKC", ".CC."]
NOTE = [".BB", ".B.", "BB.", "BB."]

DEFAULTS = {"size": "medium", "wander": True, "bubble": True, "sound": False,
            "topmost": True, "gravity": True, "jump": True, "vision": True,
            "outfit": "none", "lang": "auto", "anchor": None,
            "pets": 0, "love": 0, "snacks": [], "greet_day": "", "reminders": {},
            "milestones": {}}


# ---------------------------------------------------------------- helpers

def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)
    except OSError:
        pass


def pythonw_path():
    w = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return w if os.path.exists(w) else sys.executable


def make_shortcut(link, target, args="", workdir=""):
    def q(s):
        return "'" + str(s).replace("'", "''") + "'"
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut(%s);"
          "$s.TargetPath=%s;$s.Arguments=%s;$s.WorkingDirectory=%s;"
          "$s.Description='Claude Pet';$s.Save()" % (q(link), q(target), q(args), q(workdir)))
    try:
        os.makedirs(os.path.dirname(link), exist_ok=True)
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       creationflags=0x08000000, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.exists(link)


def set_startup(enabled):
    if enabled:
        pet = os.path.join(APP_DIR, "pet.py")
        return make_shortcut(STARTUP_LINK, pythonw_path(), '"%s"' % pet, APP_DIR)
    try:
        os.remove(STARTUP_LINK)
    except OSError:
        pass
    return False


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", wt.DWORD)]


def work_area():
    r = RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0)
    return r.left, r.top, r.right, r.bottom


def monitor_work_area(x, y):
    """Work area (screen minus taskbar) of the monitor nearest to (x, y)."""
    try:
        u32 = ctypes.windll.user32
        u32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
        u32.MonitorFromPoint.restype = wt.HANDLE
        u32.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.POINTER(MONITORINFO)]
        mon = u32.MonitorFromPoint(wt.POINT(int(x), int(y)), 2)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if u32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            r = mi.rcWork
            return r.left, r.top, r.right, r.bottom
    except Exception:
        pass
    return work_area()


def virtual_screen():
    gm = ctypes.windll.user32.GetSystemMetrics
    x, y = gm(76), gm(77)
    return x, y, x + gm(78), y + gm(79)


def level_of(love):
    idx = 0
    for i, need in enumerate(LEVELS):
        if love >= need:
            idx = i
    return idx


def build_sprite(eyes="open", edx=0, arms=("down", "down"), legs="stand", blush=False, mouth=None):
    px = {}
    for y in range(3, 11):
        for x in range(4, 16):
            px[(x, y)] = "D" if y == 10 else "O"
    arm_shapes = {
        "down": [(2, 6), (3, 6), (2, 7), (3, 7)],
        "low": [(2, 7), (3, 7), (2, 8), (3, 8)],
        "up": [(2, 3), (2, 4), (3, 4), (3, 5)],
    }
    for side, pose in zip((0, 1), arms):
        for x, y in arm_shapes[pose]:
            px[(x if side == 0 else GW - 1 - x, y)] = "O"
    if legs != "none":
        lifted = {"walk1": (5, 12), "walk2": (7, 14)}.get(legs, ())
        for x in (5, 7, 12, 14):
            px[(x, 11)] = "O"
            if x not in lifted:
                px[(x, 12)] = "O"
    for ex in (7 + edx, 12 + edx):
        color = "H" if eyes == "heart" else "E"
        pts = {
            "open": [(ex, 5), (ex, 6)],
            "blink": [(ex, 6)],
            "happy": [(ex - 1, 6), (ex, 5), (ex + 1, 6)],
            "closed": [(ex - 1, 6), (ex, 6)],
            "wide": [(ex, 4), (ex, 5), (ex, 6)],
            "up": [(ex, 4), (ex, 5)],
            "heart": [(ex - 1, 4), (ex + 1, 4), (ex - 1, 5), (ex, 5), (ex + 1, 5), (ex, 6)],
            "x": [(ex - 1, 4), (ex + 1, 4), (ex, 5), (ex - 1, 6), (ex + 1, 6)],
        }[eyes]
        for p in pts:
            px[p] = color
    if blush:
        for p in ((5, 7), (6, 7), (13, 7), (14, 7)):
            px[p] = "P"
    if mouth == "open":
        for p in ((9, 8), (10, 8), (9, 9), (10, 9)):
            px[p] = "E"
    elif mouth == "line":
        px[(9, 8)] = px[(10, 8)] = "E"
    return px


# ---------------------------------------------------------------- the pet

class Pet:
    def __init__(self, demo=False):
        self.cfg = load_config()
        self.demo = demo
        self.root = tk.Tk()
        self.root.title("Claude Pet")
        self.root.overrideredirect(True)
        self.root.config(bg=KEY)
        self.root.attributes("-transparentcolor", KEY)
        self.root.attributes("-topmost", bool(self.cfg["topmost"]))
        self.dpi = self.root.winfo_fpixels("1i") / 96.0
        self.font = ("Microsoft YaHei UI", 9)
        self.canvas = tk.Canvas(self.root, bg=KEY, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.hwnd = None
        self.x = self.y = 0
        self.CW = self.CH = 0

        self.var_size = tk.StringVar(value=self.cfg["size"])
        self.var_outfit = tk.StringVar(value=self.cfg["outfit"])
        self.var_wander = tk.BooleanVar(value=self.cfg["wander"])
        self.var_bubble = tk.BooleanVar(value=self.cfg["bubble"])
        self.var_sound = tk.BooleanVar(value=self.cfg["sound"])
        self.var_topmost = tk.BooleanVar(value=self.cfg["topmost"])
        self.var_gravity = tk.BooleanVar(value=self.cfg["gravity"])
        self.var_jump = tk.BooleanVar(value=self.cfg["jump"])
        self.var_vision = tk.BooleanVar(value=self.cfg["vision"] and platforms.HAVE_PIL)
        self.var_startup = tk.BooleanVar(value=os.path.exists(STARTUP_LINK))
        self.var_demo = tk.BooleanVar(value=demo)

        now = time.time()
        self.ticks = self.frame = 0
        self.sessions, self._mtimes = {}, {}
        self.state, self.detail_src, self.sig = "idle", ("", "", ""), None
        self.var_lang = tk.StringVar(value=self.cfg.get("lang", "auto"))
        self.lang = i18n.detect(self.cfg.get("lang", "auto"))
        self.state_since = now
        self.busy_since = None
        self.last_interaction = now
        self.last_break = now
        self.demo_start, self.demo_step = now, -1
        self.bubble_text, self.bubble_until, self.bubble_sticky = "", 0.0, False
        self.celebrations = []
        self.hover = False
        self.pointer = (0, 0)
        self.reaction = None          # (name, start, end)
        self.antic = None             # (name, start, end)
        self.particles = []
        self.drag = None
        self.dragging = False
        self.falling, self.fall_v, self.fall_plats = False, 0.0, []
        self.platform = None          # what the feet rest on (see platforms.py)
        self.jump = None
        self.next_occlusion = self.next_validate = 0.0
        self.icons = platforms.DesktopIcons()
        self.cur_mask, self.prev_mask = [], []
        self.shake_flips, self.shake_dir, self.shake_x, self.shake_dizzy = [], 0, 0, False
        self.rub_flips, self.rub_dir, self.rub_x = [], 0, None
        self.last_rub_love = self.last_rub_line = self.last_pet_love = self.last_wave = 0.0
        self.click_job = None
        self.walk = None
        self.blink_at, self.blink_end = now + 3, 0.0
        self.look, self.look_until = 0, 0.0
        self.last_bite = -1
        self.night = False
        self.stats = (0, 0, 0)
        self.stats_loaded = False

        self.apply_size()
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Double-Button-1>", self.on_double)
        self.canvas.bind("<Motion>", self.on_hover_motion)
        self.canvas.bind("<Button-3>", self.show_menu)
        self.root.after(50, self.setup_window_styles)
        self.root.after(1200, self.check_clock)
        self.root.after(300, self.maybe_fall)
        self.refresh_stats()
        self.poll()
        self.tick()

    # ---- window plumbing

    def setup_window_styles(self):
        """Hide from the taskbar / Alt-Tab (tool window)."""
        try:
            u32 = ctypes.windll.user32
            self.hwnd = u32.GetParent(self.root.winfo_id())
            style = u32.GetWindowLongW(self.hwnd, -20)
            u32.SetWindowLongW(self.hwnd, -20, (style | 0x80) & ~0x40000)
        except Exception:
            self.hwnd = None

    def keep_on_top(self):
        if self.hwnd and self.cfg["topmost"]:
            # HWND_TOPMOST, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
            ctypes.windll.user32.SetWindowPos(self.hwnd, -1, 0, 0, 0, 0, 0x13)

    def size_scale(self):
        base = dict(SIZES).get(self.cfg["size"], 5)
        return max(2, int(round(base * self.dpi)))

    def apply_size(self):
        old_feet = self.feet() if self.CW else None
        self.S = S = self.size_scale()
        self.CW = max(int(260 * self.dpi), 28 * S)
        self.BH = int(64 * self.dpi)
        self.CH = self.BH + (HEAD + GH + 1) * S
        self.canvas.config(width=self.CW, height=self.CH)
        if old_feet:
            self.put_feet(*old_feet)
        else:
            cx, bottom = self.initial_anchor()
            self.place(cx - self.CW // 2, bottom - self.CH)

    # The pet's position is tracked by its feet: the screen row right under them.
    def feet_off(self):
        return self.BH + (HEAD + 13) * self.S

    def feet(self):
        return self.x + self.CW // 2, self.y + self.feet_off()

    def put_feet(self, fx, fy):
        self.place(fx - self.CW // 2, fy - self.feet_off())

    def ground_platform(self):
        fx, fy = self.feet()
        l, _, r, b = monitor_work_area(fx, fy - 5 * self.S)
        return {"kind": "ground", "y": b, "x0": l, "x1": r}

    def default_anchor(self):
        _, _, right, bottom = work_area()
        return right - self.CW // 2 - int(20 * self.dpi), bottom + 2 * self.S

    def initial_anchor(self):
        a = self.cfg.get("anchor")
        vx0, vy0, vx1, vy1 = virtual_screen()
        if isinstance(a, list) and len(a) == 2 and vx0 <= a[0] <= vx1 and vy0 < a[1] <= vy1 + 4 * self.S:
            return int(a[0]), int(a[1])
        return self.default_anchor()

    def place(self, x, y):
        self.x, self.y = int(x), int(y)
        self.root.geometry("%dx%d+%d+%d" % (self.CW, self.CH, self.x, self.y))

    def remember_position(self):
        self.cfg["anchor"] = [self.x + self.CW // 2, self.y + self.CH]
        save_config(self.cfg)

    def reset_position(self):
        cx, bottom = self.default_anchor()
        self.place(cx - self.CW // 2, bottom - self.CH)
        self.jump, self.falling, self.walk = None, False, None
        self.platform = self.ground_platform()
        self.remember_position()

    # ---- data

    def poll(self):
        try:
            if os.path.exists(QUIT_FLAG):
                os.remove(QUIT_FLAG)
                self.quit()
                return
            if not self.demo:
                self.read_sessions()
        except Exception:
            pass
        self.root.after(400, self.poll)

    def read_sessions(self):
        now = time.time()
        seen = set()
        try:
            entries = list(os.scandir(SESSIONS_DIR))
        except OSError:
            entries = []
        for e in entries:
            if not e.name.endswith(".json"):
                continue
            try:
                mt = e.stat().st_mtime
            except OSError:
                continue
            if now - mt > 24 * 3600:
                try:
                    os.remove(e.path)
                except OSError:
                    pass
                continue
            seen.add(e.name)
            if self._mtimes.get(e.name) == mt:
                continue
            try:
                with open(e.path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            self._mtimes[e.name] = mt
            self.sessions[e.name] = data
        for name in list(self.sessions):
            if name not in seen:
                del self.sessions[name]
                self._mtimes.pop(name, None)

    def refresh_stats(self):
        try:
            today = date.today()
            p = t = 0
            path = os.path.join(STATS_DIR, today.isoformat() + ".log")
            if os.path.exists(path):
                with open(path, "rb") as f:
                    data = f.read()
                p, t = data.count(b"p"), data.count(b"t")
            d = today if p or t else today - timedelta(days=1)
            streak = 0
            while os.path.exists(os.path.join(STATS_DIR, d.isoformat() + ".log")):
                streak += 1
                d -= timedelta(days=1)
            self.stats = (p, t, streak)
            self.check_milestones(p, streak)
        except Exception:
            pass
        self.root.after(5000, self.refresh_stats)

    def check_milestones(self, prompts, streak):
        today = date.today().isoformat()
        ms = self.cfg.setdefault("milestones", {})
        if ms.get("day") != today:
            ms.clear()
            ms.update(day=today, hit=[])
        newest = None
        for n in (10, 30, 50, 100, 200, 300, 500):
            if prompts >= n and n not in ms["hit"]:
                ms["hit"].append(n)
                newest = n
        if streak in (3, 7, 14, 30, 50, 100, 200, 365) and ms.get("streak") != streak:
            ms["streak"] = streak
            self.celebrations.append(self.t("streak", streak))
        if newest:
            self.celebrations.append(self.t("milestone", newest))
        if newest or ms.get("streak") == streak:
            save_config(self.cfg)

    @staticmethod
    def effective(s, now):
        st = s.get("state", "idle")
        age = now - float(s.get("ts", 0) or 0)
        if age > 6 * 3600:
            return None
        if st in ACTIVE and age > 300:     # interrupted turns never send Stop
            return "idle"
        if st == "waiting" and age > 1800:
            return "idle"
        if st in ("done", "greet") and age > 5:
            return "idle"
        return st if st in PRIORITY else "idle"

    def live_sessions(self, now):
        live = []
        for s in self.sessions.values():
            st = self.effective(s, now)
            if st is not None:
                live.append((s, st))
        live.sort(key=lambda item: (PRIORITY.get(item[1], 1), item[0].get("ts", 0)), reverse=True)
        return live

    def compute_state(self, now):
        """(state, (action, arg, project), ts) of the session the pet should show."""
        if self.demo:
            i = int((now - self.demo_start) / 3.5) % len(DEMO_STEPS)
            st, action, arg = DEMO_STEPS[i]
            if i != self.demo_step:
                self.demo_step = i
                if st.startswith("@"):
                    self.perform(st[1:])
            if st.startswith("@"):
                return "idle", ("", "", ""), i
            return st, (action, arg, ""), i
        live = self.live_sessions(now)
        if not live:
            st, src, ts = "idle", ("", "", ""), 0
        else:
            s, st = live[0]
            ts = s.get("ts", 0)
            proj = s.get("project", "") if len(live) > 1 else ""
            src = (s.get("action", "") if st == s.get("state") else "", s.get("arg", ""), proj)
        last = max([float(s.get("ts", 0) or 0) for s, _ in live] + [self.last_interaction])
        if st == "idle" and now - last > 180:
            st = "sleeping"
        return st, src, ts

    # ---- language

    def t(self, key, *args):
        """Text for `key` in the current language (falls back to English)."""
        v = i18n.TEXT[self.lang].get(key, i18n.TEXT["en"].get(key, key))
        return v % args if args else v

    def act_text(self, action, arg):
        tpl = i18n.TEXT[self.lang].get("act_" + action) if action else None
        if not tpl:
            return None
        return tpl % (arg or "…") if "%s" in tpl else tpl

    def describe(self, st, src):
        action, arg, proj = src
        text = self.act_text(action, arg) or self.t("state_" + st)
        return "[%s] %s" % (proj, text) if proj else text

    @property
    def detail(self):
        return self.describe(self.state, self.detail_src)

    def refresh_language(self):
        lang = i18n.detect(self.cfg.get("lang", "auto"))
        if lang != self.lang:
            self.lang = lang
            self.bubble_until = 0

    def update_state(self, now):
        st, src, ts = self.compute_state(now)
        sig = (st, src, ts)
        if sig == self.sig:
            return
        self.sig = sig
        prev = self.state
        if st != prev:
            self.state_since = now
            if st == "waiting" and self.cfg["sound"]:
                try:
                    import winsound
                    winsound.MessageBeep(0x40)
                except Exception:
                    pass
        self.state, self.detail_src = st, src
        if st != "idle":
            self.antic = None
        if st in ACTIVE or st == "waiting":
            if self.busy_since is None:
                self.busy_since = now
        busy = now - self.busy_since if self.busy_since else 0
        if st in ("done", "idle", "sleeping", "greet"):
            self.busy_since = None

        if st == "done" and busy > 120:
            self.celebrate(self.t("busy_done", busy // 60))
        elif st not in ("idle", "sleeping") and (self.cfg["bubble"] or st in ("done", "greet")):
            sticky = st in ("done", "greet")
            self.say(self.detail, 4.0 if sticky else 3.5, sticky)
        elif prev == "sleeping" and st == "idle" and now - self.last_interaction < 1:
            self.say(self.t("woke"), 2.0, True)
        elif st in ("idle", "sleeping") and self.bubble_until > now and not self.bubble_sticky:
            self.bubble_until = 0

    def say(self, text, seconds, sticky=False):
        """Show a bubble; sticky ones survive the pet going back to idle."""
        self.bubble_text, self.bubble_until = text, time.time() + seconds
        self.bubble_sticky = sticky

    # ---- affection, celebrations, clock

    def add_love(self, n):
        before = level_of(self.cfg.get("love", 0))
        self.cfg["love"] = int(self.cfg.get("love", 0)) + n
        after = level_of(self.cfg["love"])
        if after > before:
            self.celebrations.append(self.t("level_up", self.t("levels")[after]))
        save_config(self.cfg)

    def celebrate(self, text):
        now = time.time()
        d = self.dpi
        for _ in range(45):
            self.emit(random.uniform(0, self.CW), random.uniform(-10, self.BH * 0.6),
                      vx=random.uniform(-1, 1) * d, vy=random.uniform(0.5, 2.5) * d, g=0.12 * d,
                      life=random.uniform(1.8, 3.0), color=random.choice("RBGSHY"),
                      size=max(2, int(self.S * 0.7)))
        self.reaction = ("cheer", now, now + 2.5)
        self.say(text, 4.0, True)

    def check_clock(self):
        try:
            self.refresh_language()     # follows Claude / Windows if they change language
            now_dt = datetime.now()
            today, h = now_dt.date().isoformat(), now_dt.hour
            self.night = h >= 23 or h < 5
            if self.cfg.get("greet_day") != today:
                self.cfg["greet_day"] = today
                self.add_love(5)
                if (now_dt.month, now_dt.day) == (1, 1):
                    self.celebrate(self.t("new_year"))
                else:
                    greet = ("greet_night" if self.night else "greet_morning" if h < 11 else
                             "greet_noon" if h < 14 else "greet_afternoon" if h < 18 else "greet_evening")
                    self.say(self.t(greet), 5.0, True)
                    self.start_antic("wave")
            rem = self.cfg.setdefault("reminders", {})
            if rem.get("day") != today:
                rem.clear()
                rem.update(day=today, done=[])
            idle = self.state in ("idle", "sleeping") and time.time() > self.bubble_until
            for hour, antic in REMINDERS.items():
                if h == hour and hour not in rem["done"] and idle:
                    rem["done"].append(hour)
                    save_config(self.cfg)
                    self.say(self.t("reminders")[hour], 6.0, True)
                    self.start_antic(antic)
                    break
            now = time.time()
            recently_active = any(now - float(s.get("ts", 0) or 0) < 300 for s in self.sessions.values())
            if not recently_active:
                self.last_break = max(self.last_break, now - 1800)
            elif now - self.last_break > 3600 and idle:
                self.last_break = now
                self.say(self.t("break"), 6.0, True)
                self.start_antic("stretch")
        except Exception:
            pass
        self.root.after(20000, self.check_clock)

    def outfit(self):
        chosen = self.cfg.get("outfit", "none")
        if self.demo and chosen == "none":
            keys = OUTFITS[1:]
            return keys[max(self.demo_step, 0) % len(keys)]
        if chosen != "none":
            return chosen
        today = date.today()
        if today.month == 12 and 20 <= today.day <= 26:
            return "santa"
        if self.night:
            return "nightcap"
        return None

    # ---- actions

    def start_antic(self, name):
        now = time.time()
        self.antic = (name, now, now + ANTICS[name])
        self.walk = None

    def perform(self, name):
        now = time.time()
        if name in ANTICS:
            self.start_antic(name)
        elif name == "eat":
            self.feed(force=True)
        elif name == "rub":
            self.reaction = ("rubbed", now, now + 1.8)
            for _ in range(4):
                self.emit_heart()
            self.say(random.choice(self.t("rub_lines")), 2.0)
        elif name == "dizzy":
            self.reaction = ("dizzy", now, now + 2.6)
            self.say(self.t("dizzy"), 2.5)
        elif name == "confetti":
            self.celebrate(self.t("confetti"))

    def feed(self, force=False):
        now = time.time()
        snacks = [t for t in self.cfg.get("snacks", []) if now - t < 3600]
        if len(snacks) >= 5 and not force:
            self.reaction = ("petted", now, now + 1.5)
            self.say(self.t("full"), 2.5)
            return
        snacks.append(now)
        self.cfg["snacks"] = snacks
        self.reaction = ("eating", now, now + 2.3)
        self.last_bite = -1
        self.walk = self.antic = None
        self.say(self.t("nom"), 1.2)
        self.add_love(3)

    def emit(self, x, y, vx=0.0, vy=0.0, g=0.0, life=1.0, color="W", size=None, rows=None, scale=None):
        self.particles.append({"x": x, "y": y, "vx": vx, "vy": vy, "g": g, "end": time.time() + life,
                               "color": color, "size": size or self.S, "rows": rows,
                               "scale": scale or self.S})

    def emit_heart(self):
        ox, oy = self.sprite_box()
        d = self.dpi
        self.emit(ox + random.uniform(5, 13) * self.S, oy + 2 * self.S,
                  vx=random.uniform(-0.6, 0.6) * d, vy=random.uniform(-2.2, -1.2) * d,
                  life=random.uniform(0.9, 1.4), rows=HEART, scale=max(1, self.S // 2))

    # ---- loop

    def tick(self):
        now = time.time()
        self.ticks += 1
        self.frame = self.ticks // 2
        try:
            self.update_state(now)
            self.update_hover(now)
            self.update_jump(now)
            self.update_fall()
            self.update_platform(now)
            self.update_autonomy(now)
            self.update_particles(now)
            if self.celebrations and now > self.bubble_until and self.state != "waiting" \
                    and not self.dragging:
                self.celebrate(self.celebrations.pop(0))
            if self.ticks % 60 == 0:
                self.keep_on_top()
            self.render(now)
        except Exception:
            pass
        self.root.after(TICK_MS, self.tick)

    def sprite_box(self):
        ox = (self.CW - GW * self.S) // 2
        oy = self.BH + HEAD * self.S
        return ox, oy

    def update_hover(self, now):
        px, py = self.root.winfo_pointerxy()
        self.pointer = (px, py)
        ox, oy = self.sprite_box()
        x0, y0 = self.x + ox + 2 * self.S, self.y + oy + 2 * self.S
        hover = x0 <= px <= x0 + 16 * self.S and y0 <= py <= y0 + 11 * self.S
        if hover and not self.hover:
            self.last_interaction = now
            if self.state == "idle" and not self.reaction_active(now) and now - self.last_wave > 30:
                self.last_wave = now
                self.start_antic("wave")
        if not hover:
            self.rub_flips, self.rub_dir, self.rub_x = [], 0, None
        self.hover = hover

    def on_hover_motion(self, e):
        """Rubbing: quick back-and-forth mouse moves over the pet."""
        if self.drag:
            return
        now = time.time()
        if self.rub_x is not None:
            dx = e.x_root - self.rub_x
            if abs(dx) < 3 * self.dpi:
                return
            sgn = 1 if dx > 0 else -1
            if self.rub_dir and sgn != self.rub_dir:
                self.rub_flips.append(now)
            self.rub_dir = sgn
        self.rub_x = e.x_root
        self.rub_flips = [t for t in self.rub_flips if now - t < 1.5]
        if len(self.rub_flips) >= 3:
            self.rub_flips = []
            self.last_interaction = now
            self.reaction = ("rubbed", now, now + 1.6)
            self.antic = self.walk = None
            self.emit_heart()
            if now - self.last_rub_line > 3:
                self.last_rub_line = now
                self.say(random.choice(self.t("rub_lines")), 1.8)
            if now - self.last_rub_love > 3:
                self.last_rub_love = now
                self.add_love(2)

    def reaction_active(self, now):
        return self.reaction is not None and now < self.reaction[2]

    def maybe_fall(self):
        """Settle onto whatever is under the pet (or the taskbar)."""
        if self.cfg["gravity"] and not self.dragging and not self.jump:
            self.start_fall(min_dy=0)

    # ---- platforms: standing, falling, jumping

    def mask_rects(self):
        """Screen rects covered by the pet's own pixels; edge detection ignores them."""
        return self.prev_mask + self.cur_mask

    @staticmethod
    def same_platform(a, b):
        return bool(a and b and abs(a["y"] - b["y"]) <= 3 and a["x0"] < b["x1"] and b["x0"] < a["x1"])

    def platforms_near(self, box, vision=True):
        S = self.S
        vx0, vy0, vx1, vy1 = virtual_screen()
        ground = self.ground_platform()
        plats = [ground]
        if not self.cfg["jump"]:
            return plats
        room = vy0 + 14 * S          # keep the whole pet on screen
        wins = platforms.window_list(self.hwnd)
        plats += platforms.window_platforms(wins, room, 8 * S)
        plats += platforms.icon_platforms(self.icons.rects(time.time()), wins, room)
        if vision and self.cfg["vision"] and platforms.HAVE_PIL:
            l, t, r, b = box
            box = (max(l, vx0), max(t, vy0), min(r, vx1), min(b, ground["y"] - 1, vy1))
            known = list(plats)
            for e in platforms.find_edges(box, self.mask_rects(), min_run=8 * S):
                if e["y"] < room or e["y"] >= ground["y"] - 2:
                    continue
                if any(self.same_platform(p, e) for p in known):
                    continue
                plats.append(e)
        return plats

    def start_fall(self, min_dy=1):
        fx, fy = self.feet()
        S = self.S
        g = self.ground_platform()
        box = (fx - 14 * S, fy - 2, fx + 14 * S, g["y"])
        self.fall_plats = [p for p in self.platforms_near(box) if p["y"] >= fy + min_dy]
        self.falling, self.fall_v = True, 0.0
        self.platform = self.jump = self.walk = None

    def update_fall(self):
        if not self.falling:
            return
        fx, fy = self.feet()
        self.fall_v += 1.5 * self.dpi
        ny = fy + self.fall_v
        m = 2 * self.S
        land = None
        for p in self.fall_plats + [self.ground_platform()]:
            ground = p["kind"] == "ground"
            if not ground and not p["x0"] + m <= fx <= p["x1"] - m:
                continue
            if p["y"] <= ny and (ground or p["y"] >= fy) and (land is None or p["y"] < land["y"]):
                land = p
        if land is None:
            self.put_feet(fx, ny)
            return
        self.falling = False
        self.land(land, self.fall_v)

    def land(self, p, v=0.0):
        p = dict(p)
        fx, _ = self.feet()
        now = time.time()
        if p["kind"] == "window":
            b = platforms.window_bounds(p["hwnd"])
            if b is None:
                self.put_feet(fx, p["y"])
                self.start_fall()
                return
            dx = b[0] - p["origin"][0]
            p.update(x0=p["x0"] + dx, x1=p["x1"] + dx, y=b[1], origin=(b[0], b[1]))
            fx += dx
        elif p["kind"] == "edge":
            # Remember which window the boundary belongs to, to ride along with it.
            h, b = platforms.owner_at(platforms.window_list(self.hwnd), fx, p["y"])
            if h:
                p.update(hwnd=h, origin=(b[0], b[1]))
        self.platform = p
        self.put_feet(fx, p["y"])
        self.next_occlusion, self.next_validate = now + 0.3, now + 1.0
        self.remember_position()
        if v > 10 * self.dpi:
            if not self.reaction_active(now) or self.reaction[0] != "dizzy":
                self.reaction = ("landed", now, now + (0.45 if v > 30 * self.dpi else 0.3))
            ox, oy = self.sprite_box()
            for side in (-1, 1):
                for _ in range(3):
                    self.emit(ox + (10 + side * 6) * self.S, oy + 12 * self.S,
                              vx=side * random.uniform(0.8, 2.0) * self.dpi, vy=-random.uniform(0.3, 1.0) * self.dpi,
                              g=0.08 * self.dpi, life=0.5, color="W", size=max(2, self.S // 2))
            if v > 30 * self.dpi and self.reaction[0] == "landed":
                self.say(self.t("ouch"), 1.5)

    def start_jump(self, p, tx):
        fx, fy = self.feet()
        d = self.dpi
        ty = p["y"]
        apex = min(fy, ty) - (35 + 0.12 * abs(tx - fx)) * d
        dist = math.hypot(tx - fx, ty - fy)
        self.jump = {"x0": fx, "y0": fy, "x1": tx, "y1": ty, "yc": 2 * apex - (fy + ty) / 2,
                     "t0": time.time() + 0.2, "dur": min(1.1, 0.45 + dist / (1500 * d)),
                     "plat": p, "dir": 1 if tx >= fx else -1}
        self.platform = self.walk = self.antic = None

    def update_jump(self, now):
        j = self.jump
        if not j:
            return
        t = (now - j["t0"]) / j["dur"]
        if t < 0:
            return        # crouching before take-off
        if t >= 1:
            self.jump = None
            self.put_feet(j["x1"], j["y1"])
            self.land(j["plat"], 14 * self.dpi)
            return
        u = 1 - t
        self.put_feet(j["x0"] + (j["x1"] - j["x0"]) * t,
                      u * u * j["y0"] + 2 * u * t * j["yc"] + t * t * j["y1"])

    def plan_jump(self):
        """Pick something nearby to hop onto: a window, an icon, a visible edge, the taskbar."""
        fx, fy = self.feet()
        d, S = self.dpi, self.S
        reach, up, down = 450 * d, 320 * d, 650 * d
        g = self.ground_platform()
        plats = self.platforms_near((fx - reach, fy - up - 4, fx + reach, min(fy + down, g["y"])))
        by_kind = {}
        for p in plats:
            if self.same_platform(p, self.platform):
                continue
            m = (8 if p["kind"] == "ground" else 3) * S
            lo, hi = max(p["x0"] + m, fx - reach), min(p["x1"] - m, fx + reach)
            dy = fy - p["y"]
            if hi < lo or dy > up or -dy > down:
                continue
            tx = random.uniform(lo, hi)
            if abs(tx - fx) < 30 * d and abs(dy) < 8 * d:
                continue
            by_kind.setdefault(p["kind"], []).append((p, tx))
        if not by_kind:
            return False
        weights = {"window": 4, "icon": 3, "edge": 3, "ground": 1}
        kinds = list(by_kind)
        kind = random.choices(kinds, [weights[k] for k in kinds])[0]
        self.start_jump(*random.choice(by_kind[kind]))
        return True

    def update_platform(self, now):
        """Keep the pet on its platform: ride moving windows, fall when it disappears."""
        p = self.platform
        if p is None or not self.cfg["gravity"] or self.dragging or self.falling or self.jump:
            return
        fx, fy = self.feet()
        S, d = self.S, self.dpi
        if p["kind"] == "ground":
            g = self.ground_platform()
            if g["y"] > fy + 1:
                self.start_fall()
                return
            if g["y"] < fy:
                self.put_feet(fx, g["y"])
            self.platform = g
            return
        if p.get("hwnd"):
            b = platforms.window_bounds(p["hwnd"])
            if b is None:
                self.start_fall()
                return
            dx, dy = b[0] - p["origin"][0], b[1] - p["origin"][1]
            if dx or dy:
                p.update(origin=(b[0], b[1]), y=p["y"] + dy, x0=p["x0"] + dx, x1=p["x1"] + dx)
                fx += dx
                self.put_feet(fx, p["y"])
            if p["kind"] == "window":
                p["x0"], p["x1"] = max(p["x0"], b[0]), min(p["x1"], b[2])
            if not p["x0"] <= fx <= p["x1"] or not b[1] <= p["y"] < b[3] \
                    or p["y"] - 14 * S < virtual_screen()[1]:
                self.start_fall()
                return
        if now >= self.next_occlusion:
            self.next_occlusion = now + 0.5
            for h, cls, (l, t, r, b) in platforms.window_list(self.hwnd):
                if h == p.get("hwnd"):
                    break
                if cls in platforms.DESKTOP_CLASSES or not (l <= fx < r and t <= p["y"] - 1 < b):
                    continue
                # Something covered our spot: hop on top of it if we can, else drop.
                if self.cfg["jump"] and cls not in platforms.NO_PLATFORM and 0 < fy - t <= 400 * d \
                        and t - 14 * S >= virtual_screen()[1] and r - l >= 8 * S:
                    self.start_jump({"kind": "window", "y": t, "x0": l, "x1": r, "hwnd": h, "origin": (l, t)},
                                    min(max(fx, l + 3 * S), r - 3 * S))
                    self.say(random.choice(self.t("hop_lines")), 1.5)
                else:
                    self.start_fall()
                return
        if p["kind"] in ("edge", "icon") and now >= self.next_validate:
            self.next_validate = now + (1.2 if p["kind"] == "edge" else 3.0)
            if p["kind"] == "edge":
                es = platforms.find_edges((fx - 10 * S, p["y"] - 8, fx + 10 * S, p["y"] + 8),
                                          self.mask_rects(), min_run=2 * S)
                ok = any(abs(e["y"] - p["y"]) <= 3 for e in es)
            else:
                ok = any(abs(t - p["y"]) <= 2 and l <= fx <= r for l, t, r, _ in self.icons.rects(now))
            if not ok:
                self.start_fall()

    def update_autonomy(self, now):
        antic_on = self.antic and now < self.antic[2]
        free = (self.state == "idle" and not (self.dragging or self.falling or self.jump or self.hover)
                and not self.reaction_active(now) and not antic_on)
        if not free or not self.cfg["wander"]:
            if self.walk:
                self.walk = None
                self.remember_position()
            if free:
                self.maybe_start_antic()
            return
        if self.walk is None:
            r = random.random()
            if r < 0.006:
                speed = max(1, int(round(1.5 * self.dpi)))
                self.walk = [random.choice((-speed, speed)), random.randint(15, 45)]
            elif r < 0.013 and self.cfg["gravity"] and self.cfg["jump"] and self.platform:
                self.plan_jump()
            else:
                self.maybe_start_antic()
            return
        if self.ticks % 2:
            return
        fx, fy = self.feet()
        nx = fx + self.walk[0]
        p = self.platform
        if self.cfg["gravity"] and p:
            m = (8 if p["kind"] == "ground" else 3) * self.S
            if not p["x0"] + m <= nx <= p["x1"] - m:
                if p["kind"] != "ground" and random.random() < 0.5:
                    self.put_feet(nx + self.walk[0] * self.S, fy)   # step off the end
                    self.start_fall()
                else:
                    self.walk[0] = -self.walk[0]
                return
        else:
            vx0, _, vx1, _ = virtual_screen()
            if nx - 8 * self.S < vx0 or nx + 8 * self.S > vx1:
                self.walk[0] = -self.walk[0]
                return
        self.put_feet(nx, fy)
        self.walk[1] -= 1
        if self.walk[1] <= 0:
            self.walk = None
            self.remember_position()

    def maybe_start_antic(self):
        if random.random() < 1 / 500:
            names = ["stretch", "yawn", "dance", "jump", "sit", "sit"]
            if self.night:
                names += ["yawn", "yawn"]
            self.start_antic(random.choice(names))

    def update_particles(self, now):
        alive = []
        for p in self.particles:
            if now >= p["end"]:
                continue
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += p["g"]
            if p["y"] < self.CH:
                alive.append(p)
        self.particles = alive[-250:]

    # ---- drawing

    def pose(self, now):
        f = self.frame
        p = {"eyes": "open", "edx": 0, "arms": ("down", "down"), "legs": "stand",
             "dy": 0, "blush": False, "mouth": None}
        if now >= self.blink_at:
            self.blink_end = now + 0.15
            self.blink_at = now + random.uniform(2.5, 6)
        blinking = now < self.blink_end

        if self.dragging or self.falling:
            name = "dragged"
        elif self.jump:
            name = "jumping"
        elif self.reaction_active(now):
            name = self.reaction[0]
        elif self.antic and now < self.antic[2] and self.state != "waiting":
            name = "antic"
        else:
            name = self.state
        el = now - (self.reaction[1] if name in ("petted", "rubbed", "eating", "dizzy", "landed", "cheer")
                    else self.antic[1] if name == "antic" else self.state_since)

        if name == "dragged":
            p["eyes"] = "x" if self.shake_dizzy else "wide"
            p["arms"], p["mouth"] = ("up", "up"), "open"
            p["legs"] = "walk1" if (f // 2) % 2 else "walk2"
            blinking = False
        elif name == "jumping":
            if now < self.jump["t0"]:
                p["dy"], p["arms"], p["eyes"] = 1, ("low", "low"), "closed"   # crouch
            else:
                p["arms"], p["eyes"], p["legs"] = ("up", "up"), "happy", "walk1"
            p["edx"] = self.jump["dir"]
            blinking = False
        elif name == "petted":
            p["eyes"], p["blush"] = "happy", True
            p["dy"] = -1 if (f // 3) % 2 else 0
            blinking = False
        elif name == "rubbed":
            p["eyes"], p["blush"] = "heart", True
            p["dy"] = (f // 2) % 2
            blinking = False
        elif name == "eating":
            p["eyes"], p["blush"] = "happy", el > 1.6
            p["mouth"] = "open" if el < 0.4 or int((el - 0.4) / 0.225) % 2 == 0 else "line"
            blinking = False
        elif name == "dizzy":
            p["eyes"], p["edx"] = "x", (-1, 0, 1, 0)[(f // 2) % 4]
            blinking = False
        elif name == "landed":
            p["eyes"], p["arms"], p["dy"] = "closed", ("low", "low"), 1
            blinking = False
        elif name == "cheer":
            p["eyes"], p["arms"] = "happy", ("up", "up")
            p["dy"] = (0, -1, -2, -1)[(f // 2) % 4]
            blinking = False
        elif name == "antic":
            a = self.antic[0]
            if a == "stretch":
                p["arms"], p["eyes"], p["dy"] = ("up", "up"), "closed", -1 if el < 1.0 else 0
                blinking = False
            elif a == "yawn":
                p["eyes"] = "closed"
                p["mouth"] = "open" if 0.3 < el < 1.4 else None
                blinking = False
            elif a == "dance":
                flip = (f // 3) % 2
                p["arms"] = ("up", "down") if flip else ("down", "up")
                p["dy"], p["eyes"] = -flip, "happy"
                p["legs"] = "walk1" if flip else "walk2"
                if self.ticks % 12 == 0:
                    ox, oy = self.sprite_box()
                    rows = NOTE if random.random() < 0.5 else [r.replace("B", "H") for r in NOTE]
                    self.emit(ox + random.choice((1, 16)) * self.S, oy + 1 * self.S,
                              vx=random.uniform(-0.5, 0.5) * self.dpi, vy=-1.2 * self.dpi,
                              life=1.2, rows=rows, scale=max(1, self.S * 2 // 3))
            elif a == "wave":
                p["eyes"] = "happy"
                p["arms"] = ("down", "up" if (f // 2) % 2 else "down")
                if self.pointer[0] < self.x + self.CW // 2:
                    p["arms"] = p["arms"][::-1]
                blinking = False
            elif a == "jump":
                p["dy"] = (1, -1, -3, -3, -2, 0)[min(5, int(el / 0.15))]
                p["arms"] = ("up", "up") if p["dy"] < 0 else ("down", "down")
            elif a == "sit":
                p["legs"], p["dy"] = "none", 2
                p["edx"] = self.track_pointer()[0]
        elif name == "idle":
            if self.walk:
                p["edx"] = 1 if self.walk[0] > 0 else -1
                p["legs"] = "walk1" if (f // 2) % 2 else "walk2"
            elif now < self.look_until:
                p["edx"] = self.look
            else:
                edx, up = self.track_pointer()
                p["edx"] = edx
                if up:
                    p["eyes"] = "up"
                if edx == 0 and not up and random.random() < 0.003:
                    self.look, self.look_until = random.choice((-1, 1)), now + 1.5
        elif name == "sleeping":
            p["eyes"] = "closed"
            p["dy"] = 1 if (f // 12) % 2 else 0
            blinking = False
        elif name == "thinking":
            p["eyes"], p["edx"] = "up", 1
            p["dy"] = -1 if (f // 8) % 2 else 0
        elif name in ("editing", "running", "working"):
            p["arms"] = ("low", "down") if (f // 2) % 2 else ("down", "low")
            p["dy"] = -1 if f % 6 == 0 else 0
        elif name in ("reading", "browsing", "planning"):
            p["edx"] = (-1, 0, 1, 0)[(f // 5) % 4]
        elif name == "delegating":
            p["arms"] = ("down", "up" if (f // 3) % 2 else "down")
            p["eyes"] = "happy"
        elif name == "compacting":
            p["dy"] = (f // 3) % 2
            p["eyes"] = "closed"
        elif name == "waiting":
            p["eyes"] = "wide"
            up = (f // 3) % 2
            p["arms"] = ("up", "up") if up else ("down", "down")
            p["dy"] = -1 if up else 0
            blinking = False
        elif name in ("done", "greet"):
            p["eyes"] = "happy"
            if name == "done":
                p["arms"] = ("up", "up")
                if el < 2.5:
                    p["dy"] = (0, -1, -2, -1)[(f // 2) % 4]
            else:
                p["arms"] = ("down", "up" if (f // 3) % 2 else "down")
            blinking = False
        if blinking and p["eyes"] in ("open", "up"):
            p["eyes"] = "blink"
        return name, el, p

    def track_pointer(self):
        """Which way the eyes should look to follow the mouse: (dx, look_up)."""
        px, py = self.pointer
        ox, oy = self.sprite_box()
        cx = self.x + ox + 10 * self.S
        cy = self.y + oy + 5 * self.S
        dx, dy = px - cx, py - cy
        if abs(dx) > 700 * self.dpi or abs(dy) > 600 * self.dpi:
            return 0, False
        edx = -1 if dx < -25 * self.dpi else 1 if dx > 25 * self.dpi else 0
        return edx, dy < -120 * self.dpi

    def rect(self, x, y, s, color):
        self.canvas.create_rectangle(x, y, x + s, y + s, fill=COLORS[color], outline="")
        self.cur_mask.append((self.x + x, self.y + y, self.x + x + s, self.y + y + s))

    def draw_rows_px(self, rows, x, y, s):
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                if ch != ".":
                    self.rect(x + i * s, y + j * s, s, ch)

    def draw_pattern(self, rows, gx, gy, ox, oy, scale=None):
        S = scale or self.S
        self.draw_rows_px(rows, ox + gx * self.S, oy + gy * self.S, S)

    def render(self, now):
        c = self.canvas
        c.delete("all")
        # The screen may still show the previous frame, so mask both.
        self.prev_mask, self.cur_mask = self.cur_mask, []
        S, f = self.S, self.frame
        name, el, p = self.pose(now)
        ox, oy = self.sprite_box()
        by = oy + p["dy"] * S
        sprite = build_sprite(p["eyes"], p["edx"], p["arms"], p["legs"], p["blush"], p["mouth"])
        for (gx, gy), ch in sprite.items():
            self.rect(ox + gx * S, by + gy * S, S, ch)

        outfit = self.outfit()
        if outfit:
            gx, gy, rows = OUTFIT_ART[outfit]
            self.draw_pattern(rows, gx, gy, ox, by)

        bob = (f // 4) % 2
        if name == "thinking":
            for k, (gx, gy, size) in enumerate(((16, 1, 1), (17, -2, 2), (19, -6, 3))):
                if (f // 4) % 4 > k:
                    self.draw_pattern(["W" * size] * size, gx, gy, ox, oy)
        elif name in ICONS:
            self.draw_pattern(ICONS[name], 16, -6 - bob, ox, oy)
        elif name == "waiting" and (f // 3) % 2 == 0:
            self.draw_pattern(BANG, 17, -6, ox, oy)
        elif name == "sleeping":
            phase = (f // 6) % 4
            for k in range(min(phase, 3)):
                self.draw_pattern(ZED, 15 + 2 * k, -1 - 3 * k, ox, oy, max(2, S * (2 + k) // 3))
        elif name in ("done", "greet", "cheer"):
            spots = ((0, -1), (18, 0), (2, -5), (17, -5), (9, -6), (11, 1))
            for k, (gx, gy) in enumerate(spots):
                if (k + f // 3) % 2:
                    self.draw_pattern(SPARK, gx, gy, ox, oy)
        elif name == "petted":
            rise = int(min(1.0, el / 2.0) * 4)
            self.draw_pattern(HEART, 8, -2 - rise, ox, oy)
        elif name == "dizzy" or (name == "dragged" and self.shake_dizzy):
            for k in range(3):
                a = now * 6 + k * 2.094
                x = ox + (8.5 + 7 * math.cos(a)) * S
                y = by + (0.5 + 1.5 * math.sin(a)) * S
                self.draw_rows_px(SPARK, x, y, max(1, S * 2 // 3))
        elif name == "eating":
            self.draw_cookie(el, ox, by)

        for part in self.particles:
            if part["rows"]:
                self.draw_rows_px(part["rows"], part["x"], part["y"], part["scale"])
            else:
                self.rect(part["x"], part["y"], part["size"], part["color"])

        text, alert = self.current_bubble(now)
        if text:
            self.draw_bubble(text, alert)

    def draw_cookie(self, el, ox, by):
        S = self.S
        if el < 0.4:
            t = el / 0.4
            self.draw_pattern(COOKIE, 20 - 9 * t, -4 + 11 * t, ox, by)
            return
        bites = int((el - 0.4) / 0.45)
        if bites != self.last_bite:
            self.last_bite = bites
            for _ in range(3):
                self.emit(ox + 10.5 * S, by + 9 * S, vx=random.uniform(-1.5, 1.5) * self.dpi,
                          vy=-random.uniform(0.5, 1.5) * self.dpi, g=0.3 * self.dpi, life=0.8,
                          color="C", size=max(2, S // 2))
        if bites < 4:
            self.draw_pattern([row[bites:] for row in COOKIE], 11 + bites, 7, ox, by)

    def current_bubble(self, now):
        if self.hover and not self.dragging and now >= self.bubble_until:
            p, t, streak = self.stats
            love = int(self.cfg.get("love", 0))
            return self.t("hover", self.detail, p, t, streak, self.t("levels")[level_of(love)], love), False
        if self.state == "waiting":
            waited = now - self.state_since
            if now < self.bubble_until and self.bubble_text != self.detail:
                return self.bubble_text, True
            if waited > 20:
                lines = [self.detail] + self.t("nag_lines")
                return lines[int(waited / 3) % len(lines)], True
            return self.detail, True
        if now < self.bubble_until:
            return self.bubble_text, False
        return "", False

    def draw_bubble(self, text, alert):
        c = self.canvas
        d = self.dpi
        pad = int(7 * d)
        cx = self.CW // 2
        bottom = self.BH + int(2 * self.S) - int(4 * d)
        t = c.create_text(cx, bottom - pad, text=text, font=self.font, fill="#222222",
                          width=self.CW - 4 * pad, anchor="s", justify="center")
        x0, y0, x1, y1 = c.bbox(t)
        bx0, bx1 = x0 - pad, x1 + pad
        by0, by1 = y0 - pad // 2, bottom
        r = int(8 * d)
        pts = [bx0 + r, by0, bx1 - r, by0, bx1, by0, bx1, by0 + r, bx1, by1 - r, bx1, by1,
               bx1 - r, by1, bx0 + r, by1, bx0, by1, bx0, by1 - r, bx0, by0 + r, bx0, by0]
        border = "#E5484D" if alert else "#3A3A3A"
        fill = "#FFF1F1" if alert else "#FFFFFF"
        w = max(1, int(round(d)))
        c.create_polygon(pts, smooth=True, fill=fill, outline=border, width=w)
        tw = int(5 * d)
        c.create_polygon(cx - tw, by1 - w, cx + tw, by1 - w, cx, by1 + tw + 1,
                         fill=fill, outline=border, width=w)
        c.create_line(cx - tw + w, by1 - w, cx + tw - w, by1 - w, fill=fill, width=w + 1)
        c.tag_raise(t)
        self.cur_mask.append((self.x + bx0, self.y + by0, self.x + bx1, self.y + by1 + tw + 1))

    # ---- interaction

    def on_press(self, e):
        self.drag = (e.x_root, e.y_root, self.x, self.y)
        self.dragging = False
        self.falling = False
        self.jump = None
        self.shake_flips, self.shake_dir, self.shake_x = [], 0, e.x_root

    def on_motion(self, e):
        if not self.drag:
            return
        sx, sy, wx, wy = self.drag
        dx, dy = e.x_root - sx, e.y_root - sy
        if not self.dragging and abs(dx) + abs(dy) < 4:
            return
        self.dragging = True
        self.walk = self.antic = self.platform = None
        self.place(wx + dx, wy + dy)
        # Shaking it hard left-right makes it dizzy.
        now = time.time()
        mdx = e.x_root - self.shake_x
        if abs(mdx) >= 8 * self.dpi:
            sgn = 1 if mdx > 0 else -1
            if self.shake_dir and sgn != self.shake_dir:
                self.shake_flips.append(now)
            self.shake_dir, self.shake_x = sgn, e.x_root
            self.shake_flips = [t for t in self.shake_flips if now - t < 1.2]
            if len(self.shake_flips) >= 4:
                self.shake_dizzy = True

    def on_release(self, e):
        if self.drag is None:
            return
        now = time.time()
        self.last_interaction = now
        self.drag = None
        if self.dragging:
            self.dragging = False
            if self.shake_dizzy:
                self.shake_dizzy = False
                self.perform("dizzy")
            if self.cfg["gravity"]:
                self.start_fall(min_dy=0)   # lands on whatever is below: window, icon, edge…
            else:
                self.remember_position()
            return
        if self.cfg["gravity"] and self.platform is None and not self.falling:
            self.start_fall(min_dy=0)       # grabbed mid-jump and let go
        if self.click_job:
            self.root.after_cancel(self.click_job)
        self.click_job = self.root.after(260, self.on_single_click)

    def on_single_click(self):
        self.click_job = None
        now = time.time()
        self.reaction = ("petted", now, now + 2.0)
        self.antic = self.walk = None
        self.cfg["pets"] = int(self.cfg.get("pets", 0)) + 1
        if now - self.last_pet_love > 2:
            self.last_pet_love = now
            self.add_love(1)
        else:
            save_config(self.cfg)
        if self.state == "waiting":
            self.say(self.t("go_check"), 2.5)
        else:
            self.say(random.choice(self.t("pet_lines")), 2.0)

    def on_double(self, e):
        if self.click_job:
            self.root.after_cancel(self.click_job)
            self.click_job = None
        self.drag = None
        self.last_interaction = time.time()
        self.feed()

    def show_menu(self, e):
        now = time.time()
        m = tk.Menu(self.root, tearoff=0)
        live = [] if self.demo else self.live_sessions(now)
        m.add_command(label=self.t("m_header", len(live)) + (self.t("m_demo") if self.demo else ""),
                      state="disabled")
        for s, st in live[:6]:
            busy = st not in ("idle", "done", "greet")
            text = self.describe(st if busy else "idle", (s.get("action", "") if busy else "", s.get("arg", ""), ""))
            m.add_command(label=self.t("m_session", s.get("project") or self.t("m_unknown"), text),
                          state="disabled")
        p, t, streak = self.stats
        love = int(self.cfg.get("love", 0))
        lv = level_of(love)
        nxt = self.t("m_next", LEVELS[lv + 1] - love) if lv + 1 < len(LEVELS) else ""
        m.add_command(label=self.t("m_stats", p, t, streak), state="disabled")
        m.add_command(label=self.t("m_love", self.t("levels")[lv], love, nxt, self.cfg.get("pets", 0)),
                      state="disabled")
        m.add_separator()
        m.add_command(label=self.t("m_feed"), command=self.feed)
        shows = tk.Menu(m, tearoff=0)
        for key in SHOW_MENU:
            shows.add_command(label=self.t("shows")[key], command=lambda k=key: self.perform(k))
        m.add_cascade(label=self.t("m_show"), menu=shows)
        outfits = tk.Menu(m, tearoff=0)
        for key in OUTFITS:
            outfits.add_radiobutton(label=self.t("outfits")[key], value=key, variable=self.var_outfit,
                                    command=self.on_outfit)
        m.add_cascade(label=self.t("m_outfit"), menu=outfits)
        sizes = tk.Menu(m, tearoff=0)
        for key, _ in SIZES:
            sizes.add_radiobutton(label=self.t("sizes")[key], value=key, variable=self.var_size, command=self.on_size)
        m.add_cascade(label=self.t("m_size"), menu=sizes)
        langs = tk.Menu(m, tearoff=0)
        langs.add_radiobutton(label=self.t("m_lang_auto"), value="auto", variable=self.var_lang, command=self.on_lang)
        for key, label in i18n.LANGS:
            langs.add_radiobutton(label=label, value=key, variable=self.var_lang, command=self.on_lang)
        m.add_cascade(label=self.t("m_lang"), menu=langs)
        m.add_separator()
        m.add_checkbutton(label=self.t("m_wander"), variable=self.var_wander, command=self.on_toggles)
        m.add_checkbutton(label=self.t("m_gravity"), variable=self.var_gravity, command=self.on_toggles)
        m.add_checkbutton(label=self.t("m_jump"), variable=self.var_jump, command=self.on_toggles)
        m.add_checkbutton(label=self.t("m_vision"), variable=self.var_vision, command=self.on_toggles,
                          state="normal" if platforms.HAVE_PIL else "disabled")
        m.add_checkbutton(label=self.t("m_bubble"), variable=self.var_bubble, command=self.on_toggles)
        m.add_checkbutton(label=self.t("m_sound"), variable=self.var_sound, command=self.on_toggles)
        m.add_checkbutton(label=self.t("m_topmost"), variable=self.var_topmost, command=self.on_toggles)
        m.add_checkbutton(label=self.t("m_startup"), variable=self.var_startup, command=self.on_startup)
        m.add_checkbutton(label=self.t("m_demo_mode"), variable=self.var_demo, command=self.on_demo)
        m.add_command(label=self.t("m_reset"), command=self.reset_position)
        m.add_separator()
        m.add_command(label=self.t("m_quit"), command=self.quit)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def on_size(self):
        self.cfg["size"] = self.var_size.get()
        self.apply_size()
        self.remember_position()

    def on_outfit(self):
        self.cfg["outfit"] = self.var_outfit.get()
        save_config(self.cfg)
        now = time.time()
        if self.cfg["outfit"] != "none":
            self.reaction = ("cheer", now, now + 1.5)
            self.say(self.t("outfit_on"), 2.0)

    def on_toggles(self):
        self.cfg["wander"] = self.var_wander.get()
        self.cfg["gravity"] = self.var_gravity.get()
        self.cfg["bubble"] = self.var_bubble.get()
        self.cfg["sound"] = self.var_sound.get()
        self.cfg["topmost"] = self.var_topmost.get()
        self.cfg["jump"] = self.var_jump.get()
        self.cfg["vision"] = self.var_vision.get()
        self.root.attributes("-topmost", self.cfg["topmost"])
        save_config(self.cfg)
        if not self.cfg["gravity"]:
            self.falling, self.platform = False, None
        elif self.platform is None and not self.falling and not self.jump:
            self.maybe_fall()

    def on_lang(self):
        self.cfg["lang"] = self.var_lang.get()
        save_config(self.cfg)
        self.refresh_language()

    def on_startup(self):
        self.var_startup.set(set_startup(self.var_startup.get()))

    def on_demo(self):
        self.demo = self.var_demo.get()
        self.demo_start, self.demo_step = time.time(), -1
        self.sig = None

    def quit(self):
        save_config(self.cfg)
        self.icons.close()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    # One pet at a time.
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\ClaudePetSingleton")
    if ctypes.windll.kernel32.GetLastError() == 183:
        return
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    try:
        os.remove(QUIT_FLAG)
    except OSError:
        pass
    Pet(demo="--demo" in sys.argv).run()
    del mutex


if __name__ == "__main__":
    main()
