"""
Tokyo Train Ticker — framebuffer display for Adafruit PiTFT 2.8" (320x240)
Uses Pillow + direct /dev/fb0 writes. No SDL/X11/Wayland needed.

Run: sudo python3 pi/pygame_display.py
"""
import os
import sys
import time
import threading
import signal
import struct

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
API_BASE  = os.getenv("API_BASE", "http://localhost:8000")
FB_DEV    = os.getenv("FB_DEV",   "/dev/fb0")
FPS       = 8

# ── Layout constants ──────────────────────────────────────────────────────────
HDR_H    = 22          # header height
HERO_TOP = HDR_H       # hero card top y
HERO_BOT = HERO_TOP + 88   # hero card bottom y (110)
FOOTER_H = 32          # footer height
FOOTER_Y = SCREEN_H - FOOTER_H   # footer top y (208)
STRIP_H  = 24          # platform strip height
COL_H    = 15          # column header height
ROW_H    = 20          # train list row height

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
        sizes = {"xs": 10, "sm": 12, "md": 14, "lg": 18, "xl": 24, "hero": 30}
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
    "picker_open":    False,
    "picker_type":    None,
    "picker_results": [],
    "picker_scroll":  0,
    "list_scroll":    0,   # upcoming train list scroll offset
}

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

