"""좌표와 날짜로 일별 기온 · 강수확률 · 눈을 받는다. 비 오는 날인지의 판정은 여기 없다(5단계). (PRD 9번 get_weather, 14번 4단계 중 4-4)

값을 받지 못한 날은 지어내지 않고 available: False 로 표시한다. 그래프는 그 날을 "날씨 정보를 가져오지 못했습니다" 로 알리고 코스는 계속 짠다.
"""
import time
from datetime import date, timedelta

import config
from harness.logs import get_logger
from tools import kma
from tools.geo import _point

log = get_logger("tools.weather")

SOURCE = "Open-Meteo"


def fetch_open_meteo(lat: float, lon: float, start: str, end: str, get=None) -> dict:
    """실제 호출. 끝내 실패하면 예외를 던진다(get_weather 가 받아 결과로 바꾼다)."""
    import requests

    get = get or requests.get
    params = {"latitude": lat, "longitude": lon, "daily": config.WEATHER_DAILY, "timezone": "Asia/Seoul", "start_date": start, "end_date": end}
    # 왜: 잠깐 끊긴 것은 한 번 더 부르면 풀린다. 요청이 잘못된 경우(4xx)는 다시 불러도 같으므로 바로 끝낸다. 어디: 실제 호출.
    # 교안: 3일차 Part2 "실패도 결과로". 오래 죽어 있으면 여기서도 못 살리므로, 그때는 그래프가 "날씨를 가져오지 못했습니다" 로 알리고 코스를 짠다.
    for attempt in range(config.WEATHER_RETRIES + 1):
        try:
            res = get(config.WEATHER_URL, params=params, timeout=config.WEATHER_TIMEOUT_SEC)
            if res.status_code < 500:
                res.raise_for_status()
                return res.json()
            error = RuntimeError(f"HTTP {res.status_code}")
        except (requests.ConnectionError, requests.Timeout) as e:
            error = e
        log.warning("날씨 서버 응답 없음 (시도 %d/%d): %s", attempt + 1, config.WEATHER_RETRIES + 1, type(error).__name__)
        if attempt == config.WEATHER_RETRIES:
            raise error


def _blank(day: str, note: str) -> dict:
    return {"date": day, "available": False, "temp_max": None, "temp_min": None, "rain_prob": None, "snow_cm": None, "note": note}


def _open_meteo_values(fetch, point, askable) -> dict:
    raw = fetch(point[0], point[1], askable[0].isoformat(), askable[-1].isoformat())
    daily, values = raw["daily"], {}
    for i, day in enumerate(daily["time"]):
        # 항목이 통째로 없거나 날짜 수보다 짧으면 그 날의 값은 None 이다(뒤에서 "없음" 으로 표시된다).
        values[day] = {key: (daily.get(name) or [])[i] if i < len(daily.get(name) or []) else None for key, name in (
            ("temp_max", "temperature_2m_max"), ("temp_min", "temperature_2m_min"),
            ("rain_prob", "precipitation_probability_max"), ("snow_cm", "snowfall_sum"))}
    return values


