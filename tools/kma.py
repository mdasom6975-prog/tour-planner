"""기상청 단기 · 중기예보를 받아 날짜별 값으로 바꾼다. 네트워크 호출(fetch_*)과 해석(parse_*)을 나눠, 해석은 저장해 둔 실제 응답으로 확인한다. (PRD 9번 get_weather)

값의 모양은 Open-Meteo 층과 같다: temp_max · temp_min · rain_prob · snow_cm, 거기에 눈 예보 여부 snow(참/거짓)를 더한다.
키(TOURAPI_KEY)는 data.go.kr 공용이다. 실패 로그에는 예외 종류만 적는다(예외 문구에 주소가 섞일 수 있다).
"""
import math
import os
import re
from datetime import datetime, timedelta, timezone

import config
from harness.logs import get_logger

log = get_logger("tools.kma")
KST = timezone(timedelta(hours=9))
SHORT_SOURCE = "기상청 단기예보"
MID_SOURCE = "기상청 중기예보"
BASE_TIMES = ["0200", "0500", "0800", "1100", "1400", "1700", "2000", "2300"]

# 왜: 중기예보는 시 · 도 단위 구역(육상)과 도시 단위(기온) 코드를 따로 받는다. 좌표에서 가장 가까운 대표 도시의 두 코드를 쓴다. 어디: 중기 조회 전.
# 교안: 직접 대응 없음. 구역 코드는 기상청 중기예보 가이드의 예보구역 표(엑셀)에서 확인했다. 경계 지역은 이웃 구역으로 잡힐 수 있다.
MID_CITIES = [  # (이름, 위도, 경도, 육상 코드, 기온 코드)
    ("서울", 37.57, 126.98, "11B00000", "11B10101"), ("춘천", 37.88, 127.73, "11D10000", "11D10301"),
    ("강릉", 37.75, 128.88, "11D20000", "11D20501"), ("청주", 36.64, 127.49, "11C10000", "11C10301"),
    ("대전", 36.35, 127.38, "11C20000", "11C20401"), ("전주", 35.82, 127.15, "11F10000", "11F10201"),
    ("광주", 35.16, 126.85, "11F20000", "11F20501"), ("대구", 35.87, 128.60, "11H10000", "11H10701"),
    ("부산", 35.18, 129.08, "11H20000", "11H20201"), ("제주", 33.50, 126.53, "11G00000", "11G00201"),
]


def to_grid(lat: float, lon: float) -> tuple:
    """위경도 → 기상청 격자(nx, ny). 기상청 공식 Lambert 변환식. 서울시청은 (60, 127)."""
    re_, grid = 6371.00877, 5.0
    d2r = math.pi / 180
    slat1, slat2, olon, olat = 30 * d2r, 60 * d2r, 126 * d2r, 38 * d2r
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(math.tan(math.pi / 4 + slat2 / 2) / math.tan(math.pi / 4 + slat1 / 2))
    sf = math.tan(math.pi / 4 + slat1 / 2) ** sn * math.cos(slat1) / sn
    ro = re_ / grid * sf / math.tan(math.pi / 4 + olat / 2) ** sn
    ra = re_ / grid * sf / math.tan(math.pi / 4 + lat * d2r / 2) ** sn
    theta = lon * d2r - olon
    theta = (theta + math.pi) % (2 * math.pi) - math.pi
    theta *= sn
    return int(ra * math.sin(theta) + 210 / grid + 1.5), int(ro - ra * math.cos(theta) + 675 / grid + 1.5)


def mid_region(lat: float, lon: float) -> tuple:
    """가장 가까운 대표 도시의 (육상 코드, 기온 코드)."""
    best = min(MID_CITIES, key=lambda c: (c[1] - lat) ** 2 + ((c[2] - lon) * math.cos(lat * math.pi / 180)) ** 2)
    return best[3], best[4]


def _number(text) -> float:
    m = re.search(r"[\d.]+", str(text))
    return float(m.group()) if m else 0.0


def _snow_amount(text: str) -> float:
    # '적설없음' 0, '0.5cm 미만' 은 0.5 로(조금이라도 오는 것이므로 0 으로 두지 않는다), '5.0cm 이상' 은 5.0.
    return 0.0 if "없음" in str(text) else _number(text)


