"""
ODPT API client with demo-mode fallback.
Real data: https://developer.odpt.org/ (free registration, get API key)
Demo mode: generates realistic simulated train data when no key is configured.
"""
import asyncio
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx

from line_data import LINES, STATIONS

ODPT_BASE = "https://api.odpt.org/api/4"
JST = timezone(timedelta(hours=9))

# Typical headways in minutes per line (peak / off-peak)
HEADWAYS = {
    "JY": (3, 4),   "JC": (5, 10),  "JB": (4, 6),   "JK": (3, 4),
    "JA": (4, 8),   "JH": (10, 15), "JU": (15, 20),  "JE": (12, 15),
    "JO": (15, 20), "G":  (3, 5),   "M":  (4, 6),    "H":  (3, 5),
    "T":  (5, 8),   "C":  (5, 8),   "Y":  (5, 8),    "Z":  (4, 6),
    "N":  (5, 8),   "F":  (4, 6),   "A":  (5, 8),    "I":  (5, 8),
    "S":  (8, 12),  "E":  (5, 8),   "TY": (5, 8),    "DT": (4, 6),
    "OM": (10, 15), "MG": (5, 8),   "KO": (5, 10),   "OH": (8, 12),
    "SI": (8, 12),  "TJ": (8, 12),  "KS": (8, 12),
}

# Terminal stations per line for destination labeling
TERMINALS = {
    "JY": ["IKEBUKURO", "SHIBUYA", "SHINJUKU", "UENO", "TOKYO"],
    "JC": ["TAKAO", "TACHIKAWA", "OGIKUBO", "TOKYO"],
    "JB": ["CHIBA", "MITAKA", "SHINJUKU"],
    "JK": ["OMIYA", "OFUNA", "YOKOHAMA"],
    "JA": ["OMIYA", "OSAKI", "SHIBUYA"],
    "JH": ["OMIYA", "YOKOHAMA", "KAMAKURA", "ZUSHI"],
    "JU": ["UTSUNOMIYA", "TAKASAKI", "UENO", "SHINJUKU"],
    "G":  ["ASAKUSA", "SHIBUYA", "GINZA"],
    "M":  ["OGIKUBO", "IKEBUKURO", "HONANCHO"],
    "H":  ["KITASENJU", "NAKAMEGURO", "NAKA-MEGURO"],
    "T":  ["NISHIFUNABASHI", "NAKANO", "MITAKA"],
    "C":  ["YOYOGI-UEHARA", "AYASE", "ABIKO"],
    "Y":  ["WAKOSHI", "SHIN-KIBA", "NISHI-FUNABASHI"],
    "Z":  ["OSHIAGE", "SHIBUYA", "NAGATSUTA"],
    "N":  ["TOCHOMAE", "MEGURO", "NISHI-TAKASHIMADAIRA"],
    "F":  ["WAKOSHI", "SHIBUYA", "MOTOMACHI-CHUKAGAI"],
    "A":  ["NISHI-MAGOME", "OSHIAGE", "NARITA-SKYACCESS"],
    "I":  ["MEGURO", "NISHI-TAKASHIMADAIRA", "MITA"],
    "S":  ["SHINJUKU", "MOTOSUMIYOSHI", "SHINOZAKIMACHI"],
    "E":  ["TOCHOMAE", "NERIMA-KASUGACHO", "HIKARIGAOKA"],
    "TY": ["YOKOHAMA", "SHIBUYA", "MOTOMACHI-CHUKAGAI"],
    "DT": ["SHIBUYA", "CHUO-RINKAN", "NAGATSUTA"],
    "OM": ["FUTAKO-TAMAGAWA", "OSAKI"],
    "MG": ["MEGURO", "NAGATSUTA", "MIZONOKUCHI"],
    "KO": ["CHOFU", "SHINJUKU", "HASHIMOTO", "KEIO-HACHIOJI"],
    "KL": ["KEIO-SAGAMIHARA", "SHINJUKU"],
    "KI": ["KICHIJOJI", "SHIBUYA"],
    "OH": ["ODAWARA", "SHINJUKU", "FUJISAWA", "KARAKIDA"],
    "OE": ["KATASE-ENOSHIMA", "SHINJUKU"],
    "SI": ["HANNO", "IKEBUKURO", "MUSASHI-KYURYO"],
    "SS": ["HANA-KOGANEI", "NISHI-SHINJUKU"],
    "TJ": ["OGOSE", "IKEBUKURO", "KAWAGOE"],
    "TS": ["TOBU-NIKKO", "ASAKUSA", "AIZUWAKAMATSU"],
    "KS": ["URAGA", "SHINAGAWA", "NARITA"],
    "KK": ["HANEDA-AIRPORT", "SHINAGAWA"],
    "KE": ["NARITA-AIRPORT", "UENO"],
    "MM": ["MOTOMACHI-CHUKAGAI", "YOKOHAMA"],
    "SR": ["URAWA-MISONO", "OSAKI", "SHINJUKU"],
    "RI": ["SHINKIBA", "OSAKI"],
    "YU": ["TOYOSU", "SHIMBASHI"],
    "MO": ["HANEDA-AIRPORT-T1", "HAMAMATSUCHO"],
}


