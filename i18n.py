"""Text for Claude Pet in every supported language, and language detection.

The language follows, in order: the pet's own setting (right-click menu),
Claude Code's `language` setting, the Claude desktop app's locale, and finally
the Windows display language.
"""

import ctypes
import glob
import json
import os

LANGS = [("zh", "中文"), ("en", "English")]

TEXT = {
    "zh": {
        # what the pet says for each state when there's no more specific detail
        "state_idle": "等你吩咐～", "state_thinking": "思考中…", "state_reading": "在翻文件…",
        "state_editing": "在改代码…", "state_running": "在跑命令…", "state_browsing": "在上网查资料…",
        "state_delegating": "派小帮手去干活…", "state_planning": "在列计划…", "state_working": "忙碌中…",
        "state_compacting": "整理记忆中…", "state_waiting": "需要你批准一下！", "state_done": "搞定啦！",
        "state_greet": "你好呀！", "state_sleeping": "Zzz…",
        # what Claude Code is doing (written by the hook as action + argument)
        "act_greet": "你好呀！", "act_prompt": "收到！思考中…", "act_think": "思考中…",
        "act_read": "正在读 %s", "act_grep": "正在搜索 “%s”", "act_glob": "正在找文件 %s",
        "act_ls": "正在翻目录", "act_edit": "正在改 %s", "act_write": "正在写 %s",
        "act_run": "正在运行 %s", "act_output": "在看命令输出", "act_websearch": "正在搜索：%s",
        "act_webfetch": "正在看 %s", "act_agent": "派小帮手：%s", "act_plan": "在更新计划",
        "act_skill": "在用技能 %s", "act_mcp": "正在用 %s", "act_tool": "正在用 %s",
        "act_permission": "需要你批准：%s", "act_permission_any": "需要你批准一下！",
        "act_idle_input": "等你回复～", "act_done": "搞定啦！", "act_compact": "整理记忆中…",
        # chatter
        "pet_lines": ["嘿嘿～", "摸摸头 ♥", "我在呢！", "今天也要加油鸭", "再摸就要变成小螃蟹了",
                      "(｡•ᴗ•｡)", "Claude 待命中！", "痒痒的～"],
        "rub_lines": ["呼噜呼噜～", "好舒服～", "再撸一会儿嘛", "♥♥♥"],
        "nag_lines": ["在吗在吗～", "Claude 在等你点批准哦", "戳戳你～"],
        "hop_lines": ["嘿咻！", "差点被压扁！", "跳上来啦"],
        "levels": ["刚认识", "小伙伴", "好朋友", "亲密搭档", "最佳拍档", "灵魂伴侣"],
        "outfits": {"none": "无", "party": "派对帽", "bow": "蝴蝶结", "shades": "墨镜",
                    "crown": "皇冠", "santa": "圣诞帽"},
        "sizes": {"small": "小", "medium": "中", "large": "大", "huge": "特大"},
        "shows": {"dance": "跳个舞", "stretch": "伸懒腰", "yawn": "打哈欠", "sit": "坐下",
                  "jump": "跳一跳", "eat": "吃零食", "confetti": "放彩带"},
        "reminders": {12: "到饭点啦，去吃午饭吧～", 18: "该吃晚饭啦！",
                      23: "夜深了，早点休息哦", 1: "已经凌晨啦…快去睡觉！"},
        "greet_night": "这么晚还在写代码呀…", "greet_morning": "早上好！今天也一起加油～",
        "greet_noon": "中午好，记得吃饭哦", "greet_afternoon": "下午好～", "greet_evening": "晚上好！",
        "new_year": "新年快乐！今年也请多关照～",
        "woke": "唔…醒啦～", "full": "吃不下啦～肚子圆滚滚的", "nom": "啊呜～",
        "dizzy": "晕晕乎乎…别晃啦", "confetti": "撒花～", "outfit_on": "好看吗？",
        "go_check": "快去 Claude 那边看看！", "ouch": "哎哟！",
        "milestone": "今天第 %d 次提问啦！", "streak": "连续陪你 %d 天啦！",
        "level_up": "亲密度升级：%s！", "busy_done": "搞定！这次忙了 %d 分钟，辛苦啦",
        "break": "写了一个小时啦，起来伸个懒腰吧～",
        "hover": "%s\n今天 %d 次提问 · %d 次工具 · 连续 %d 天\n♥ %s · 亲密度 %d",
        # right-click menu
        "m_header": "Claude Pet  ·  %d 个会话", "m_demo": "（演示中）", "m_session": "    %s：%s",
        "m_unknown": "未知项目", "m_stats": "今天 %d 次提问 · %d 次工具 · 连续 %d 天",
        "m_love": "♥ %s · 亲密度 %d%s · 被摸 %d 次", "m_next": "，再 %d 点升级",
        "m_feed": "喂零食（也可以双击它）", "m_show": "表演一个", "m_outfit": "装扮", "m_size": "大小",
        "m_wander": "到处溜达", "m_gravity": "重力（松手会掉下来）", "m_jump": "跳上窗口和桌面图标",
        "m_vision": "识别软件里的边界", "m_bubble": "冒泡显示进度", "m_sound": "需要批准时响一声",
        "m_topmost": "总在最前", "m_startup": "开机自动启动", "m_demo_mode": "演示模式",
        "m_reset": "回到右下角", "m_lang": "语言", "m_lang_auto": "自动（跟随 Claude / 系统）",
        "m_quit": "退出",
    },
    "en": {
        "state_idle": "At your service~", "state_thinking": "Thinking…", "state_reading": "Reading files…",
        "state_editing": "Editing code…", "state_running": "Running commands…",
        "state_browsing": "Browsing the web…", "state_delegating": "Sending a helper…",
        "state_planning": "Making a plan…", "state_working": "Busy busy…",
        "state_compacting": "Tidying up memory…", "state_waiting": "Need your approval!",
        "state_done": "All done!", "state_greet": "Hi there!", "state_sleeping": "Zzz…",
        "act_greet": "Hi there!", "act_prompt": "Got it! Thinking…", "act_think": "Thinking…",
        "act_read": "Reading %s", "act_grep": "Searching “%s”", "act_glob": "Looking for %s",
        "act_ls": "Browsing folders", "act_edit": "Editing %s", "act_write": "Writing %s",
        "act_run": "Running %s", "act_output": "Checking output", "act_websearch": "Searching: %s",
        "act_webfetch": "Reading %s", "act_agent": "Helper: %s", "act_plan": "Updating the plan",
        "act_skill": "Using skill %s", "act_mcp": "Using %s", "act_tool": "Using %s",
        "act_permission": "Approve %s?", "act_permission_any": "Need your approval!",
        "act_idle_input": "Waiting for you~", "act_done": "All done!", "act_compact": "Tidying up memory…",
        "pet_lines": ["Hehe~", "Pat pat ♥", "I'm here!", "Let's do our best today!",
                      "Keep patting and I'll turn into a crab", "(｡•ᴗ•｡)", "Claude on standby!",
                      "That tickles~"],
        "rub_lines": ["Purrrr~", "So comfy~", "A little more, please", "♥♥♥"],
        "nag_lines": ["Hello? Anyone there?", "Claude is waiting for your OK", "Poke poke~"],
        "hop_lines": ["Hup!", "Almost got squished!", "Up I go!"],
        "levels": ["Stranger", "Buddy", "Good friend", "Close partner", "Best partner", "Soulmate"],
        "outfits": {"none": "None", "party": "Party hat", "bow": "Bow", "shades": "Shades",
                    "crown": "Crown", "santa": "Santa hat"},
        "sizes": {"small": "Small", "medium": "Medium", "large": "Large", "huge": "Huge"},
        "shows": {"dance": "Dance", "stretch": "Stretch", "yawn": "Yawn", "sit": "Sit down",
                  "jump": "Jump", "eat": "Eat a snack", "confetti": "Confetti"},
        "reminders": {12: "Lunch time! Go grab some food~", 18: "Dinner time!",
                      23: "It's getting late, get some rest", 1: "It's past midnight… time for bed!"},
        "greet_night": "Coding this late?…", "greet_morning": "Good morning! Let's have a great day~",
        "greet_noon": "Hi! Don't forget lunch", "greet_afternoon": "Good afternoon~",
        "greet_evening": "Good evening!", "new_year": "Happy New Year!",
        "woke": "Mm… I'm awake~", "full": "Too full~ my belly is round", "nom": "Nom~",
        "dizzy": "So dizzy… stop shaking", "confetti": "Yay~", "outfit_on": "Do I look good?",
        "go_check": "Go check on Claude!", "ouch": "Ouch!",
        "milestone": "Prompt #%d today!", "streak": "%d days in a row together!",
        "level_up": "Friendship up: %s!", "busy_done": "Done! That took %d min, great work",
        "break": "An hour of coding! Time to stretch~",
        "hover": "%s\nToday: %d prompts · %d tools · %d-day streak\n♥ %s · affection %d",
        "m_header": "Claude Pet  ·  %d session(s)", "m_demo": " (demo)", "m_session": "    %s: %s",
        "m_unknown": "unknown project", "m_stats": "Today: %d prompts · %d tools · %d-day streak",
        "m_love": "♥ %s · affection %d%s · petted %d times", "m_next": ", %d to next level",
        "m_feed": "Feed a snack (or double-click)", "m_show": "Do a trick", "m_outfit": "Outfit",
        "m_size": "Size", "m_wander": "Wander around", "m_gravity": "Gravity (falls when dropped)",
        "m_jump": "Jump onto windows & icons", "m_vision": "Detect edges inside apps",
        "m_bubble": "Show progress bubbles", "m_sound": "Beep when approval is needed",
        "m_topmost": "Always on top", "m_startup": "Start with Windows", "m_demo_mode": "Demo mode",
        "m_reset": "Back to the corner", "m_lang": "Language", "m_lang_auto": "Auto (follow Claude / system)",
        "m_quit": "Quit",
    },
}


