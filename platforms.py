"""Things the pet can stand on.

Three sources, all returned as dicts {"kind", "y", "x0", "x1", ...} where y is
the first pixel row of the surface (the pet's feet rest right on top of it):

- window: the visible part of a top-level window's top edge
- icon:   the top of a desktop icon (read from the desktop's list view)
- edge:   any long horizontal boundary visible on screen (toolbars, panels,
          separators inside apps), found by a simple edge detector on a
          screenshot of the area around the pet. Needs Pillow.
"""

import ctypes
import ctypes.wintypes as wt
import re

try:
    from PIL import Image, ImageChops, ImageDraw
    HAVE_PIL = True
except Exception:  # Pillow is optional: windows and icons still work
    HAVE_PIL = False

# Private DLL handles so the argtypes below don't leak into other modules.
_u32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_g32 = ctypes.WinDLL("gdi32")
_dwm = ctypes.WinDLL("dwmapi")


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def _sig(fn, restype, *argtypes):
    fn.restype, fn.argtypes = restype, list(argtypes)


_sig(_u32.EnumWindows, wt.BOOL, WNDENUMPROC, wt.LPARAM)
_sig(_u32.IsWindow, wt.BOOL, wt.HWND)
_sig(_u32.IsWindowVisible, wt.BOOL, wt.HWND)
_sig(_u32.IsIconic, wt.BOOL, wt.HWND)
_sig(_u32.GetWindowLongW, ctypes.c_long, wt.HWND, ctypes.c_int)
_sig(_u32.GetClassNameW, ctypes.c_int, wt.HWND, wt.LPWSTR, ctypes.c_int)
_sig(_u32.GetWindowTextLengthW, ctypes.c_int, wt.HWND)
_sig(_u32.GetWindowRect, wt.BOOL, wt.HWND, ctypes.POINTER(RECT))
_sig(_u32.FindWindowW, wt.HWND, wt.LPCWSTR, wt.LPCWSTR)
_sig(_u32.FindWindowExW, wt.HWND, wt.HWND, wt.HWND, wt.LPCWSTR, wt.LPCWSTR)
_sig(_u32.GetWindowThreadProcessId, wt.DWORD, wt.HWND, ctypes.POINTER(wt.DWORD))
_sig(_u32.SendMessageTimeoutW, ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM,
     wt.UINT, wt.UINT, ctypes.POINTER(ctypes.c_size_t))
_sig(_u32.MapWindowPoints, ctypes.c_int, wt.HWND, wt.HWND, ctypes.POINTER(wt.POINT), wt.UINT)
_sig(_u32.GetDC, wt.HDC, wt.HWND)
_sig(_u32.ReleaseDC, ctypes.c_int, wt.HWND, wt.HDC)
_sig(_dwm.DwmGetWindowAttribute, ctypes.c_long, wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD)
_sig(_k32.OpenProcess, wt.HANDLE, wt.DWORD, wt.BOOL, wt.DWORD)
_sig(_k32.VirtualAllocEx, ctypes.c_void_p, wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, wt.DWORD)
_sig(_k32.VirtualFreeEx, wt.BOOL, wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD)
_sig(_k32.WriteProcessMemory, wt.BOOL, wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
     ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t))
_sig(_k32.ReadProcessMemory, wt.BOOL, wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
     ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t))
_sig(_k32.CloseHandle, wt.BOOL, wt.HANDLE)
_sig(_g32.CreateCompatibleDC, wt.HDC, wt.HDC)
_sig(_g32.CreateCompatibleBitmap, wt.HBITMAP, wt.HDC, ctypes.c_int, ctypes.c_int)
_sig(_g32.SelectObject, wt.HGDIOBJ, wt.HDC, wt.HGDIOBJ)
_sig(_g32.BitBlt, wt.BOOL, wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
     wt.HDC, ctypes.c_int, ctypes.c_int, wt.DWORD)
_sig(_g32.GetDIBits, ctypes.c_int, wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p,
     ctypes.c_void_p, wt.UINT)
_sig(_g32.DeleteObject, wt.BOOL, wt.HGDIOBJ)
_sig(_g32.DeleteDC, wt.BOOL, wt.HDC)

DESKTOP_CLASSES = {"Progman", "WorkerW"}
# Windows that hide what's under them but aren't fun (or stable) to stand on.
NO_PLATFORM = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "#32768", "NotifyIconOverflowWindow",
               "TopLevelWindowForOverflowXamlIsland", "Xaml_WindowedPopupClass"}

WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x20, 0x80, 0x80000, 0x08000000


# ---------------------------------------------------------------- windows

def _class_name(h):
    buf = ctypes.create_unicode_buffer(128)
    _u32.GetClassNameW(h, buf, 128)
    return buf.value