def _now_jst() -> datetime:
    return datetime.now(JST)


def _is_peak() -> bool:
    h = _now_jst().hour
    return (7 <= h <= 9) or (17 <= h <= 20)


def _headway(line_code: str) -> int:
    peak, off = HEADWAYS.get(line_code, (8, 12))
    return peak if _is_peak() else off


class ODPTClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self._cache: dict = {}
        self._cache_time: dict = {}
        self._cache_ttl = 15  # seconds

    async def _get(self, endpoint: str, params: dict) -> list:
        if self.api_key:
            params["acl:consumerKey"] = self.api_key
        url = f"{ODPT_BASE}/{endpoint}"
        cache_key = url + str(sorted(params.items()))
        now = time.time()
        if cache_key in self._cache and now - self._cache_time.get(cache_key, 0) < self._cache_ttl:
            return self._cache[cache_key]
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            self._cache[cache_key] = data
            self._cache_time[cache_key] = now
            return data

    def _strip_prefix(self, s: str) -> str:
        if ":" in s:
            return s.rsplit(":", 1)[-1]
        return s

    def _station_display_name(self, odpt_id: str) -> str:
        """Convert odpt station ID to readable name."""
        raw = self._strip_prefix(odpt_id)
        # "JR-East.Yamanote.Tokyo" → "Tokyo"
        parts = raw.split(".")
        return parts[-1] if parts else raw

    async def get_trains_at_station(self, station_id: str) -> list:
        """Return upcoming trains for a station. Falls back to demo data."""
        if not self.api_key:
            return self._demo_station_trains(station_id)
        station = STATIONS.get(station_id)
        if not station:
            return []
        results = []
        for line_code, odpt_station_id in station.get("odpt", {}).items():
            line = LINES.get(line_code, {})
            try:
                trains = await self._get("odpt:Train", {
                    "odpt:railway": line.get("odpt", ""),
                })
                for t in trains:
                    from_st = t.get("odpt:fromStation", "")
                    to_st = t.get("odpt:toStation", "")
                    dest_list = t.get("odpt:destinationStation", [])
                    dest = (dest_list[0] if dest_list else to_st) or ""
                    if odpt_station_id in (from_st, to_st):
                        results.append({
                            "line_code": line_code,
                            "line_name": line.get("short", line_code),
                            "color": line.get("color", "#ffffff"),
                            "text_color": line.get("text", "#000000"),
                            "shape": line.get("shape", "rect"),
                            "train_number": t.get("odpt:trainNumber", ""),
                            "destination": self._station_display_name(dest).upper(),
                            "platform": "",
                            "delay_min": (t.get("odpt:delay", 0) or 0) // 60,
                            "eta_min": 1,
                            "direction": t.get("odpt:railDirection", ""),
                        })
            except Exception:
                results.extend(self._demo_line_trains(station_id, line_code))
        results.sort(key=lambda x: x["eta_min"])
        return results[:16]

    async def get_trains_on_line(self, line_code: str) -> list:
        """Return all current trains on a line."""
        if not self.api_key:
            return self._demo_line_all_trains(line_code)
        line = LINES.get(line_code)
        if not line:
            return []
        try:
            trains = await self._get("odpt:Train", {"odpt:railway": line["odpt"]})
            results = []
            for t in trains:
                dest_list = t.get("odpt:destinationStation", [])
                dest = dest_list[0] if dest_list else t.get("odpt:toStation", "")
                results.append({
                    "line_code": line_code,
                    "color": line.get("color", "#ffffff"),
                    "text_color": line.get("text", "#000000"),
                    "train_number": t.get("odpt:trainNumber", ""),
                    "from_station": self._station_display_name(t.get("odpt:fromStation", "")).upper(),
                    "to_station": self._station_display_name(t.get("odpt:toStation", "")).upper(),
                    "destination": self._station_display_name(dest).upper(),
                    "delay_min": (t.get("odpt:delay", 0) or 0) // 60,
                })
            return results
        except Exception:
            return self._demo_line_all_trains(line_code)

    # ── Demo/simulation mode ─────────────────────────────────────────────────

    def _demo_station_trains(self, station_id: str) -> list:
        station = STATIONS.get(station_id)
        if not station:
            return []
        results = []
        seed = int(time.time() / 30)  # changes every 30s for realistic movement
        for line_code in station.get("lines", []):
            results.extend(self._demo_line_trains(station_id, line_code, seed))
        results.sort(key=lambda x: x["eta_min"])
        return results  # no cap — caller sees the full hour

    # Stable per-line platform assignment: same line at same station always maps
    # to the same platform number. Two directions of the same line get adjacent
    # platforms (e.g. JY at Shibuya → platforms 1 and 2).
    _PLATFORM_COUNTS = {
        "shinjuku": 20, "tokyo": 12, "ikebukuro": 8, "shibuya": 8,
        "shinagawa": 6, "ueno": 8, "shimbashi": 6, "akihabara": 4,
    }

    def _station_platform(self, station_id: str, line_code: str, direction: int = 0) -> str:
        """Return a stable platform label for a line at a station."""
        max_plt = self._PLATFORM_COUNTS.get(station_id, 4)
        # Deterministic base platform index per station+line
        base = (abs(hash(station_id + line_code)) % max_plt) + 1
        # Direction 1 gets the adjacent platform (wrapping within count)
        plt = base + direction
        if plt > max_plt:
            plt = max(1, base - 1)
        return str(plt)

    def _demo_line_trains(self, station_id: str, line_code: str, seed: int = None) -> list:
        line = LINES.get(line_code, {})
        terminals = TERMINALS.get(line_code, ["TERMINUS"])
        hw = _headway(line_code)
        if seed is None:
            seed = int(time.time() / 30)
        rng = random.Random(seed + hash(station_id + line_code))
        trains = []
        offset = rng.randint(0, hw - 1)
        i = 0
        eta = offset
        while eta <= 60:
            # Alternate direction each train (inbound/outbound on adjacent platforms)
            direction = i % 2
            dest = terminals[i % len(terminals)]
            delay = rng.choice([0, 0, 0, 1, 2]) if _is_peak() else 0
            trains.append({
                "line_code": line_code,
                "line_name": line.get("short", line_code),
                "color": line.get("color", "#ffffff"),
                "text_color": line.get("text", "#000000"),
                "shape": line.get("shape", "rect"),
                "train_number": f"{line_code}{(rng.randint(100, 999) + i) % 900 + 100}",
                "destination": dest,
                "platform": self._station_platform(station_id, line_code, direction),
                "delay_min": delay,
                "eta_min": max(1, eta),
                "direction": "",
            })
            i += 1
            eta += hw + rng.randint(-1, 1)  # slight jitter per train
        return trains

    def _demo_line_all_trains(self, line_code: str) -> list:
        line = LINES.get(line_code, {})
        terminals = TERMINALS.get(line_code, ["TERMINUS"])
        hw = _headway(line_code)
        seed = int(time.time() / 30)
        rng = random.Random(seed + hash(line_code))
        num_trains = max(3, 60 // hw)
        results = []
        # Get all station IDs that have this line
        line_stations = [
            sid for sid, s in STATIONS.items() if line_code in s.get("lines", [])
        ]
        if not line_stations:
            line_stations = ["shinjuku", "shibuya", "ikebukuro"]
        for i in range(num_trains):
            st = line_stations[i % len(line_stations)]
            st_data = STATIONS.get(st, {})
            dest = rng.choice(terminals)
            results.append({
                "line_code": line_code,
                "color": line.get("color", "#ffffff"),
                "text_color": line.get("text", "#000000"),
                "train_number": f"{line_code}{100 + i}",
                "from_station": st_data.get("name_en", st).upper(),
                "to_station": dest,
                "destination": dest,
                "delay_min": rng.choice([0, 0, 0, 0, 1, 2]) if _is_peak() else 0,
            })
        return results