def parse_short(items: list) -> dict:
    """단기예보 item 목록 → {'2026-11-14': {...}}. 하루 값이 모자란 날(기온 · 강수확률을 못 정하는 날)은 넣지 않는다."""
    by_day = {}
    for it in items:
        d = it["fcstDate"]
        by_day.setdefault(d, {}).setdefault(it["category"], []).append(it["fcstValue"])
    out = {}
    for d, cats in sorted(by_day.items()):
        pops = [float(v) for v in cats.get("POP", [])]
        tmps = [float(v) for v in cats.get("TMP", [])]
        # 왜: 최저 · 최고기온(TMN/TMX)은 발표 시각에 따라 오늘 것이 빠진다. 없으면 시간별 기온이 하루치(20개 이상)일 때만 거기서 뽑는다. 어디: 날짜별 정리.
        # 교안: 기상청 단기예보 가이드 "TMN/TMX 발표 시각별 제공 범위". 모자라면 지어내지 않고 이 날은 비운다.
        tmx = [float(v) for v in cats.get("TMX", [])] or (tmps if len(tmps) >= 20 else [])
        tmn = [float(v) for v in cats.get("TMN", [])] or (tmps if len(tmps) >= 20 else [])
        if not pops or not tmx or not tmn:
            continue
        snow_cm = round(sum(_snow_amount(v) for v in cats.get("SNO", [])), 1)
        snowy_type = any(str(v) in ("2", "3") for v in cats.get("PTY", []))   # 2 비/눈, 3 눈
        out[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = {"temp_max": max(tmx), "temp_min": min(tmn), "rain_prob": max(pops),
                                            "snow_cm": snow_cm, "snow": bool(snow_cm > 0 or snowy_type)}
    return out


def parse_mid(tm_fc: str, land: dict, ta: dict) -> dict:
    """중기예보(육상 item · 기온 item) → 날짜별 값. 발표일 + N일 뒤를 날짜로 쓴다."""
    base = datetime.strptime(tm_fc[:8], "%Y%m%d")
    out = {}
    for n in range(4, 11):
        am, pm = (f"{n}Am", f"{n}Pm") if n <= 7 else (str(n), str(n))
        probs = [land[k] for k in (f"rnSt{am}", f"rnSt{pm}") if land.get(k) is not None]
        words = " ".join(str(land.get(k) or "") for k in (f"wf{am}", f"wf{pm}"))
        hi, lo = ta.get(f"taMax{n}"), ta.get(f"taMin{n}")
        if not probs or hi is None or lo is None:
            continue
        out[(base + timedelta(days=n)).strftime("%Y-%m-%d")] = {"temp_max": float(hi), "temp_min": float(lo), "rain_prob": float(max(probs)),
                                                                "snow_cm": None, "snow": "눈" in words}
    return out


def _items(res) -> list:
    body = res.json()["response"]
    if body["header"]["resultCode"] != "00":
        raise RuntimeError(f"기상청 오류 {body['header']['resultCode']}")
    item = body["body"]["items"]["item"]
    return item if isinstance(item, list) else [item]


def _call(base: str, op: str, params: dict, get=None) -> list:
    import requests

    get = get or requests.get
    key = os.getenv("TOURAPI_KEY")
    if not key:
        raise RuntimeError("TOURAPI_KEY 없음")
    res = get(f"{base}/{op}", params={"serviceKey": key, "dataType": "JSON", "pageNo": 1, **params}, timeout=config.WEATHER_TIMEOUT_SEC)
    res.raise_for_status()
    return _items(res)


def short_base(now: datetime) -> tuple:
    """가장 최근 발표 시각. 발표 10분 뒤부터 받을 수 있고, 02:10 전이면 전날 23시 발표를 쓴다."""
    t = now.astimezone(KST) - timedelta(minutes=10)
    done = [b for b in BASE_TIMES if b <= t.strftime("%H%M")]
    return (t.strftime("%Y%m%d"), done[-1]) if done else ((t - timedelta(days=1)).strftime("%Y%m%d"), "2300")


def fetch_short(lat: float, lon: float, get=None, now=None) -> list:
    """단기예보 item 목록. 실패하면 예외(get_weather 가 받아 다음 층으로 넘어간다)."""
    nx, ny = to_grid(lat, lon)
    bd, bt = short_base(now or datetime.now(KST))
    return _call(config.KMA_SHORT_BASE, "getVilageFcst", {"numOfRows": 1000, "base_date": bd, "base_time": bt, "nx": nx, "ny": ny}, get)


def fetch_mid(lat: float, lon: float, get=None, now=None) -> dict:
    """{'tmFc', 'land', 'ta'}. 발표는 06시 · 18시, 최근 24시간 것만 받을 수 있다."""
    now = (now or datetime.now(KST)).astimezone(KST)
    tm = now.replace(hour=18, minute=0) if now.hour >= 18 else now.replace(hour=6, minute=0) if now.hour >= 6 else (now - timedelta(days=1)).replace(hour=18, minute=0)
    tm_fc = tm.strftime("%Y%m%d%H%M")
    land_id, ta_id = mid_region(lat, lon)
    land = _call(config.KMA_MID_BASE, "getMidLandFcst", {"numOfRows": 10, "regId": land_id, "tmFc": tm_fc}, get)[0]
    ta = _call(config.KMA_MID_BASE, "getMidTa", {"numOfRows": 10, "regId": ta_id, "tmFc": tm_fc}, get)[0]
    return {"tmFc": tm_fc, "land": land, "ta": ta}
