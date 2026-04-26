"""
Tokyo Train Ticker — framebuffer display for Adafruit PiTFT 2.8" (320x240)
Uses Pillow + direct /dev/fb0 writes. No SDL/X11/Wayland needed.

Run:               sudo python3 pi/pygame_display.py
One-time calibration (device level):  sudo bash pi/setup_touch.sh
"""
import os
import sys
import time
import threading
import signal
import math as _math

try:
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
except ImportError:
    print("Missing deps: sudo apt install -y python3-pil python3-numpy")
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("Missing httpx: sudo pip3 install --break-system-packages httpx")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 320, 240
API_BASE = os.getenv("API_BASE", "http://localhost:8000")
FB_DEV   = os.getenv("FB_DEV",   "/dev/fb0")
FPS      = 4

# ── Layout constants ──────────────────────────────────────────────────────────
HDR_H    = 22
HERO_TOP = HDR_H
HERO_BOT = HERO_TOP + 88
FOOTER_H = 32
FOOTER_Y = SCREEN_H - FOOTER_H
STRIP_H  = 24
COL_H    = 15
ROW_H    = 22

# ── Car formation data ────────────────────────────────────────────────────────
CARS = {
    "JY": 11, "JC": 10, "JB": 10, "JK": 15, "JA": 10,
    "JH": 15, "JU": 15, "JE": 15, "JO": 15,
    "G":  6,  "M":  10, "H":  8,  "T":  10, "C":  10,
    "Y":  8,  "Z":  8,  "N":  6,  "F":  8,  "A":  8,
    "I":  6,  "S":  8,  "E":  6,  "TY": 8,  "DT": 10,
    "OM": 4,  "MG": 5,  "KO": 10, "OH": 10, "SI": 8,
    "TJ": 8,  "KS": 8,
}

# ── Japanese destination/line name lookups ────────────────────────────────────
DEST_JA = {
    "IKEBUKURO": "池袋",   "SHIBUYA": "渋谷",     "SHINJUKU": "新宿",
    "UENO": "上野",         "TOKYO": "東京",        "TAKAO": "高尾",
    "TACHIKAWA": "立川",   "OGIKUBO": "荻窪",      "CHIBA": "千葉",
    "MITAKA": "三鷹",      "OMIYA": "大宮",         "OFUNA": "大船",
    "YOKOHAMA": "横浜",    "OSAKI": "大崎",         "UTSUNOMIYA": "宇都宮",
    "TAKASAKI": "高崎",    "KAMAKURA": "鎌倉",      "ZUSHI": "逗子",
    "SHINAGAWA": "品川",   "NARITA": "成田",
    "ASAKUSA": "浅草",     "GINZA": "銀座",          "HONANCHO": "方南町",
    "KITASENJU": "北千住", "NAKAMEGURO": "中目黒",   "NAKA-MEGURO": "中目黒",
    "NAKANO": "中野",      "NISHIFUNABASHI": "西船橋","NISHI-FUNABASHI": "西船橋",
    "YOYOGI-UEHARA": "代々木上原", "AYASE": "綾瀬", "ABIKO": "我孫子",
    "WAKOSHI": "和光市",   "SHIN-KIBA": "新木場",    "SHINKIBA": "新木場",
    "OSHIAGE": "押上",     "NAGATSUTA": "長津田",    "TOCHOMAE": "都庁前",
    "MEGURO": "目黒",      "NISHI-TAKASHIMADAIRA": "西高島平",
    "MOTOMACHI-CHUKAGAI": "元町・中華街",
    "NISHI-MAGOME": "西馬込",       "HIKARIGAOKA": "光が丘",
    "NERIMA-KASUGACHO": "練馬春日町",
    "FUTAKO-TAMAGAWA": "二子玉川",  "MIZONOKUCHI": "溝の口",
    "MOTOSUMIYOSHI": "元住吉",      "CHOFU": "調布",
    "HASHIMOTO": "橋本",            "KEIO-HACHIOJI": "京王八王子",
    "KEIO-SAGAMIHARA": "京王相模原","KICHIJOJI": "吉祥寺",
    "ODAWARA": "小田原",            "FUJISAWA": "藤沢",
    "KARAKIDA": "唐木田",           "KATASE-ENOSHIMA": "片瀬江ノ島",
    "HANNO": "飯能",                "OGOSE": "越生",
    "KAWAGOE": "川越",              "TOBU-NIKKO": "東武日光",
    "AIZUWAKAMATSU": "会津若松",    "URAGA": "浦賀",
    "NARITA-SKYACCESS": "成田スカイアクセス",
    "HANEDA-AIRPORT": "羽田空港",   "NARITA-AIRPORT": "成田空港",
    "HANEDA-AIRPORT-T1": "羽田空港第1ターミナル",
    "TOYOSU": "豊洲",   "SHIMBASHI": "新橋",         "HAMAMATSUCHO": "浜松町",
    "URAWA-MISONO": "浦和美園",     "SHINOZAKIMACHI": "篠崎",
    "HANA-KOGANEI": "花小金井",     "NISHI-SHINJUKU": "西新宿",
    "MUSASHI-KYURYO": "武蔵丘",
}

LINE_NAME_JA = {
    "JY": "山手線",        "JC": "中央線",          "JB": "中央・総武線",
    "JK": "京浜東北線",    "JA": "埼京線",           "JH": "横須賀線",
    "JU": "宇都宮・高崎線","JE": "京葉線",           "JO": "横須賀・総武線",
    "G":  "銀座線",        "M":  "丸ノ内線",         "H":  "日比谷線",
    "T":  "東西線",        "C":  "千代田線",         "Y":  "有楽町線",
    "Z":  "半蔵門線",      "N":  "南北線",            "F":  "副都心線",
    "A":  "浅草線",        "I":  "三田線",            "S":  "新宿線",
    "E":  "大江戸線",
    "TY": "東横線",        "DT": "田園都市線",       "OM": "大井町線",
    "MG": "目黒線",        "KK": "空港線",
    "KO": "京王線",        "KL": "京王相模原線",      "KI": "井の頭線",
    "OH": "小田原線",      "OE": "江ノ島線",
    "SI": "池袋線",        "SS": "新宿線",
    "TJ": "東上線",        "TS": "スカイツリーライン",
    "KS": "本線",          "KE": "本線",
    "MM": "みなとみらい線","SR": "埼玉高速鉄道線",
    "RI": "りんかい線",    "YU": "ゆりかもめ",
    "MO": "東京モノレール",
}