def _cloaked(h):
    v = wt.DWORD()
    return _dwm.DwmGetWindowAttribute(h, 14, ctypes.byref(v), 4) == 0 and v.value != 0


def _bounds(h):
    """Visible frame of a window (without the invisible resize border/shadow)."""
    r = RECT()
    if _dwm.DwmGetWindowAttribute(h, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        if not _u32.GetWindowRect(h, ctypes.byref(r)):
            return None
    return r.left, r.top, r.right, r.bottom


def window_bounds(h):
    """Bounds of a window if it's still shown on screen, else None."""
    if not h or not _u32.IsWindow(h) or not _u32.IsWindowVisible(h) or _u32.IsIconic(h) or _cloaked(h):
        return None
    return _bounds(h)


def window_list(exclude=None):
    """Visible top-level windows, topmost first: [(hwnd, class, (l, t, r, b))]."""
    out = []

    def cb(h, _):
        try:
            if h == exclude or not _u32.IsWindowVisible(h) or _u32.IsIconic(h) or _cloaked(h):
                return True
            ex = _u32.GetWindowLongW(h, -20)
            if ex & WS_EX_TRANSPARENT:
                return True
            if ex & WS_EX_NOACTIVATE and ex & WS_EX_LAYERED:
                return True       # invisible overlays such as the GeForce overlay
            if ex & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) and _u32.GetWindowTextLengthW(h) == 0:
                return True       # tooltips, shadows, invisible helper popups
            b = _bounds(h)
            if b and b[2] - b[0] >= 20 and b[3] - b[1] >= 20:
                out.append((h, _class_name(h), b))
        except Exception:
            pass
        return True

    _u32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def subtract(segs, l, r):
    out = []
    for a, c in segs:
        if r <= a or l >= c:
            out.append((a, c))
            continue
        if a < l:
            out.append((a, l))
        if r < c:
            out.append((r, c))
    return out


def visible_segments(y, x0, x1, occluders):
    """Parts of the row just above y (where the pet stands) not hidden by occluders."""
    segs = [(x0, x1)]
    for l, t, r, b in occluders:
        if t <= y - 1 < b:
            segs = subtract(segs, l, r)
            if not segs:
                break
    return segs


def window_platforms(wins, min_y, min_w):
    plats, above = [], []
    for h, cls, (l, t, r, b) in wins:
        if cls in DESKTOP_CLASSES:
            continue
        if cls not in NO_PLATFORM and t >= min_y:
            for a, c in visible_segments(t, l, r, above):
                if c - a >= min_w:
                    plats.append({"kind": "window", "y": t, "x0": a, "x1": c, "hwnd": h, "origin": (l, t)})
        above.append((l, t, r, b))
    return plats


def owner_at(wins, x, y):
    """Topmost non-desktop window containing (x, y)."""
    for h, cls, (l, t, r, b) in wins:
        if cls not in DESKTOP_CLASSES and l <= x < r and t <= y < b:
            return h, (l, t, r, b)
    return None, None


# ---------------------------------------------------------------- desktop icons

class DesktopIcons:
    """Reads desktop icon rectangles from Explorer's list view.

    The list view only answers with a pointer into Explorer's own memory, so
    we keep one small scratch buffer there for the RECT it fills in.
    """

    LVM_GETITEMCOUNT, LVM_GETITEMRECT, LVIR_ICON = 0x1004, 0x100E, 1

    def __init__(self):
        self.lv = self.proc = self.mem = None
        self.cache, self.cache_t = [], -1e9

    def close(self):
        if self.proc and self.mem:
            _k32.VirtualFreeEx(self.proc, self.mem, 0, 0x8000)
        if self.proc:
            _k32.CloseHandle(self.proc)
        self.lv = self.proc = self.mem = None

    @staticmethod
    def _listview():
        progman = _u32.FindWindowW("Progman", None)
        dv = _u32.FindWindowExW(progman, None, "SHELLDLL_DefView", None) if progman else None
        if not dv:
            found = []

            def cb(h, _):
                d = _u32.FindWindowExW(h, None, "SHELLDLL_DefView", None)
                if d:
                    found.append(d)
                    return False
                return True

            _u32.EnumWindows(WNDENUMPROC(cb), 0)
            dv = found[0] if found else None
        return _u32.FindWindowExW(dv, None, "SysListView32", None) if dv else None

    def rects(self, now, max_age=3.0):
        if now - self.cache_t >= max_age:
            self.cache_t = now
            try:
                self.cache = self._read()
            except Exception:
                self.cache = []
        return self.cache

    def _read(self):
        lv = self._listview()
        if not lv or not _u32.IsWindowVisible(lv):
            return []
        if lv != self.lv:
            self.close()
            pid = wt.DWORD()
            _u32.GetWindowThreadProcessId(lv, ctypes.byref(pid))
            # PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE
            self.proc = _k32.OpenProcess(0x0008 | 0x0010 | 0x0020, False, pid.value)
            if not self.proc:
                return []
            self.mem = _k32.VirtualAllocEx(self.proc, None, 4096, 0x3000, 0x04)
            if not self.mem:
                self.close()
                return []
            self.lv = lv
        res = ctypes.c_size_t()
        if not _u32.SendMessageTimeoutW(lv, self.LVM_GETITEMCOUNT, 0, 0, 0x2, 200, ctypes.byref(res)):
            return []
        out = []
        rc = RECT()
        pts = (wt.POINT * 2)()
        for i in range(min(int(res.value), 400)):
            rc.left, rc.top, rc.right, rc.bottom = self.LVIR_ICON, 0, 0, 0
            if not _k32.WriteProcessMemory(self.proc, self.mem, ctypes.byref(rc), ctypes.sizeof(rc), None):
                break
            ok = _u32.SendMessageTimeoutW(lv, self.LVM_GETITEMRECT, i, self.mem, 0x2, 200, ctypes.byref(res))
            if not ok:
                break
            if not res.value:
                continue
            if not _k32.ReadProcessMemory(self.proc, self.mem, ctypes.byref(rc), ctypes.sizeof(rc), None):
                break
            pts[0].x, pts[0].y, pts[1].x, pts[1].y = rc.left, rc.top, rc.right, rc.bottom
            _u32.MapWindowPoints(lv, None, pts, 2)
            out.append((pts[0].x, pts[0].y, pts[1].x, pts[1].y))
        return out


