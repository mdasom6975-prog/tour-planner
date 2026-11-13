"""좌표와 날짜로 일별 기온 · 강수확률 · 눈을 받는다. 비 오는 날인지의 판정은 여기 없다(5단계). (PRD 9번 get_weather, 14번 4단계 중 4-4)

값을 받지 못한 날은 지어내지 않고 available: False 로 표시한다. 그래프는 그 날을 "날씨 정보를 가져오지 못했습니다" 로 알리고 코스는 계속 짠다.
"""
import time
from datetime import date, timedelta

import config
from tools.geo import _point

SOURCE = "Open-Meteo"


def fetch_open_meteo(lat: float, lon: float, start: str, end: str) -> dict:
    """실제 호출. 실패하면 예외를 던진다(get_weather 가 받아 결과로 바꾼다)."""
    import requests

    res = requests.get(config.WEATHER_URL, timeout=config.WEATHER_TIMEOUT_SEC, params={
        "latitude": lat, "longitude": lon, "daily": config.WEATHER_DAILY, "timezone": "Asia/Seoul", "start_date": start, "end_date": end})
    res.raise_for_status()
    return res.json()


def _blank(day: str, note: str) -> dict:
    return {"date": day, "available": False, "temp_max": None, "temp_min": None, "rain_prob": None, "snow_cm": None, "note": note}


def get_weather(lat, lon, dates: list, *, fetch=None, today: str | None = None) -> dict:
    """성공: {"ok": True, "days": [...], "unavailable": [날짜], "source", "took_ms"} / 실패: {"ok": False, "reason"}"""
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

    # 왜: 예보는 오늘부터 정해진 일수까지만 나온다. 범위 밖 날짜를 물으면 서버가 요청 전체를 거절하므로, 물을 수 있는 날만 골라 묻는다. 어디: 호출 전.
    # 교안: 4일차 PRD "외부 의존 주입" — 오늘 날짜와 조회 함수를 인자로 받아, 평가에서 가짜 날씨로 같은 결과를 낸다.
    last = first + timedelta(days=config.WEATHER_FORECAST_DAYS - 1)
    askable = sorted({d for d in wanted if first <= d <= last})
    values = {}
    if askable:
        try:
            raw = (fetch or fetch_open_meteo)(point[0], point[1], askable[0].isoformat(), askable[-1].isoformat())
            daily = raw["daily"]
            for i, day in enumerate(daily["time"]):
                # 항목이 통째로 없거나 날짜 수보다 짧으면 그 날의 값은 None 이다(뒤에서 "없음" 으로 표시된다).
                values[day] = {key: (daily.get(name) or [])[i] if i < len(daily.get(name) or []) else None for key, name in (
                    ("temp_max", "temperature_2m_max"), ("temp_min", "temperature_2m_min"),
                    ("rain_prob", "precipitation_probability_max"), ("snow_cm", "snowfall_sum"))}
        except Exception as e:   # 시간 초과 · 서버 오류 · 깨진 응답. 그래프가 멈추지 않게 결과로 돌려준다.
            return {"ok": False, "reason": f"날씨를 가져오지 못했습니다: {type(e).__name__}"}

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
        elif v is None or v["temp_max"] is None or v["rain_prob"] is None:
            days.append(_blank(key, "응답에 값이 없음"))
        else:
            days.append({"date": key, "available": True, **v, "note": ""})
    return {"ok": True, "days": days, "unavailable": [d["date"] for d in days if not d["available"]],
            "source": SOURCE, "took_ms": round((time.perf_counter() - started) * 1000, 1)}