# ── Colors (RGB tuples) ───────────────────────────────────────────────────────
BLACK   = (0,   0,   0)
WHITE   = (220, 220, 220)
DIM     = (55,  55,  55)
DARK    = (18,  18,  18)
ORANGE  = (255, 107, 53)
YELLOW  = (255, 215, 0)
GREEN   = (154, 205, 50)
BORDER  = (28,  28,  28)

# ── Framebuffer ───────────────────────────────────────────────────────────────
def _fb_bpp():
    try:
        return int(open("/sys/class/graphics/fb0/bits_per_pixel").read().strip())
    except Exception:
        return 16

def _img_to_bytes(img: Image.Image) -> bytes:
    bpp = _fb_bpp()
    if bpp == 32:
        return img.convert("RGBA").tobytes()
    arr = np.array(img.convert("RGB"), dtype=np.uint16)
    r = (arr[:,:,0] >> 3).astype(np.uint16)
    g = (arr[:,:,1] >> 2).astype(np.uint16)
    b = (arr[:,:,2] >> 3).astype(np.uint16)
    rgb565 = (r << 11) | (g << 5) | b
    return rgb565.tobytes()

_fb = None
def _open_fb():
    global _fb
    try:
        _fb = open(FB_DEV, "wb")
    except PermissionError:
        print(f"Cannot open {FB_DEV} — run with sudo")
        sys.exit(1)
    for tty in ("/dev/tty1", "/dev/tty"):
        try:
            with open(tty, "wb") as t:
                t.write(b"\033[?25l\033[2J")
            break
        except Exception:
            pass

def flush(img: Image.Image):
    if _fb is None:
        return
    try:
        _fb.seek(0)
        _fb.write(_img_to_bytes(img))
        _fb.flush()
    except Exception as e:
        print(f"fb write error: {e}")

def _cleanup():
    if _fb is not None:
        try:
            _fb.seek(0)
            _fb.write(b"\x00" * SCREEN_W * SCREEN_H * 2)
            _fb.flush()
        except Exception:
            pass
    for tty in ("/dev/tty1", "/dev/tty"):
        try:
            with open(tty, "wb") as t:
                t.write(b"\033[?25h\033c")
            break
        except Exception:
            pass

# ── Fonts ─────────────────────────────────────────────────────────────────────
FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
]

def _load_font(size):
    for p in FONT_PATHS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

fonts = {}
def get_font(key):
    if key not in fonts:
        sizes = {"xxs": 10, "xs": 13, "sm": 16, "md": 19, "lg": 23, "xl": 30, "hero": 40}
        fonts[key] = _load_font(sizes.get(key, 12))
    return fonts[key]

# ── CJK font support ──────────────────────────────────────────────────────────
CJK_FONT_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Light.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Light.ttc",
    "/usr/share/fonts/truetype/vlgothic/VL-Gothic-Regular.ttf",
    "/usr/share/fonts/truetype/vlgothic/VL-PGothic-Regular.ttf",
    "/usr/share/fonts/truetype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
]

_cjk_fonts = {}
def get_cjk_font(size):
    if size not in _cjk_fonts:
        for p in CJK_FONT_PATHS:
            if os.path.exists(p):
                try:
                    _cjk_fonts[size] = ImageFont.truetype(p, size)
                    break
                except Exception:
                    continue
        if size not in _cjk_fonts:
            _cjk_fonts[size] = get_font("xs")
    return _cjk_fonts[size]

def _ensure_cjk_font():
    if any(os.path.exists(p) for p in CJK_FONT_PATHS):
        return
    import subprocess
    for pkg in ("fonts-noto-cjk", "fonts-vlgothic", "fonts-ipafont-gothic"):
        try:
            print(f"CJK fonts not found — installing {pkg}...")
            subprocess.run(["apt-get", "install", "-y", "-q", pkg],
                           check=True, timeout=180)
            print(f"Installed {pkg}")
            return
        except Exception as e:
            print(f"Could not install {pkg}: {e}")
    print("Run manually: sudo apt install -y fonts-vlgothic")

# ── State ─────────────────────────────────────────────────────────────────────
state = {
    "mode":           "station",
    "station_id":     "shibuya",
    "station_en":     "SHIBUYA",
    "station_ja":     "渋谷",
    "line_code":      "JY",
    "station_trains": [],
    "line_trains":    [],
    "all_stations":   [],
    "all_lines":      [],
    "demo_mode":      True,
    "connected":      False,
    "last_update":    0,
    "platform_filter":"ALL",
    "plt_popup_open": False,
    "picker_open":    False,
    "picker_type":    None,
    "picker_results": [],
    "picker_scroll":  0,
    "list_scroll":    0,
    "confirm_exit":   False,
}

_hold_start_time: float = 0.0
_hold_pos: tuple = (0, 0)
_hold_consumed: bool = False
_service_start_time: float = 0.0
_last_tap_pos = None
_last_tap_time: float = 0.0

# ── Data fetching ─────────────────────────────────────────────────────────────
def fetch(url):
    try:
        with httpx.Client(timeout=6.0) as c:
            r = c.get(url)
            r.raise_for_status()
            return r.json()
    except Exception:
        return None

def refresh_data():
    if state["mode"] == "station":
        data = fetch(f"{API_BASE}/api/trains/station/{state['station_id']}")
        if data is not None:
            state["station_trains"] = data
            state["last_update"] = time.time()
    else:
        data = fetch(f"{API_BASE}/api/trains/line/{state['line_code']}")
        if data is not None:
            state["line_trains"] = data
            state["last_update"] = time.time()

def load_meta():
    lines    = fetch(f"{API_BASE}/api/lines")
    stations = fetch(f"{API_BASE}/api/stations")
    status   = fetch(f"{API_BASE}/api/status")
    if lines:    state["all_lines"]    = lines
    if stations: state["all_stations"] = stations
    if status:   state["demo_mode"]    = status.get("demo_mode", True)
    state["connected"] = bool(lines)

def background_loop():
    load_meta()
    while True:
        refresh_data()
        time.sleep(15)

# ── Drawing helpers ────────────────────────────────────────────────────────────
def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def brighten(rgb, f=1.4, add=40):
    return tuple(min(255, int(c * f + add)) for c in rgb)

def text_w(draw, text, font):
    bb = draw.textbbox((0,0), text, font=font)
    return bb[2] - bb[0]