def get_weather(lat, lon, dates: list, *, fetch=None, short=None, mid=None, today: str | None = None) -> dict:
    """성공: {"ok": True, "days": [...], "unavailable": [날짜], "source", "took_ms"} / 실패: {"ok": False, "reason"}

    날짜마다 기상청 단기(오늘~) → 기상청 중기(4~10일 뒤) → Open-Meteo 순으로 첫 번째로 값을 준 층의 것을 쓴다.
    fetch(Open-Meteo) · short · mid 중 하나라도 넘기면 넘긴 층만 쓴다(테스트에서 가짜로 바꾸기 위해). 아무것도 안 넘기면 세 층 모두 실제 호출.
    """
    started = time.perf_counter()
    point, problem = _point((lat, lon))
    if problem:
        return {"ok": False, "reason": problem}
    if not dates:
        return {"ok": False, "reason": "날짜가 없습니다"}
    try:
        wanted = [date.fromisoformat(d) for d in dates]
        first = date.fromisoformat(today) if today else date.today()
    except (TypeError, ValueError):
        return {"ok": False, "reason": f"날짜를 읽지 못했습니다: {dates!r} (예: 2026-11-14)"}

    if fetch is None and short is None and mid is None:
        fetch = fetch_open_meteo
        short = lambda la, lo: kma.fetch_short(la, lo)
        mid = lambda la, lo: kma.fetch_mid(la, lo)

    # 왜: 예보는 오늘부터 정해진 일수까지만 나온다. 범위 밖 날짜를 물으면 서버가 요청 전체를 거절하므로, 물을 수 있는 날만 골라 묻는다. 어디: 호출 전.
    # 교안: 4일차 PRD "외부 의존 주입" — 오늘 날짜와 조회 함수를 인자로 받아, 평가에서 가짜 날씨로 같은 결과를 낸다.
    last = first + timedelta(days=config.WEATHER_FORECAST_DAYS - 1)
    todo = sorted({d for d in wanted if first <= d <= last})
    values, sources, error = {}, {}, None

    def run_layer(name, call, covers):
        # 왜: 한 층이 실패해도 다음 층이 있으면 코스를 계속 짠다. 기상청이 느리거나 죽어도 Open-Meteo 가 받쳐 준다. 어디: 층별 시도.
        # 교안: 3일차 Part2 "실패도 결과로" 를 층 단위로 적용. 예외 문구에는 주소(키)가 섞일 수 있어 종류만 남긴다.
        nonlocal error
        want = [d for d in todo if d.isoformat() not in values and covers(d)]
        if not want or call is None:
            return
        try:
            got = call(want)
        except Exception as e:
            log.error("날씨를 가져오지 못했습니다: %s (%s, %s ~ %s)", type(e).__name__, name, want[0], want[-1])
            error = error or type(e).__name__
            return
        for d in want:
            v = got.get(d.isoformat())
            if v is not None and v.get("temp_max") is not None and v.get("rain_prob") is not None:
                values[d.isoformat()], sources[d.isoformat()] = v, name

    span = lambda d: (d - first).days
    run_layer(kma.SHORT_SOURCE, short and (lambda want: kma.parse_short(short(point[0], point[1]))), lambda d: span(d) <= 4)
    def mid_call(want):
        got = mid(point[0], point[1])
        return kma.parse_mid(got["tmFc"], got["land"], got["ta"])
    run_layer(kma.MID_SOURCE, mid and mid_call, lambda d: 3 <= span(d) <= 10)
    run_layer(SOURCE, fetch and (lambda want: _open_meteo_values(fetch, point, want)), lambda d: True)
    if error and not values and todo:
        return {"ok": False, "reason": f"날씨를 가져오지 못했습니다: {error}"}

    # 왜: 받지 못한 날을 평균이나 어제 값으로 채우면 틀린 날씨로 코스를 짜게 된다. 없는 날은 없다고 표시만 한다. 어디: 날짜별 정리.
    # 교안: 3일차 Part2 "실패도 결과로" 를 날짜 단위로 적용. 판정(강수 60% 이상)은 하지 않고 숫자만 준다 — 도구는 한 가지 일만.
    days = []
    for d in wanted:
        key = d.isoformat()
        v = values.get(key)
        if d < first:
            days.append(_blank(key, "지난 날짜"))
        elif d > last:
            days.append(_blank(key, f"예보 범위 밖 (오늘부터 {config.WEATHER_FORECAST_DAYS}일까지)"))
        elif v is None:
            days.append(_blank(key, "응답에 값이 없음"))
        else:
            # 기상청 층의 날은 어느 예보에서 왔는지(source)와 눈 예보 여부(snow)가 더해진다.
            days.append({"date": key, "available": True, **v, "note": "", **({"source": sources[key]} if sources[key] != SOURCE else {})})
    used = list(dict.fromkeys(sources[d["date"]] for d in days if d["available"]))
    return {"ok": True, "days": days, "unavailable": [d["date"] for d in days if not d["available"]],
            "source": " + ".join(used) if used else SOURCE, "took_ms": round((time.perf_counter() - started) * 1000, 1)}