def normalize(value):
    """Map a locale or language name ('zh-Hans', 'chinese', 'en-US'…) to 'zh' / 'en'."""
    v = str(value or "").strip().lower()
    if not v:
        return None
    if v.startswith("zh") or "chinese" in v or "中文" in v or "汉语" in v:
        return "zh"
    return "en"


def _read_json(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def claude_code_language():
    """Claude Code's `language` setting (the language Claude replies in)."""
    for path in (os.path.join(os.path.expanduser("~"), ".claude", "settings.local.json"),
                 os.path.join(os.path.expanduser("~"), ".claude", "settings.json")):
        data = _read_json(path)
        if isinstance(data, dict) and data.get("language"):
            return normalize(data["language"])
    return None


def claude_app_language():
    """UI locale of the Claude desktop app."""
    candidates = [os.path.join(os.environ.get("APPDATA", ""), "Claude", "config.json")]
    candidates += glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Claude-Data", "*", "config.json"))
    newest = None
    for path in candidates:
        data = _read_json(path)
        if isinstance(data, dict) and data.get("locale"):
            mtime = os.path.getmtime(path)
            if newest is None or mtime > newest[0]:
                newest = (mtime, data["locale"])
    return normalize(newest[1]) if newest else None


def system_language():
    try:
        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "zh" if langid & 0x3FF == 0x04 else "en"
    except Exception:
        return "en"


def detect(setting="auto"):
    if setting in TEXT:
        return setting
    return claude_code_language() or claude_app_language() or system_language()