def draw_hero_card(draw):
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

    badge_size = 68
    bx = (100 - badge_size) // 2
    by = HERO_TOP + (88 - badge_size) // 2
    code   = train["line_code"]
    rgb_bg = color
    rgb_fg = hex_to_rgb(train.get("text_color", "#000000"))
    brect  = [bx, by, bx + badge_size, by + badge_size]
    if shape == "circle":
        draw.ellipse(brect, fill=rgb_bg)
    elif shape == "square":
        draw.rounded_rectangle(brect, radius=4, fill=rgb_bg)
    else:
        draw.rounded_rectangle(brect, radius=10, fill=rgb_bg)
    f_big = get_font("xl")
    tw = text_w(draw, code, f_big)
    draw.text((bx + (badge_size - tw)//2, by + (badge_size - f_big.size)//2),
              code, font=f_big, fill=rgb_fg)

    rx = 104
    line_obj  = next((l for l in state["all_lines"] if l["code"] == code), {})
    line_name = line_obj.get("name", code)

    # Car formation diagram — right side of line-name row
    n_cars = CARS.get(code, 8)
    car_avail = SCREEN_W - 4 - 218   # x=218 to x=316 = 98px
    car_w = min(14, max(5, (car_avail - (n_cars - 1) * 2) // n_cars))
    car_h = 9
    car_gap = 2
    total_car_w = n_cars * (car_w + car_gap) - car_gap
    car_x = 218 + max(0, (car_avail - total_car_w) // 2)
    car_y = HERO_TOP + 4
    for ci in range(n_cars):
        cx = car_x + ci * (car_w + car_gap)
        fill = color if ci < n_cars - 1 else brighten(color, f=0.8, add=0)
        draw.rectangle([cx, car_y, cx + car_w, car_y + car_h], fill=fill)
    f_xs = get_font("xs")
    nc_label = f"{n_cars}c"
    draw.text((car_x + total_car_w + 3, car_y), nc_label, font=f_xs, fill=(50, 50, 50))

    draw_text(draw, rx, HERO_TOP + 4, line_name.upper(), f_xs, DIM, max_w=110)

    dest = ("→ " + train.get("destination", "")).upper()
    draw_text(draw, rx, HERO_TOP + 16, dest, get_font("md"), bright, max_w=210)

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

def draw_platform_strip(draw) -> int:
    """Returns y-bottom of strip (used as top_y for upcoming list)."""
    trains = state["station_trains"]
    seen = set()
    for t in trains:
        p = str(t.get("platform","")).strip()
        if p and p != "–":
            seen.add(p)
    platforms = sorted(seen, key=lambda v: (float(v) if v.replace(".","").isdigit() else 999, v))

    if len(platforms) <= 1:
        return HERO_BOT

    y = HERO_BOT
    draw.rectangle([0, y, SCREEN_W, y + STRIP_H], fill=(6, 6, 6))
    draw.line([0, y + STRIP_H, SCREEN_W, y + STRIP_H], fill=BORDER)

    f  = get_font("sm")
    draw.text((4, y + 6), "PLT", font=f, fill=(40, 40, 40))
    x  = 36
    pf = state["platform_filter"]
    for label in ["ALL"] + platforms:
        active = (label == pf)
        tw     = text_w(draw, label, f) + 10
        brect  = [x, y+3, x+tw, y+STRIP_H-3]
        if active:
            draw.rounded_rectangle(brect, radius=3, fill=(25, 25, 25))
            draw.rounded_rectangle(brect, radius=3, outline=(100, 100, 100))
            draw.text((x+5, y+6), label, font=f, fill=WHITE)
        else:
            draw.rounded_rectangle(brect, radius=3, outline=(30, 30, 30))
            draw.text((x+5, y+6), label, font=f, fill=DIM)
        x += tw + 5
        if x > SCREEN_W - 14:
            break
    return y + STRIP_H

def draw_upcoming_list(draw, top_y):
    trains  = state["station_trains"]
    pf      = state["platform_filter"]
    visible = [t for t in trains if pf == "ALL" or str(t.get("platform","")) == pf]
    scroll  = state["list_scroll"]
    upcoming = visible[1:][scroll:]  # skip hero train, then apply scroll

    h_y = top_y
    draw.rectangle([0, h_y, SCREEN_W, h_y + COL_H], fill=(10, 10, 10))
    draw.line([0, h_y + COL_H, SCREEN_W, h_y + COL_H], fill=BORDER)
    f_hdr = get_font("xs")
    draw.text((4,   h_y+3), "LINE",        font=f_hdr, fill=(45,45,45))
    draw.text((36,  h_y+3), "NEXT TRAINS", font=f_hdr, fill=(45,45,45))
    draw.text((248, h_y+3), "PLT",         font=f_hdr, fill=(45,45,45))
    draw.text((289, h_y+3), "MIN",         font=f_hdr, fill=(45,45,45))

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
            draw.rectangle([0, row_y, SCREEN_W, row_y+12], fill=BLACK)
            draw.text((4, row_y+1), lbl, font=f_xs, fill=(35,35,35))
            lx = 4 + text_w(draw, lbl, f_xs) + 4
            draw.line([lx, row_y+6, SCREEN_W-4, row_y+6], fill=(20,20,20))
            last_bucket = bidx
            row_y += 12
            if row_y >= FOOTER_Y:
                break

        bg = (10,10,10) if (upcoming.index(t) % 2 == 0) else BLACK
        draw.rectangle([0, row_y, SCREEN_W, row_y+ROW_H], fill=bg)

        color  = hex_to_rgb(t.get("color", "#888"))
        bright = brighten(color)
        code   = t["line_code"]
        plat   = str(t.get("platform") or "–")

        # Colored left border for line identity
        draw.rectangle([0, row_y, 3, row_y + ROW_H], fill=color)

        draw_badge(draw, 5, row_y+3, code, t.get("color","#888"),
                   t.get("text_color","#fff"), t.get("shape","rect"), size=14)

        dest = t.get("destination","").upper()[:11]
        draw_text(draw, 38, row_y+4, dest, f_xs, bright, max_w=196)

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
    bw = draw_badge(draw, 4, HERO_TOP+5, state["line_code"],
                    line_obj.get("color","#888"), line_obj.get("text_color","#fff"),
                    shape, size=16)
    draw.text((10 + bw, HERO_TOP+7), line_obj.get("name","").upper(),
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
        draw.line([0, row_y+row_h-1, SCREEN_W, row_y+row_h-1], fill=BORDER)

        draw.text((4, row_y+2), f"#{t.get('train_number','')}", font=f_xs, fill=DIM)

        dest = ("→ " + t.get("destination","")).upper()
        draw_text(draw, 4, row_y+14, dest, f_xs, bright, max_w=250)

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
            draw_text(draw, 4, row_y+3, item["name_en"].upper(), f_sm, WHITE, max_w=140)
            draw.text((4, row_y+14), item.get("name_ja",""), font=f_xs, fill=(70,70,70))
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
FOOTER_BW = SCREEN_W // len(FOOTER_BUTTONS)

def draw_footer(draw):
    draw.rectangle([0, FOOTER_Y, SCREEN_W, SCREEN_H], fill=(8,8,8))
    draw.line([0, FOOTER_Y, SCREEN_W, FOOTER_Y], fill=BORDER)
    f = get_font("md")
    ty = FOOTER_Y + (FOOTER_H - f.size) // 2  # vertically centered
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

# ── Touch input ───────────────────────────────────────────────────────────────
_EV_FMT  = "llHHi"
_EV_SIZE = struct.calcsize(_EV_FMT)

_TOUCH_KEYWORDS = ("touch", "ads", "stmpe", "ft5", "ft6", "goodix", "edt-ft", "ili")

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

# For this hardware (FT6236 on Adafruit PiTFT 2.8" landscape):
#   raw_x = vertical axis, range 0–239 (0=bottom, 239=top)
#   raw_y = horizontal axis, range 0–319 (0=left, 319=right)
# Transform: screen_x = raw_y, screen_y = 239 - raw_x
_touch_x_max = SCREEN_H - 1   # 239 — raw_x is the vertical axis
_touch_y_max = SCREEN_W - 1   # 319 — raw_y is the horizontal axis

def _map_touch(rx, ry, xmax, ymax):
    # Swap axes, invert screen_y
    sx = round(ry * (SCREEN_W - 1) / ymax)
    sy = (SCREEN_H - 1) - round(rx * (SCREEN_H - 1) / xmax)
    return sx, sy

def _read_abs_max(event_dev, axis_code):
    try:
        name = os.path.basename(event_dev)
        line = open(f"/sys/class/input/{name}/device/abs{axis_code:02x}").read().strip().split()
        return int(line[2])
    except Exception:
        return None

def handle_touch_events(q):
    global _touch_x_max, _touch_y_max
    import select

    dev = None
    for attempt in range(15):
        dev = find_touch_device()
        if dev:
            break
        print(f"Touch not ready, retry {attempt+1}/15 in 3s...")
        time.sleep(3)
    if not dev:
        print("Touch disabled — device never appeared")
        return

    try:
        f = open(dev, "rb")
    except Exception as e:
        print(f"Cannot open touch device {dev}: {e}")
        return

    mx = _read_abs_max(dev, 0)
    my = _read_abs_max(dev, 1)
    if mx and mx > 0: _touch_x_max = mx
    if my and my > 0: _touch_y_max = my
    print(f"Touch axis range: x=0-{_touch_x_max}  y=0-{_touch_y_max}  event_size={_EV_SIZE}")

    EV_ABS, EV_KEY = 3, 1
    ABS_X,  ABS_Y  = 0, 1
    ABS_MT_POSITION_X, ABS_MT_POSITION_Y = 53, 54
    BTN_TOUCH = 330
    DRAG_MIN  = 14   # raw_x units before treated as scroll, not tap

    x = y = 0
    start_x = start_y = 0
    finger_down = False

    while True:
        try:
            r, _, _ = select.select([f], [], [], 1.0)
            if not r:
                continue
            raw = f.read(_EV_SIZE)
            if len(raw) < _EV_SIZE:
                continue
            _, _, etype, ecode, evalue = struct.unpack(_EV_FMT, raw)

            if etype == EV_ABS:
                if ecode in (ABS_X, ABS_MT_POSITION_X):
                    x = evalue
                elif ecode in (ABS_Y, ABS_MT_POSITION_Y):
                    y = evalue

            elif etype == EV_KEY and ecode == BTN_TOUCH:
                if evalue:                       # finger down
                    finger_down = True
                    start_x, start_y = x, y     # record contact position
                elif finger_down:               # finger up
                    finger_down = False
                    dx = x - start_x            # raw_x delta = vertical screen movement
                    if abs(dx) >= DRAG_MIN:
                        # screen_y = (SCREEN_H-1) - raw_x → d(screen_y) = -dx
                        q.put(("scroll", -dx))
                    else:
                        sx, sy = _map_touch(start_x, start_y,
                                            _touch_x_max, _touch_y_max)
                        q.put(("tap", sx, sy))

        except Exception as e:
            print(f"Touch read error: {e}")
            time.sleep(0.1)

import queue as _queue
_touch_q = _queue.Queue()

def process_touch(x, y):
    if y >= FOOTER_Y:
        idx = x // FOOTER_BW
        if 0 <= idx < len(FOOTER_BUTTONS):
            _, action = FOOTER_BUTTONS[idx]
            if action == "station":
                state["mode"] = "station"
                state["platform_filter"] = "ALL"
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

    # Platform strip — full strip height
    if state["mode"] == "station" and HERO_BOT <= y <= HERO_BOT + STRIP_H:
        trains = state["station_trains"]
        seen = set(str(t.get("platform","")).strip() for t in trains
                   if t.get("platform") and t.get("platform") != "–")
        platforms = ["ALL"] + sorted(seen, key=lambda v: (float(v) if v.replace(".","").isdigit() else 999, v))
        cx = 34
        f_tmp = get_font("xs")
        img_tmp = Image.new("RGB", (1, 1))
        d_tmp   = ImageDraw.Draw(img_tmp)
        for lbl in platforms:
            tw = text_w(d_tmp, lbl, f_tmp) + 8
            if x <= cx + tw:
                state["platform_filter"] = lbl
                return
            cx += tw + 4

def process_scroll(dy):
    """dy: screen pixels dragged (positive=down, negative=up)."""
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
        limit   = max(0, len(visible) - 1 - 3)   # -1 for hero, ~3 visible rows
        state["list_scroll"] = max(0, min(limit, state["list_scroll"] + delta))

# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    _ensure_cjk_font()
    _open_fb()

    threading.Thread(target=background_loop, daemon=True).start()
    threading.Thread(target=handle_touch_events, args=(_touch_q,), daemon=True).start()

    signal.signal(signal.SIGINT,  lambda *_: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    interval = 1.0 / FPS
    print(f"Tokyo Train Ticker running → {FB_DEV}  ({SCREEN_W}x{SCREEN_H})")

    while True:
        t0 = time.time()

        while not _touch_q.empty():
            try:
                event = _touch_q.get_nowait()
                if event[0] == "tap":
                    process_touch(event[1], event[2])
                elif event[0] == "scroll":
                    process_scroll(event[1])
            except Exception as e:
                print(f"touch event error: {e}")

        img  = Image.new("RGB", (SCREEN_W, SCREEN_H), BLACK)
        draw = ImageDraw.Draw(img)

        draw_header(draw)

        if state["picker_open"]:
            draw_picker(draw)
        elif state["mode"] == "station":
            draw_hero_card(draw)
            plt_bottom = draw_platform_strip(draw)
            draw_upcoming_list(draw, plt_bottom)
        else:
            draw_line_tracker(draw)

        draw_footer(draw)

        flush(img)

        elapsed = time.time() - t0
        time.sleep(max(0, interval - elapsed))


if __name__ == "__main__":
    main()