def icon_platforms(icon_rects, wins, min_y):
    occluders = [b for _, cls, b in wins if cls not in DESKTOP_CLASSES]
    plats = []
    for l, t, r, b in icon_rects:
        if t < min_y:
            continue
        for a, c in visible_segments(t, l, r, occluders):
            if c - a >= 0.6 * (r - l):
                plats.append({"kind": "icon", "y": t, "x0": a, "x1": c})
    return plats


# ---------------------------------------------------------------- on-screen edges

def grab(l, t, r, b):
    """Screenshot of a screen region as a PIL RGB image."""
    w, h = r - l, b - t
    sdc = _u32.GetDC(None)
    mdc = _g32.CreateCompatibleDC(sdc)
    bmp = _g32.CreateCompatibleBitmap(sdc, w, h)
    old = _g32.SelectObject(mdc, bmp)
    try:
        _g32.BitBlt(mdc, 0, 0, w, h, sdc, l, t, 0x00CC0020)  # SRCCOPY
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth, bmi.bmiHeader.biHeight = w, -h  # top-down
        bmi.bmiHeader.biPlanes, bmi.bmiHeader.biBitCount = 1, 32
        buf = ctypes.create_string_buffer(w * h * 4)
        _g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    finally:
        _g32.SelectObject(mdc, old)
        _g32.DeleteObject(bmp)
        _g32.DeleteDC(mdc)
        _u32.ReleaseDC(None, sdc)
    return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)


def find_edges(box, mask=(), min_run=32, block=4, thresh=14):
    """Long horizontal boundaries in a screen region.

    A pixel is an edge pixel when the rows 2px above and below it differ in
    brightness; an edge is a run of those at least `min_run` px long. `mask`
    lists screen rects to ignore (the pet's own pixels).
    """
    if not HAVE_PIL:
        return []
    l, t, r, b = (int(v) for v in box)
    if r - l < min_run or b - t < 6:
        return []
    img = grab(l, t, r, b).convert("L")
    w, h = img.size
    diff = ImageChops.difference(img.crop((0, 0, w, h - 2)), img.crop((0, 2, w, h)))
    diff = diff.point(lambda v: 255 if v >= thresh else 0)
    if mask:
        draw = ImageDraw.Draw(diff)
        for x0, y0, x1, y1 in mask:
            if x1 >= l and x0 <= r and y1 >= t - 4 and y0 <= b:
                draw.rectangle((x0 - l - 1, y0 - t - 3, x1 - l + 1, y1 - t + 1), fill=0)
    red = diff.reduce((block, 1)).point(lambda v: 255 if v >= 224 else 0)
    rw, data = red.width, red.tobytes()
    run = re.compile(b"\xff{%d,}" % max(2, -(-min_run // block)))
    edges, recent = [], []
    for row in range(red.height):
        base = row * rw
        for m in run.finditer(data, base, base + rw):
            a, c = m.start() - base, m.end() - base
            # The same boundary shows up on 2 neighbouring rows; keep the top one.
            dup = any(row - pr <= 3 and a < pc and c > pa for pr, pa, pc in recent)
            recent.append((row, a, c))
            if not dup:
                edges.append({"kind": "edge", "y": t + row + 2, "x0": l + a * block, "x1": l + c * block})
        recent = [x for x in recent if row - x[0] <= 3]
    return edges
