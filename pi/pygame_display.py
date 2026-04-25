"""
Pygame renderer for Adafruit PiTFT 2.8" (320x240) on Raspberry Pi Zero.
Connects to the local FastAPI backend and renders directly to the framebuffer.

Usage:
  On Pi:  SDL_FBDEV=/dev/fb1 SDL_VIDEODRIVER=fbcon python3 pygame_display.py
  On dev: python3 pygame_display.py  (opens a 320x240 window)
"""
import asyncio
import json
import os
import sys
import time
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

import pygame
import httpx
import websockets

# ── Config ──────────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 320, 240
API_BASE = os.getenv("API_BASE", "http://localhost:8000")
WS_URL   = os.getenv("WS_URL",  "ws://localhost:8000/ws")
JST = timezone(timedelta(hours=9))
IS_PI = os.path.exists("/dev/fb1")

# Colors
C_BG      = (8,   8,   8)
C_HEADER  = (13,  13,  13)
C_BORDER  = (26,  26,  26)
C_DIM     = (60,  60,  60)
C_TEXT    = (220, 220, 220)
C_YELLOW  = (255, 215, 0)
C_GREEN   = (154, 205, 50)
C_ORANGE  = (255, 107, 53)

# ── Fonts (will be loaded after pygame.init) ─────────────────────────────────
fonts: dict = {}

def load_fonts():
    pygame.font.init()
    mono = pygame.font.match_font("sharetechmono,couriernew,courier,monospace")
    fonts["sm"]  = pygame.font.Font(mono, 9)
    fonts["md"]  = pygame.font.Font(mono, 11)
    fonts["lg"]  = pygame.font.Font(mono, 13)
    fonts["xl"]  = pygame.font.Font(mono, 16)

# ── State ─────────────────────────────────────────────────────────────────────
state = {
    "mode": "station",           # "station" | "line"
    "station_id": "shibuya",
    "station_en": "SHIBUYA",
    "station_ja": "渋谷",
    "line_code": "JY",
    "station_trains": [],
    "line_trains": [],
    "all_stations": [],
    "all_lines": [],
    "demo_mode": True,
    "connected": False,
    "last_update": 0,
    "platform_filter": "ALL",   # "ALL" or specific platform label
    "picker_open": False,
    "picker_type": None,        # "station" | "line" | "platform"
    "picker_results": [],
    "picker_scroll": 0,
    "picker_query": "",
}

# ── REST data fetch (runs in background thread) ───────────────────────────────

def fetch_blocking(url: str) -> Optional[dict | list]:
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.get(url)
            r.raise_for_status()
            return r.json()
    except Exception:
        return None

def refresh_data():
    if state["mode"] == "station":
        data = fetch_blocking(f"{API_BASE}/api/trains/station/{state['station_id']}")
        if data is not None:
            state["station_trains"] = data
            state["last_update"] = time.time()
    else:
        data = fetch_blocking(f"{API_BASE}/api/trains/line/{state['line_code']}")
        if data is not None:
            state["line_trains"] = data
            state["last_update"] = time.time()

def load_meta():
    lines = fetch_blocking(f"{API_BASE}/api/lines")
    if lines: state["all_lines"] = lines
    stations = fetch_blocking(f"{API_BASE}/api/stations")
    if stations: state["all_stations"] = stations
    status = fetch_blocking(f"{API_BASE}/api/status")
    if status: state["demo_mode"] = status.get("demo_mode", True)
    state["connected"] = bool(lines)

def background_loop():
    load_meta()
    while True:
        refresh_data()
        time.sleep(15)

# ── Drawing helpers ────────────────────────────────────────────────────────────

def hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def brighten(rgb: tuple, factor: float = 1.4, add: int = 40) -> tuple:
    return tuple(min(255, int(c * factor + add)) for c in rgb)