def draw_text(draw, x, y, text, font, color=WHITE, max_w=None):
    if max_w:
        while text and text_w(draw, text, font) > max_w:
            text = text[:-2] + "…"
    draw.text((x, y), text, font=font, fill=color)

def draw_badge(draw, x, y, code, color, text_color, shape, size=13):
    f = get_font("xs")
    tw = text_w(draw, code, f)
    w  = max(tw + 6, size)
    h  = size
    rgb_bg = hex_to_rgb(color)
    rgb_fg = hex_to_rgb(text_color)
    rect = [x, y, x + w, y + h]
    if shape == "circle":
        cx, cy, r = x + w//2, y + h//2, h//2
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=rgb_bg)
    elif shape == "square":
        draw.rectangle(rect, fill=rgb_bg)
    else:
        draw.rounded_rectangle(rect, radius=2, fill=rgb_bg)
    draw.text((x + (w - tw)//2, y + (h - f.size)//2), code, font=f, fill=rgb_fg)
    return w

def draw_dest(draw, x, y, dest_en, font_en, color, max_w):
    key = dest_en.upper().lstrip("→ ").strip()
    ja  = DEST_JA.get(key, "")
    if ja:
        f_ja = get_cjk_font(13)
        draw.text((x, y), ja, font=f_ja, fill=(150, 125, 50))
        x     += text_w(draw, ja, f_ja) + 3
        max_w -= text_w(draw, ja, f_ja) + 3
    draw_text(draw, x, y, dest_en, font_en, color, max_w)

# ── Operator logo images ──────────────────────────────────────────────────────

_OPERATOR_LOGO_FILES = {
    'JR-East':    'jr-east.png',
    'TokyoMetro': 'tokyo-metro.png',
    'Tokyu':      'tokyu.png',
    'Tobu':       'tobu.png',
    'Seibu':      'seibu.png',
    'Odakyu':     'odakyu.png',
    'Keio':       'keio.png',
    'Keisei':     'keisei.png',
    'Keikyu':     'keikyu.png',
}

_op_logos = {}

def _load_operator_logos():
    logo_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'frontend', 'logos')
    iw, ih = 62, 16
    for operator, fname in _OPERATOR_LOGO_FILES.items():
        path = os.path.join(logo_dir, fname)
        try:
            raw = Image.open(path).convert('RGB')
            ow, oh = raw.size
            scale = min(iw / ow, ih / oh)
            nw, nh = round(ow * scale), round(oh * scale)
            resized = raw.resize((nw, nh), Image.LANCZOS)
            icon = Image.new('RGB', (iw, ih), (255, 255, 255))
            icon.paste(resized, ((iw - nw) // 2, (ih - nh) // 2))
            _op_logos[operator] = icon
        except Exception as e:
            print(f"Logo load failed ({fname}): {e}")

# ── Operator logo drawing (fallback geometric) ────────────────────────────────

def _logo_bg(draw, bx, by, size, color, radius=None):
    if radius is None:
        radius = max(4, size // 8)
    draw.rounded_rectangle([bx, by, bx + size, by + size], radius=radius, fill=color)

def draw_operator_logo(draw, bx, by, size, operator, code, color, text_color):
    bg  = hex_to_rgb(color)
    fg  = hex_to_rgb(text_color)
    cx  = bx + size // 2
    cy  = by + size // 2

    if operator == "JR-East":
        _logo_bg(draw, bx, by, size, (22, 22, 22))
        dot = max(4, size // 9)
        draw.ellipse([bx+size-dot*3, by+dot, bx+size-dot, by+dot*3], fill=(200, 70, 20))
        f = get_font("xl"); lw = text_w(draw, "JR", f)
        draw.text((cx - lw//2, cy - f.size//2), "JR", font=f, fill=(220, 220, 220))

    elif operator == "TokyoMetro":
        _logo_bg(draw, bx, by, size, (0, 157, 224), radius=size // 10)
        f = get_font("xl"); lw = text_w(draw, "M", f)
        my = cy - f.size // 2 + 2
        draw.text((cx - lw//2, my), "M", font=f, fill=(255, 255, 255))
        dr = max(3, size // 13)
        dy = my - dr - 2
        for dx in (-lw//4, lw//4):
            draw.ellipse([cx+dx-dr, dy-dr, cx+dx+dr, dy+dr], fill=(255, 255, 255))
        f2 = get_font("xs"); lnw = text_w(draw, code, f2)
        draw.text((cx - lnw//2, by + size - f2.size - 2), code, font=f2, fill=(200, 240, 255))

    elif operator == "Toei":
        _logo_bg(draw, bx, by, size, (0, 160, 74))
        pad = size // 7
        fan_cx, fan_cy = cx, by + size - pad - 2
        fan_r = int(size * 0.62)
        draw.pieslice([fan_cx-fan_r, fan_cy-fan_r, fan_cx+fan_r, fan_cy+fan_r],
                      start=200, end=340, fill=(255, 255, 255))
        nw = max(3, size // 11)
        draw.rectangle([fan_cx-nw, by+pad+2, fan_cx+nw, fan_cy], fill=(0, 160, 74))
        draw.rectangle([fan_cx-2, fan_cy-2, fan_cx+2, by+size-3], fill=(255, 255, 255))
        f2 = get_font("xs"); lnw = text_w(draw, code, f2)
        draw.text((cx - lnw//2, by+2), code, font=f2, fill=(200, 255, 200))

    elif operator == "Tokyu":
        _logo_bg(draw, bx, by, size, (230, 0, 18))
        ro, ri = size // 3, size // 7
        pts = []
        for i in range(10):
            a = _math.pi * i / 5 - _math.pi / 2
            r = ro if i % 2 == 0 else ri
            pts.append((cx + r * _math.cos(a), cy - size//14 + r * _math.sin(a)))
        draw.polygon(pts, fill=(255, 255, 255))

    elif operator == "Tobu":
        _logo_bg(draw, bx, by, size, (0, 65, 160))
        f = get_font("lg"); lw = text_w(draw, "TOBU", f)
        draw.text((cx - lw//2, cy - f.size//2), "TOBU", font=f, fill=(255, 255, 255))

    elif operator == "Seibu":
        _logo_bg(draw, bx, by, size, (255, 255, 255), radius=4)
        r, sh = size // 3, size // 8
        draw.ellipse([cx-r-sh, cy-r, cx+r-sh, cy+r], fill=(0, 113, 188))
        draw.ellipse([cx-r+sh, cy-r, cx+r+sh, cy+r], fill=(0, 170, 220))
        f = get_font("lg"); sw = text_w(draw, "S", f)
        draw.text((cx-sw//2, cy-f.size//2), "S", font=f, fill=(255, 255, 255))

    elif operator == "Odakyu":
        _logo_bg(draw, bx, by, size, (0, 173, 239))
        r = size // 4; ox = size // 10
        draw.ellipse([cx-r+ox, cy-r, cx+r+ox, cy+r], fill=(255, 255, 255))
        draw.polygon([(cx-r+ox+2, cy),
                      (cx - size//3, cy - size//5),
                      (cx - size//3, cy + size//5)], fill=(255, 255, 255))

    elif operator in ("Keio", "Keisei"):
        col = (0, 31, 98) if operator == "Keio" else bg
        _logo_bg(draw, bx, by, size, col)
        lbl = "KEIO" if operator == "Keio" else code
        f = get_font("lg"); lw = text_w(draw, lbl, f)
        draw.text((cx - lw//2, cy - f.size//2), lbl, font=f, fill=(255, 255, 255))

    elif operator == "Keikyu":
        _logo_bg(draw, bx, by, size, (211, 0, 47))
        f = get_font("xl"); lw = text_w(draw, "KQ", f)
        draw.text((cx - lw//2, cy - f.size//2), "KQ", font=f, fill=(255, 255, 255))

    else:
        draw.rounded_rectangle([bx, by, bx+size, by+size], radius=max(4, size//8), fill=bg)
        f = get_font("xl"); lw = text_w(draw, code, f)
        draw.text((cx - lw//2, cy - f.size//2), code, font=f, fill=fg)

def dot_grid_overlay(img):
    arr = np.array(img)
    for y in range(0, SCREEN_H, 4):
        for x in range(0, SCREEN_W, 4):
            arr[y, x] = np.clip(arr[y, x].astype(int) - 15, 0, 255)
    return Image.fromarray(arr.astype(np.uint8))

# ── Screen sections ───────────────────────────────────────────────────────────
def draw_header(draw):
    draw.rectangle([0, 0, SCREEN_W, HDR_H], fill=(8, 8, 8))
    draw.line([0, HDR_H, SCREEN_W, HDR_H], fill=BORDER)
    f_ja = get_cjk_font(13)
    f_en = get_font("sm")
    f_clk = get_font("xs")
    ja = state["station_ja"]
    en = state["station_en"]
    draw.text((4, 4), ja, font=f_ja, fill=(160, 130, 60))
    x = 4 + text_w(draw, ja, f_ja) + 5
    draw_text(draw, x, 4, en, f_en, WHITE, max_w=180)
    from datetime import datetime, timezone, timedelta
    JST = timezone(timedelta(hours=9))
    clk = datetime.now(JST).strftime("%H:%M:%S")
    cw = text_w(draw, clk, f_clk)
    draw.text((SCREEN_W - cw - 4, 6), clk, font=f_clk, fill=(70, 70, 70))

def draw_hero_card(draw, img):
    trains  = state["station_trains"]
    pf      = state["platform_filter"]
    visible = [t for t in trains if pf == "ALL" or str(t.get("platform","")) == pf]
    train   = visible[0] if visible else None

    draw.rectangle([0, HERO_TOP, SCREEN_W, HERO_BOT], fill=(5, 5, 5))
    draw.line([0, HERO_BOT, SCREEN_W, HERO_BOT], fill=BORDER)

    if not train:
        draw.text((10, HERO_TOP + 36), "NO SERVICE DATA", font=get_font("sm"), fill=DIM)
        return

    color   = hex_to_rgb(train.get("color", "#888888"))
    bright  = brighten(color)
    shape   = train.get("shape", "rect")

    code     = train["line_code"]
    line_obj = next((l for l in state["all_lines"] if l["code"] == code), {})
    operator = line_obj.get("operator", "")

    # Primary: colored line-code badge
    badge_size = 60
    bx = (100 - badge_size) // 2
    by = HERO_TOP + 4
    rgb_bg = color
    rgb_fg = hex_to_rgb(train.get("text_color", "#ffffff"))
    if shape == "circle":
        draw.ellipse([bx, by, bx+badge_size, by+badge_size], fill=rgb_bg)
    elif shape == "square":
        draw.rectangle([bx, by, bx+badge_size, by+badge_size], fill=rgb_bg)
    else:
        draw.rounded_rectangle([bx, by, bx+badge_size, by+badge_size],
                                radius=max(4, badge_size//8), fill=rgb_bg)
    f_code = get_font("hero")
    lw = text_w(draw, code, f_code)
    draw.text((bx + (badge_size-lw)//2, by + (badge_size-f_code.size)//2),
              code, font=f_code, fill=rgb_fg)

    # Secondary: operator logo below badge
    logo_y = by + badge_size + 2
    if operator in _op_logos:
        logo_img = _op_logos[operator]
        lw_logo, lh_logo = logo_img.size
        img.paste(logo_img, (bx + (badge_size - lw_logo)//2, logo_y))
    else:
        draw_operator_logo(draw, bx, logo_y, 20, operator, code,
                           train.get("color","#888888"), train.get("text_color","#000000"))

    rx = 104
    line_name    = line_obj.get("name", code)
    line_name_ja = LINE_NAME_JA.get(code, "")

    n_cars = CARS.get(code, 8)
    car_avail = SCREEN_W - 4 - 218
    car_w = min(14, max(5, (car_avail - (n_cars - 1) * 2) // n_cars))
    car_gap = 2
    total_car_w = n_cars * (car_w + car_gap) - car_gap
    car_x = 218 + max(0, (car_avail - total_car_w) // 2)
    car_y = HERO_TOP + 4
    for ci in range(n_cars):
        cx_car = car_x + ci * (car_w + car_gap)
        draw.rectangle([cx_car, car_y, cx_car + car_w, car_y + 9], fill=color)
    f_xs = get_font("xs")
    draw.text((car_x + total_car_w + 3, car_y), f"{n_cars}c", font=f_xs, fill=(50, 50, 50))

    if line_name_ja:
        f_ja = get_cjk_font(10)
        draw.text((rx, HERO_TOP + 4), line_name_ja, font=f_ja, fill=(130, 108, 45))
        lnj_w = text_w(draw, line_name_ja, f_ja)
        draw_text(draw, rx + lnj_w + 3, HERO_TOP + 5, line_name.upper(),
                  f_xs, (40, 40, 40), max_w=110 - lnj_w - 3)
    else:
        draw_text(draw, rx, HERO_TOP + 4, line_name.upper(), f_xs, DIM, max_w=110)

    dest_en = ("→ " + train.get("destination", "")).upper()
    draw_dest(draw, rx, HERO_TOP + 16, dest_en, get_font("md"), bright, max_w=210)

    eta = train.get("eta_min", 0)
    if eta <= 1:
        eta_str, eta_color = "NOW", ORANGE
        if int(time.time() * 2) % 2 == 0:
            eta_color = (120, 50, 20)
    elif eta <= 4:
        eta_str, eta_color = f"{eta} MIN", YELLOW
    else:
        eta_str, eta_color = f"{eta} MIN", GREEN

    draw.text((rx, HERO_TOP + 30), eta_str, font=get_font("hero"), fill=eta_color)

    if train.get("delay_min", 0) > 0:
        draw.text((rx, HERO_TOP + 64), f"+{train['delay_min']}m delay",
                  font=get_font("xs"), fill=(230, 120, 34))
    plt = train.get("platform", "")
    if plt:
        draw.text((rx + 100, HERO_TOP + 64), f"PLT {plt}",
                  font=get_font("xs"), fill=(60, 60, 60))

def _plt_popup_platforms():
    trains = state["station_trains"]
    seen = set(str(t.get("platform","")).strip() for t in trains
               if t.get("platform") and t.get("platform") != "–")
    return ["ALL"] + sorted(seen, key=lambda v: (float(v) if v.replace(".","").isdigit() else 999, v))

PLT_POPUP_ITEM_H = 18
PLT_POPUP_W      = 52
PLT_POPUP_PAD    = 3

def plt_popup_rect():
    platforms = _plt_popup_platforms()
    h = len(platforms) * PLT_POPUP_ITEM_H + PLT_POPUP_PAD * 2
    x = SCREEN_W - PLT_POPUP_W - 4
    y = HERO_BOT + COL_H + 1
    return x, y, PLT_POPUP_W, h

def draw_plt_popup(draw):
    platforms = _plt_popup_platforms()
    px, py, pw, ph = plt_popup_rect()
    pf = state["platform_filter"]
    f  = get_font("xs")
    draw.rounded_rectangle([px-1, py, px+pw+1, py+ph], radius=3, fill=(18, 18, 18))
    draw.rounded_rectangle([px-1, py, px+pw+1, py+ph], radius=3, outline=(70, 70, 70))
    for i, label in enumerate(platforms):
        iy = py + PLT_POPUP_PAD + i * PLT_POPUP_ITEM_H
        active = (label == pf)
        if active:
            draw.rounded_rectangle([px+2, iy, px+pw-2, iy+PLT_POPUP_ITEM_H-2],
                                   radius=2, fill=(40, 40, 40))
        lw = text_w(draw, label, f)
        draw.text((px + (pw - lw)//2, iy + (PLT_POPUP_ITEM_H - f.size)//2),
                  label, font=f, fill=WHITE if active else (110, 110, 110))

def draw_upcoming_list(draw, top_y):
    trains  = state["station_trains"]
    pf      = state["platform_filter"]
    visible = [t for t in trains if pf == "ALL" or str(t.get("platform","")) == pf]
    scroll  = state["list_scroll"]
    upcoming = visible[1:][scroll:]

    h_y = top_y
    draw.rectangle([0, h_y, SCREEN_W, h_y + COL_H], fill=(10, 10, 10))
    draw.line([0, h_y + COL_H, SCREEN_W, h_y + COL_H], fill=BORDER)
    f_hdr = get_font("xxs")
    draw.text((4,   h_y+3), "LINE",        font=f_hdr, fill=(45,45,45))
    draw.text((36,  h_y+3), "NEXT TRAINS", font=f_hdr, fill=(45,45,45))
    draw.text((289, h_y+3), "MIN",         font=f_hdr, fill=(45,45,45))
    pf_disp  = state["platform_filter"]
    plt_txt  = f"P{pf_disp}" if pf_disp != "ALL" else "PLT"
    plt_col  = (180, 150, 40) if pf_disp != "ALL" else (55, 55, 55)
    draw.text((248, h_y+3), plt_txt, font=f_hdr, fill=plt_col)

    row_y  = h_y + COL_H + 1
    f_sm   = get_font("sm")
    f_xs   = get_font("xs")
    BUCKETS = [
        (2,  "ARRIVING"),
        (10, "NEXT 10 MIN"),
        (20, "20 MIN"),
        (30, "30 MIN"),
        (45, "45 MIN"),
        (60, "1 HOUR"),
    ]
    last_bucket = -1

    for t in upcoming:
        if row_y >= FOOTER_Y:
            break
        eta  = t.get("eta_min", 0)
        bidx = next((i for i, (m, _) in enumerate(BUCKETS) if eta <= m), -1)
        if bidx >= 0 and bidx != last_bucket:
            lbl = BUCKETS[bidx][1]
            draw.rectangle([0, row_y, SCREEN_W, row_y+13], fill=BLACK)
            draw.text((4, row_y+2), lbl, font=f_hdr, fill=(35,35,35))
            lx = 4 + text_w(draw, lbl, f_hdr) + 4
            draw.line([lx, row_y+6, SCREEN_W-4, row_y+6], fill=(20,20,20))
            last_bucket = bidx
            row_y += 13
            if row_y >= FOOTER_Y:
                break

        bg = (10,10,10) if (upcoming.index(t) % 2 == 0) else BLACK
        draw.rectangle([0, row_y, SCREEN_W, row_y+ROW_H], fill=bg)

        color  = hex_to_rgb(t.get("color", "#888"))
        bright = brighten(color)
        code   = t["line_code"]
        plat   = str(t.get("platform") or "–")

        draw.rectangle([0, row_y, 3, row_y + ROW_H], fill=color)

        draw_badge(draw, 5, row_y+3, code, t.get("color","#888"),
                   t.get("text_color","#fff"), t.get("shape","rect"), size=14)

        dest = t.get("destination","").upper()
        draw_dest(draw, 38, row_y+4, dest, f_xs, bright, max_w=196)

        if t.get("delay_min", 0) > 0:
            draw.ellipse([240, row_y+6, 245, row_y+11], fill=(230,120,34))

        draw.text((248, row_y+4), plat, font=f_xs, fill=(60,60,60))

        if eta <= 1:
            etxt, ecol = "NOW", ORANGE
            if int(time.time()*2)%2 == 0: ecol = (100,40,15)
        elif eta <= 4:
            etxt, ecol = str(eta), YELLOW
        else:
            etxt, ecol = str(eta), GREEN
        ew = text_w(draw, etxt, f_sm)
        draw.text((SCREEN_W - ew - 4, row_y+3), etxt, font=f_sm, fill=ecol)

        draw.line([0, row_y+ROW_H-1, SCREEN_W, row_y+ROW_H-1], fill=BORDER)
        row_y += ROW_H

def draw_line_tracker(draw):
    trains   = state["line_trains"]
    line_obj = next((l for l in state["all_lines"] if l["code"] == state["line_code"]), {})
    color    = hex_to_rgb(line_obj.get("color", "#888"))
    bright   = brighten(color)
    shape    = line_obj.get("shape", "rect")

    draw.rectangle([0, HERO_TOP, SCREEN_W, HERO_TOP+24], fill=(8,8,8))
    draw.line([0, HERO_TOP+24, SCREEN_W, HERO_TOP+24], fill=BORDER)
    lc = state["line_code"]
    bw = draw_badge(draw, 4, HERO_TOP+5, lc,
                    line_obj.get("color","#888"), line_obj.get("text_color","#fff"),
                    shape, size=16)
    lnj = LINE_NAME_JA.get(lc, "")
    nx = 10 + bw
    if lnj:
        f_cjk = get_cjk_font(11)
        draw.text((nx, HERO_TOP+6), lnj, font=f_cjk, fill=(140, 115, 50))
        nx += text_w(draw, lnj, f_cjk) + 4
    draw.text((nx, HERO_TOP+7), line_obj.get("name","").upper(),
              font=get_font("sm"), fill=bright)
    cnt = f"{len(trains)} trains"
    cw = text_w(draw, cnt, get_font("xs"))
    draw.text((SCREEN_W - cw - 4, HERO_TOP+8), cnt, font=get_font("xs"), fill=DIM)

    row_y = HERO_TOP + 26
    row_h = 34
    f_xs  = get_font("xs")
    f_sm  = get_font("sm")
    for t in trains[:5]:
        if row_y + row_h > FOOTER_Y:
            break
        bg = (10,10,10) if trains.index(t)%2==0 else BLACK
        draw.rectangle([0, row_y, SCREEN_W, row_y+row_h], fill=bg)
        draw.rectangle([0, row_y, 3, row_y+row_h], fill=color)
        draw.line([0, row_y+row_h-1, SCREEN_W, row_y+row_h-1], fill=BORDER)

        draw.text((6, row_y+2), f"#{t.get('train_number','')}", font=f_xs, fill=DIM)

        dest_en = ("→ " + t.get("destination","")).upper()
        draw_dest(draw, 6, row_y+14, dest_en, f_xs, bright, max_w=244)

        if t.get("delay_min",0) > 0:
            ds = f"+{t['delay_min']}m"
            dw = text_w(draw, ds, f_xs)
            draw.text((SCREEN_W-dw-4, row_y+2), ds, font=f_xs, fill=ORANGE)

        from_s = t.get("from_station","").upper()[:7]
        to_s   = t.get("to_station","").upper()[:7]
        px = 4
        py = row_y + 26
        draw.text((px, py), from_s, font=f_xs, fill=(70,70,70))
        px += text_w(draw, from_s, f_xs) + 3
        draw.line([px, py+4, px+12, py+4], fill=(50,50,50))
        px += 14
        draw.ellipse([px-3, py+1, px+3, py+7], fill=color)
        px += 7
        draw.line([px, py+4, px+12, py+4], fill=(40,40,40))
        px += 14
        draw.text((px, py), to_s, font=f_xs, fill=(110,110,110))

        row_y += row_h

def draw_picker(draw):
    draw.rectangle([0, HERO_TOP, SCREEN_W, FOOTER_Y], fill=(4,4,4))
    draw.line([0, HERO_TOP+13, SCREEN_W, HERO_TOP+13], fill=BORDER)
    title = "SELECT STATION" if state["picker_type"] == "station" else "SELECT LINE"
    draw.text((4, HERO_TOP+2), title, font=get_font("xs"), fill=(60,60,60))

    results = state["picker_results"]
    scroll  = state["picker_scroll"]
    f_sm    = get_font("sm")
    f_xs    = get_font("xs")
    list_top = HERO_TOP + 14

    if state["picker_type"] == "station":
        row_h = 24
        row_y = list_top
        for item in results[scroll:scroll+8]:
            if row_y + row_h > FOOTER_Y:
                break
            bg = (12,12,12) if results.index(item)%2==0 else (8,8,8)
            draw.rectangle([0, row_y, SCREEN_W, row_y+row_h], fill=bg)
            ja = item.get("name_ja", "")
            if ja:
                f_cjk = get_cjk_font(13)
                draw.text((4, row_y+4), ja, font=f_cjk, fill=(160, 130, 60))
                jw = text_w(draw, ja, f_cjk) + 5
            else:
                jw = 0
            draw_text(draw, 4 + jw, row_y+5, item["name_en"].upper(), f_sm, WHITE, max_w=140 - jw)
            bx = 190
            for lc in item.get("lines",[])[:6]:
                lo = next((l for l in state["all_lines"] if l["code"]==lc), None)
                if lo:
                    bw = draw_badge(draw, bx, row_y+5, lc,
                                    lo["color"], lo["text_color"], lo["shape"], 13)
                    bx += bw + 2
            draw.line([0, row_y+row_h-1, SCREEN_W, row_y+row_h-1], fill=BORDER)
            row_y += row_h
    else:
        cols, col_w = 3, SCREEN_W // 3
        row_y = list_top
        row_h = 36
        for i, item in enumerate(results[scroll:scroll+12]):
            col = i % cols
            rx  = col * col_w + 3
            if col == 0 and i > 0:
                row_y += row_h
            if row_y + row_h > FOOTER_Y:
                break
            bg = (12,12,12) if i%2==0 else (8,8,8)
            draw.rectangle([rx, row_y, rx+col_w-3, row_y+row_h-2], fill=bg)
            bw = draw_badge(draw, rx+4, row_y+5, item["code"],
                            item["color"], item["text_color"], item["shape"], 18)
            short = item.get("short", item["code"])[:7]
            draw_text(draw, rx+4, row_y+26, short, f_xs, DIM, max_w=col_w-8)

FOOTER_BUTTONS = [("STN", "station"), ("LINE", "line"), ("PICK", "pick")]

def draw_exit_confirm(draw):
    draw.rectangle([0, HDR_H, SCREEN_W, FOOTER_Y], fill=(4, 4, 4))
    draw.rounded_rectangle([16, 50, 304, 190], radius=10, fill=(14, 14, 14))
    draw.rounded_rectangle([16, 50, 304, 190], radius=10, outline=(55, 55, 55))
    f_md = get_font("md"); f_sm = get_font("sm"); f_xs = get_font("xs")
    draw.text((SCREEN_W//2 - text_w(draw, "STOP DISPLAY?", f_md)//2, 62),
              "STOP DISPLAY?", font=f_md, fill=WHITE)
    draw.text((SCREEN_W//2 - text_w(draw, "hold STN or LINE 2s", f_xs)//2, 82),
              "hold STN or LINE 2s", font=f_xs, fill=(40, 40, 40))
    draw.rounded_rectangle([40, 110, 140, 150], radius=6, fill=(160, 20, 20))
    draw.text((90 - text_w(draw, "EXIT", f_md)//2, 123), "EXIT", font=f_md, fill=WHITE)
    draw.rounded_rectangle([180, 110, 280, 150], radius=6, fill=(22, 22, 22))
    draw.rounded_rectangle([180, 110, 280, 150], radius=6, outline=(55, 55, 55))
    draw.text((230 - text_w(draw, "CANCEL", f_sm)//2, 127), "CANCEL", font=f_sm, fill=DIM)

FOOTER_BW = SCREEN_W // len(FOOTER_BUTTONS)

def draw_footer(draw):
    draw.rectangle([0, FOOTER_Y, SCREEN_W, SCREEN_H], fill=(8,8,8))
    draw.line([0, FOOTER_Y, SCREEN_W, FOOTER_Y], fill=BORDER)
    if _hold_start_time > 0:
        elapsed  = time.time() - _hold_start_time
        progress = min(1.0, elapsed / 2.0)
        bar_w    = int(progress * SCREEN_W)
        draw.rectangle([0, FOOTER_Y, bar_w, FOOTER_Y + 2], fill=ORANGE)
    f = get_font("md")
    ty = FOOTER_Y + (FOOTER_H - f.size) // 2
    for i, (label, action) in enumerate(FOOTER_BUTTONS):
        bx     = i * FOOTER_BW
        active = (action == state["mode"])
        brect  = [bx + 2, FOOTER_Y + 3, bx + FOOTER_BW - 2, SCREEN_H - 3]
        if active:
            draw.rounded_rectangle(brect, radius=3, fill=(20,20,20))
            draw.rounded_rectangle(brect, radius=3, outline=(90,90,90))
            draw.text((bx + (FOOTER_BW - text_w(draw, label, f)) // 2, ty),
                      label, font=f, fill=WHITE)
        else:
            draw.rounded_rectangle(brect, radius=3, outline=(28,28,28))
            draw.text((bx + (FOOTER_BW - text_w(draw, label, f)) // 2, ty),
                      label, font=f, fill=DIM)
    if state["demo_mode"]:
        draw.text((SCREEN_W - 36, FOOTER_Y + (FOOTER_H - 10) // 2), "DEMO",
                  font=get_font("xs"), fill=(50,40,10))

# ── Touch input — reads calibrated coords from tslib ─────────────────────────
_TOUCH_KEYWORDS = ("touch", "ads", "stmpe", "ft5", "ft6", "goodix", "edt-ft", "ili", "ep0110", "eeti")

def find_touch_device():
    base = "/sys/class/input"
    try:
        for d in sorted(os.listdir(base)):
            name_file = os.path.join(base, d, "device", "name")
            if os.path.exists(name_file):
                n = open(name_file).read().strip().lower()
                if any(k in n for k in _TOUCH_KEYWORDS):
                    ev_dir = os.path.join(base, d)
                    for sub in sorted(os.listdir(ev_dir)):
                        if sub.startswith("event"):
                            dev = f"/dev/input/{sub}"
                            print(f"Touch device: {dev!r}  ({n})")
                            return dev
    except Exception:
        pass
    print("No touch device found — check /proc/bus/input/devices")
    return None

def handle_touch_events(q):
    global _hold_start_time, _hold_pos, _hold_consumed
    import tslib_input as _ts

    dev = os.environ.get("TSLIB_TSDEVICE", "")
    if not dev or not os.path.exists(dev):
        dev = find_touch_device() or ""

    handle = None
    for attempt in range(15):
        if dev and os.path.exists(dev):
            handle = _ts.open_ts(dev)
        if handle:
            break
        print(f"Touch not ready, retry {attempt+1}/15 in 3s...")
        time.sleep(3)
        if not dev:
            dev = find_touch_device() or ""

    if not handle:
        print("Touch disabled — tslib could not open device")
        print("Run:  sudo bash pi/setup_touch.sh")
        return

    print(f"tslib opened: {dev}")

    DRAG_MIN      = 10   # screen pixels (calibrated space)
    prev_pressure = 0
    start_x = start_y = 0
    last_x  = last_y  = 0

    while True:
        try:
            result = _ts.read_ts(handle)
            if result is None:
                time.sleep(0.01)
                continue
            x, y, pressure = result

            if pressure > 0:
                last_x, last_y = x, y

            if pressure > 0 and prev_pressure == 0:
                start_x, start_y = x, y
                _hold_consumed = False
                if y >= FOOTER_Y and not state["confirm_exit"]:
                    _hold_start_time = time.time()
                    _hold_pos = (x, y)
                else:
                    _hold_start_time = 0.0

            elif pressure == 0 and prev_pressure > 0:
                _hold_start_time = 0.0
                if _hold_consumed:
                    _hold_consumed = False
                else:
                    dx = last_x - start_x
                    if abs(dx) >= DRAG_MIN:
                        q.put(("scroll", -dx))
                    else:
                        q.put(("tap", start_x, start_y))

            prev_pressure = pressure

        except Exception as e:
            print(f"Touch read error: {e}")
            time.sleep(0.1)

import queue as _queue
_touch_q = _queue.Queue()

def check_hold():
    global _hold_start_time, _hold_consumed
    # Brief startup guard against FT6236 phantom events at boot
    if time.time() - _service_start_time < 5.0:
        _hold_start_time = 0.0
        return
    if _hold_start_time > 0 and not _hold_consumed:
        if time.time() - _hold_start_time >= 2.0:
            _hold_consumed = True
            _hold_start_time = 0.0
            process_long_press(*_hold_pos)

def draw_tap_indicator(draw):
    if _last_tap_pos is None:
        return
    elapsed = time.time() - _last_tap_time
    if elapsed > 0.35:
        return
    tx, ty = _last_tap_pos
    frac = min(1.0, elapsed / 0.35)
    r = int(6 + 10 * frac)
    alpha = int(200 * (1.0 - frac))
    draw.ellipse([tx - r, ty - r, tx + r, ty + r], outline=(alpha, alpha, alpha))

def process_long_press(x, y):
    if y >= FOOTER_Y:
        idx = x // FOOTER_BW
        if idx in (0, 1):   # hold STN or LINE → exit confirm
            state["confirm_exit"] = True

def process_touch(x, y):
    if state["confirm_exit"]:
        if 40 <= x <= 140 and 110 <= y <= 150:   # EXIT
            import subprocess
            subprocess.Popen(["systemctl", "stop", "train-display.service"])
            sys.exit(0)
        else:                                      # CANCEL or anywhere else
            state["confirm_exit"] = False
        return

    if y >= FOOTER_Y:
        idx = x // FOOTER_BW
        if 0 <= idx < len(FOOTER_BUTTONS):
            _, action = FOOTER_BUTTONS[idx]
            if action == "station":
                state["mode"] = "station"
                state["platform_filter"] = "ALL"
                state["plt_popup_open"] = False
                state["picker_open"] = False
            elif action == "line":
                state["picker_type"] = "line"
                state["picker_results"] = state["all_lines"]
                state["picker_scroll"] = 0
                state["picker_open"] = True
            elif action == "pick":
                state["picker_type"] = "station"
                state["picker_results"] = state["all_stations"]
                state["picker_scroll"] = 0
                state["picker_open"] = True
            threading.Thread(target=refresh_data, daemon=True).start()
        return

    if state["picker_open"]:
        list_top = HERO_TOP + 14
        row_h = 24 if state["picker_type"] == "station" else 36
        idx = (y - list_top) // row_h + state["picker_scroll"]
        results = state["picker_results"]
        if 0 <= idx < len(results):
            item = results[idx]
            state["picker_open"] = False
            if state["picker_type"] == "station":
                state["station_id"]      = item["id"]
                state["station_en"]      = item["name_en"].upper()
                state["station_ja"]      = item.get("name_ja","")
                state["mode"]            = "station"
                state["platform_filter"] = "ALL"
            else:
                state["line_code"] = item["code"]
                state["mode"]      = "line"
            threading.Thread(target=refresh_data, daemon=True).start()
        state["list_scroll"] = 0
        return

    # Platform popup: handle taps when open
    if state["plt_popup_open"]:
        px, py, pw, ph = plt_popup_rect()
        if px <= x <= px + pw and py <= y <= py + ph:
            platforms = _plt_popup_platforms()
            idx = (y - py - PLT_POPUP_PAD) // PLT_POPUP_ITEM_H
            if 0 <= idx < len(platforms):
                state["platform_filter"] = platforms[idx]
                state["list_scroll"] = 0
        state["plt_popup_open"] = False
        return

    # PLT column header tap → open popup
    if state["mode"] == "station" and HERO_BOT <= y <= HERO_BOT + COL_H and x >= 240:
        state["plt_popup_open"] = True
        return

def process_scroll(dy):
    if state["picker_open"]:
        row_h   = 24 if state["picker_type"] == "station" else 36
        visible = 8  if state["picker_type"] == "station" else 5
        delta   = -round(dy / row_h)
        limit   = max(0, len(state["picker_results"]) - visible)
        state["picker_scroll"] = max(0, min(limit, state["picker_scroll"] + delta))
    elif state["mode"] == "station":
        trains  = state["station_trains"]
        pf      = state["platform_filter"]
        visible = [t for t in trains if pf == "ALL" or str(t.get("platform","")) == pf]
        delta   = -round(dy / ROW_H)
        limit   = max(0, len(visible) - 1 - 3)
        state["list_scroll"] = max(0, min(limit, state["list_scroll"] + delta))

# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    _ensure_cjk_font()
    _load_operator_logos()
    _open_fb()

    threading.Thread(target=background_loop, daemon=True).start()
    threading.Thread(target=handle_touch_events, args=(_touch_q,), daemon=True).start()

    import atexit
    atexit.register(_cleanup)
    signal.signal(signal.SIGINT,  lambda *_: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    interval = 1.0 / FPS
    print(f"Tokyo Train Ticker → {FB_DEV}  ({SCREEN_W}x{SCREEN_H})")

    global _last_tap_pos, _last_tap_time, _service_start_time
    _service_start_time = time.time()

    while True:
        try:
            t0 = time.time()

            check_hold()

            while not _touch_q.empty():
                try:
                    event = _touch_q.get_nowait()
                    age = time.time() - _service_start_time
                    if event[0] == "tap" and age >= 5.0:
                        _last_tap_pos = (event[1], event[2])
                        _last_tap_time = time.time()
                        process_touch(event[1], event[2])
                    elif event[0] == "scroll" and age >= 5.0:
                        process_scroll(event[1])
                except Exception as e:
                    print(f"touch event error: {e}", flush=True)

            img  = Image.new("RGB", (SCREEN_W, SCREEN_H), BLACK)
            draw = ImageDraw.Draw(img)

            draw_header(draw)

            if state["confirm_exit"]:
                draw_exit_confirm(draw)
            elif state["picker_open"]:
                draw_picker(draw)
            elif state["mode"] == "station":
                draw_hero_card(draw, img)
                draw_upcoming_list(draw, HERO_BOT)
                if state["plt_popup_open"]:
                    draw_plt_popup(draw)
            else:
                draw_line_tracker(draw)

            draw_footer(draw)
            draw_tap_indicator(draw)

            flush(img)

            elapsed = time.time() - t0
            time.sleep(max(0, interval - elapsed))

        except Exception as e:
            print(f"Main loop error: {e}", flush=True)
            time.sleep(0.5)


if __name__ == "__main__":
    main()