def draw_badge(surf, x, y, code: str, color: str, text_color: str, shape: str, font):
    bg = hex_to_rgb(color)
    fg = hex_to_rgb(text_color)
    tw, th = font.size(code)
    w = max(tw + 4, 14 if shape == "circle" else 18)
    h = 12
    rect = pygame.Rect(x, y, w, h)
    if shape == "circle":
        cx, cy = rect.centerx, rect.centery
        r = h // 2
        pygame.draw.circle(surf, bg, (cx, cy), r)
    elif shape == "square":
        pygame.draw.rect(surf, bg, rect, border_radius=1)
    else:
        pygame.draw.rect(surf, bg, rect, border_radius=3)
    txt = font.render(code, True, fg)
    surf.blit(txt, (rect.centerx - tw // 2, rect.centery - th // 2))
    return w

def draw_text(surf, text, x, y, font, color=C_TEXT, max_w=None):
    if max_w:
        while font.size(text)[0] > max_w and len(text) > 1:
            text = text[:-2] + "…"
    rendered = font.render(str(text), True, color)
    surf.blit(rendered, (x, y))
    return rendered.get_width()

# ── Screen sections ────────────────────────────────────────────────────────────

def draw_header(surf):
    pygame.draw.rect(surf, C_HEADER, (0, 0, SCREEN_W, 22))
    pygame.draw.line(surf, C_BORDER, (0, 22), (SCREEN_W, 22))

    # Station name
    draw_text(surf, state["station_ja"], 4, 5, fonts["sm"], (100, 100, 100))
    en_x = 4 + fonts["sm"].size(state["station_ja"])[0] + 4
    draw_text(surf, state["station_en"], en_x, 4, fonts["md"], C_TEXT, max_w=200)

    # Clock (JST)
    now = datetime.now(JST)
    clock_str = now.strftime("%H:%M:%S")
    cw = fonts["sm"].size(clock_str)[0]
    draw_text(surf, clock_str, SCREEN_W - cw - 4, 6, fonts["sm"], C_DIM)

def draw_line_badges(surf, y=22):
    pygame.draw.rect(surf, (6, 6, 6), (0, y, SCREEN_W, 18))
    pygame.draw.line(surf, C_BORDER, (0, y + 18), (SCREEN_W, y + 18))
    station = next((s for s in state["all_stations"] if s["id"] == state["station_id"]), None)
    if not station:
        return
    x = 4
    for lc in station.get("lines", []):
        line = next((l for l in state["all_lines"] if l["code"] == lc), None)
        if not line:
            continue
        w = draw_badge(surf, x, y + 3, lc, line["color"], line["text_color"], line["shape"], fonts["sm"])
        x += w + 3
        if x > SCREEN_W - 20:
            break

def _get_platforms(trains: list) -> list:
    seen = set()
    for t in trains:
        p = str(t.get("platform") or "").strip()
        if p and p != "–":
            seen.add(p)
    try:
        return sorted(seen, key=lambda x: (float(x), x))
    except Exception:
        return sorted(seen)


def draw_platform_strip(surf, trains, y=40):
    platforms = _get_platforms(trains)
    if len(platforms) <= 1:
        return y  # nothing to show

    pygame.draw.rect(surf, (6, 6, 6), (0, y, SCREEN_W, 16))
    pygame.draw.line(surf, C_BORDER, (0, y + 16), (SCREEN_W, y + 16))
    draw_text(surf, "PLT", 4, y + 4, fonts["sm"], (60, 60, 60))

    x = 28
    pf = state["platform_filter"]
    for label in ["ALL"] + platforms:
        active = (label == pf)
        tw, th = fonts["sm"].size(label)
        bw = tw + 6
        brect = pygame.Rect(x, y + 2, bw, 12)
        bg = (26, 26, 26) if active else (8, 8, 8)
        border = (100, 100, 100) if active else (36, 36, 36)
        fg = C_TEXT if active else (80, 80, 80)
        pygame.draw.rect(surf, bg, brect, border_radius=2)
        pygame.draw.rect(surf, border, brect, 1, border_radius=2)
        draw_text(surf, label, brect.centerx - tw // 2, brect.centery - th // 2, fonts["sm"], fg)
        x += bw + 3
        if x > SCREEN_W - 10:
            break

    return y + 16


def draw_station_board(surf):
    draw_line_badges(surf, y=22)

    trains = state["station_trains"]

    # Platform filter strip (returns next y position)
    content_y = draw_platform_strip(surf, trains, y=40)

    # Apply platform filter
    pf = state["platform_filter"]
    visible_trains = [t for t in trains if pf == "ALL" or str(t.get("platform", "")) == pf]

    # Column headers
    hdr_y = content_y
    pygame.draw.rect(surf, (14, 14, 14), (0, hdr_y, SCREEN_W, 14))
    draw_text(surf, "LINE", 4, hdr_y + 2, fonts["sm"], C_DIM)
    draw_text(surf, "DESTINATION", 34, hdr_y + 2, fonts["sm"], C_DIM)
    draw_text(surf, "PLT", 246, hdr_y + 2, fonts["sm"], C_DIM)
    draw_text(surf, "MIN", 291, hdr_y + 2, fonts["sm"], C_DIM)
    pygame.draw.line(surf, C_BORDER, (0, hdr_y + 14), (SCREEN_W, hdr_y + 14))

    row_y = hdr_y + 15
    row_h = 18

    if not visible_trains:
        msg = f"No trains on platform {pf}" if pf != "ALL" else "No service data"
        draw_text(surf, msg, SCREEN_W // 2 - 50, row_y + 20, fonts["sm"], C_DIM)
        return

    for i, t in enumerate(visible_trains):
        if row_y + row_h > SCREEN_H - 20:
            break
        line = next((l for l in state["all_lines"] if l["code"] == t["line_code"]), None)
        bg = (11, 11, 11) if i % 2 == 0 else C_BG
        pygame.draw.rect(surf, bg, (0, row_y, SCREEN_W, row_h))

        if line:
            draw_badge(surf, 3, row_y + 3, t["line_code"], t["color"], t["text_color"], t.get("shape", "rect"), fonts["sm"])

        dest = (t.get("destination") or "").upper()[:11]
        color = brighten(hex_to_rgb(t.get("color", "#ffffff")))
        draw_text(surf, dest, 34, row_y + 4, fonts["sm"], color, max_w=200)

        if t.get("delay_min", 0) > 0:
            pygame.draw.circle(surf, (238, 136, 51), (240, row_y + 9), 3)

        plat = str(t.get("platform") or "–")
        draw_text(surf, plat, 253, row_y + 4, fonts["sm"], C_DIM)

        eta = t.get("eta_min", 0)
        if eta <= 1:
            eta_color = C_ORANGE if int(time.time() * 2) % 2 == 0 else (100, 50, 20)
            eta_str = "NOW"
        elif eta <= 3:
            eta_color = C_YELLOW
            eta_str = str(eta)
        else:
            eta_color = C_GREEN
            eta_str = str(eta)
        ew = fonts["md"].size(eta_str)[0]
        draw_text(surf, eta_str, SCREEN_W - ew - 4, row_y + 3, fonts["md"], eta_color)

        pygame.draw.line(surf, C_BORDER, (0, row_y + row_h - 1), (SCREEN_W, row_y + row_h - 1))
        row_y += row_h

def draw_line_tracker(surf):
    # Line name header
    pygame.draw.rect(surf, C_HEADER, (0, 22, SCREEN_W, 20))
    pygame.draw.line(surf, C_BORDER, (0, 42), (SCREEN_W, 42))
    line = next((l for l in state["all_lines"] if l["code"] == state["line_code"]), None)
    if line:
        x = 6
        w = draw_badge(surf, x, 27, state["line_code"], line["color"], line["text_color"], line["shape"], fonts["sm"])
        x += w + 6
        color = brighten(hex_to_rgb(line["color"]))
        draw_text(surf, line["name"].upper(), x, 27, fonts["sm"], color, max_w=180)
        count_str = f"{len(state['line_trains'])} TRAINS"
        cw = fonts["sm"].size(count_str)[0]
        draw_text(surf, count_str, SCREEN_W - cw - 4, 28, fonts["sm"], C_DIM)

    trains = state["line_trains"]
    row_y = 44
    row_h = 32
    for t in trains[:6]:
        if row_y + row_h > SCREEN_H - 20:
            break
        pygame.draw.rect(surf, (10, 10, 10) if (row_y // row_h) % 2 == 0 else C_BG, (0, row_y, SCREEN_W, row_h))
        pygame.draw.line(surf, C_BORDER, (0, row_y + row_h - 1), (SCREEN_W, row_y + row_h - 1))

        # Train number
        draw_text(surf, f"#{t.get('train_number','')}", 4, row_y + 2, fonts["sm"], C_DIM)

        # Destination
        dest = (t.get("destination") or "").upper()
        lcolor = brighten(hex_to_rgb(t.get("color", "#ffffff")))
        draw_text(surf, f"→ {dest}", 4, row_y + 13, fonts["sm"], lcolor, max_w=SCREEN_W - 60)

        # Delay
        if t.get("delay_min", 0) > 0:
            ds = f"+{t['delay_min']}min"
            dw = fonts["sm"].size(ds)[0]
            draw_text(surf, ds, SCREEN_W - dw - 4, row_y + 2, fonts["sm"], C_ORANGE)

        # Progress bar: from → ● → to → ··· dest
        from_st = (t.get("from_station") or "").upper()[:7]
        to_st   = (t.get("to_station") or "").upper()[:7]
        line_rgb = hex_to_rgb(t.get("color", "#555555"))
        bar_y = row_y + 23
        fw = fonts["sm"].size(from_st)[0]
        draw_text(surf, from_st, 4, bar_y, fonts["sm"], (80, 80, 80))
        x = 4 + fw + 3
        pygame.draw.line(surf, (50, 50, 50), (x, bar_y + 4), (x + 15, bar_y + 4))
        x += 17
        pygame.draw.circle(surf, line_rgb, (x, bar_y + 4), 4)
        x += 7
        pygame.draw.line(surf, (40, 40, 40), (x, bar_y + 4), (x + 15, bar_y + 4))
        x += 17
        draw_text(surf, to_st, x, bar_y, fonts["sm"], (130, 130, 130))

        row_y += row_h

def draw_footer(surf):
    y = SCREEN_H - 20
    pygame.draw.rect(surf, (10, 10, 10), (0, y, SCREEN_W, 20))
    pygame.draw.line(surf, C_BORDER, (0, y), (SCREEN_W, y))

    buttons = [
        ("STATION", "station"),
        ("LINE", "line"),
        ("PICK", "pick"),
    ]
    bw, bh = 64, 14
    x = 4
    for label, action in buttons:
        active = (action == state["mode"]) or (action == "pick")
        bg = (20, 20, 20) if active else C_BG
        fg = C_TEXT if active else C_DIM
        border = (80, 80, 80) if active else C_BORDER
        brect = pygame.Rect(x, y + 3, bw, bh)
        pygame.draw.rect(surf, bg, brect, border_radius=2)
        pygame.draw.rect(surf, border, brect, 1, border_radius=2)
        tw = fonts["sm"].size(label)[0]
        draw_text(surf, label, brect.centerx - tw // 2, brect.centery - fonts["sm"].get_height() // 2, fonts["sm"], fg)
        x += bw + 4

    if state["demo_mode"]:
        draw_text(surf, "DEMO", SCREEN_W - 35, y + 5, fonts["sm"], (80, 80, 40))

def draw_picker(surf):
    # Semi-opaque overlay
    overlay = pygame.Surface((SCREEN_W, SCREEN_H - 40), pygame.SRCALPHA)
    overlay.fill((8, 8, 8, 245))
    surf.blit(overlay, (0, 22))

    pygame.draw.line(surf, C_BORDER, (0, 32), (SCREEN_W, 32))
    title = "SELECT STATION" if state["picker_type"] == "station" else "SELECT LINE"
    draw_text(surf, title, 4, 24, fonts["sm"], C_DIM)

    results = state["picker_results"]
    row_y = 42
    row_h = 18 if state["picker_type"] == "station" else 30

    for i, item in enumerate(results[state["picker_scroll"]:state["picker_scroll"] + 10]):
        if row_y + row_h > SCREEN_H - 20:
            break
        bg = (20, 20, 20) if i % 2 == 0 else (12, 12, 12)
        pygame.draw.rect(surf, bg, (0, row_y, SCREEN_W, row_h))
        if state["picker_type"] == "station":
            draw_text(surf, item["name_en"].upper(), 4, row_y + 4, fonts["sm"], C_TEXT, max_w=160)
            draw_text(surf, item["name_ja"], 4, row_y + row_h - 11, fonts["sm"], (80, 80, 80))
            bx = 190
            for lc in item.get("lines", [])[:5]:
                l = next((x for x in state["all_lines"] if x["code"] == lc), None)
                if l:
                    w = draw_badge(surf, bx, row_y + 3, lc, l["color"], l["text_color"], l["shape"], fonts["sm"])
                    bx += w + 2
        else:
            l = item
            draw_badge(surf, 4, row_y + 7, l["code"], l["color"], l["text_color"], l["shape"], fonts["md"])
            draw_text(surf, l["name"].upper(), 28, row_y + 8, fonts["sm"], brighten(hex_to_rgb(l["color"])), max_w=250)

        pygame.draw.line(surf, C_BORDER, (0, row_y + row_h - 1), (SCREEN_W, row_y + row_h - 1))
        row_y += row_h

# ── Touch / keyboard input handling ─────────────────────────────────────────

def handle_touch(pos, surf_size):
    x, y = pos
    footer_y = SCREEN_H - 20
    if y >= footer_y:
        bw = 64
        btn_x = 4
        for action in ["station", "line", "pick"]:
            if btn_x <= x <= btn_x + bw:
                if action == "station":
                    state["mode"] = "station"
                    state["platform_filter"] = "ALL"
                    state["picker_open"] = False
                    threading.Thread(target=refresh_data, daemon=True).start()
                elif action == "line":
                    open_picker("line")
                elif action == "pick":
                    open_picker("station")
                return
            btn_x += bw + 4
        return

    # Platform strip tap (y 40-56 when strip is visible)
    if state["mode"] == "station" and not state["picker_open"]:
        trains = state["station_trains"]
        platforms = _get_platforms(trains)
        if len(platforms) > 1 and 40 <= y <= 56:
            all_labels = ["ALL"] + platforms
            # Reconstruct button x positions to find which was tapped
            cx = 28
            for label in all_labels:
                try:
                    tw = pygame.font.Font(None, 9).size(label)[0] + 6
                except Exception:
                    tw = len(label) * 6 + 6
                if cx <= x <= cx + tw:
                    state["platform_filter"] = label
                    return
                cx += tw + 3
            return

    if state["picker_open"]:
        row_h = 18 if state["picker_type"] == "station" else 30
        idx = (y - 42) // row_h + state["picker_scroll"]
        if 0 <= idx < len(state["picker_results"]):
            item = state["picker_results"][idx]
            state["picker_open"] = False
            if state["picker_type"] == "station":
                state["station_id"] = item["id"]
                state["station_en"] = item["name_en"].upper()
                state["station_ja"] = item.get("name_ja", "")
                state["mode"] = "station"
                state["platform_filter"] = "ALL"
            else:
                state["line_code"] = item["code"]
                state["mode"] = "line"
            threading.Thread(target=refresh_data, daemon=True).start()

def open_picker(picker_type):
    state["picker_type"] = picker_type
    state["picker_open"] = True
    state["picker_scroll"] = 0
    if picker_type == "station":
        state["picker_results"] = state["all_stations"]
    else:
        state["picker_results"] = state["all_lines"]

# ── Main loop ────────────────────────────────────────────────────────────────

def main():
    if IS_PI:
        os.environ.setdefault("SDL_FBDEV", "/dev/fb1")
        os.environ.setdefault("SDL_VIDEODRIVER", "fbcon")
        os.environ.setdefault("SDL_NOMOUSE", "1")

    pygame.init()
    load_fonts()

    flags = 0 if IS_PI else 0
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), flags)
    pygame.display.set_caption("Tokyo Train Ticker")
    pygame.mouse.set_visible(not IS_PI)

    clock = pygame.time.Clock()

    # Start background data thread
    bg = threading.Thread(target=background_loop, daemon=True)
    bg.start()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q or event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_s:
                    state["mode"] = "station"
                    state["picker_open"] = False
                elif event.key == pygame.K_l:
                    open_picker("line")
                elif event.key == pygame.K_p:
                    open_picker("station")
                elif event.key == pygame.K_f and state["mode"] == "station":
                    # Cycle platform filter
                    trains = state["station_trains"]
                    plats = ["ALL"] + _get_platforms(trains)
                    cur = state["platform_filter"]
                    idx = plats.index(cur) if cur in plats else 0
                    state["platform_filter"] = plats[(idx + 1) % len(plats)]
                elif event.key == pygame.K_UP and state["picker_open"]:
                    state["picker_scroll"] = max(0, state["picker_scroll"] - 1)
                elif event.key == pygame.K_DOWN and state["picker_open"]:
                    state["picker_scroll"] = min(
                        max(0, len(state["picker_results"]) - 1),
                        state["picker_scroll"] + 1
                    )
            elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
                pos = event.pos if event.type == pygame.MOUSEBUTTONDOWN else (
                    int(event.x * SCREEN_W), int(event.y * SCREEN_H)
                )
                handle_touch(pos, (SCREEN_W, SCREEN_H))

        # Draw
        screen.fill(C_BG)
        draw_header(screen)

        if state["picker_open"]:
            draw_picker(screen)
        elif state["mode"] == "station":
            draw_station_board(screen)
        else:
            draw_line_tracker(screen)

        draw_footer(screen)

        if not state["connected"]:
            msg = "Connecting to backend…"
            mw = fonts["sm"].size(msg)[0]
            draw_text(screen, msg, SCREEN_W // 2 - mw // 2, SCREEN_H // 2, fonts["sm"], C_DIM)

        pygame.display.flip()
        clock.tick(10)  # 10 FPS is plenty for train info

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
