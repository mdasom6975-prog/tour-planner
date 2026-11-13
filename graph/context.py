"""fetch_context 노드의 알맹이. 날씨 · 축제를 병렬로 받고, 후보 × 여행일 휴무 표를 만든다. (14번 5-4)

날씨를 받지 못해도 코스는 짠다. 받지 못한 날은 지어내지 않고 알림 문장으로 알린다 (PRD F3).
"""
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import config
from rag.filters import area_of
from tools.rest import WEEK, rest_on


def trip_dates(start: str, days: int) -> list:
    # 왜: 날짜 계산은 코드가 한다. LLM 이 준 시작일과 일수에서 여행일 목록을 만든다. 어디: fetch_context 입구.
    # 교안: PRD 8번 "날짜 · 요일 계산은 코드".
    first = date.fromisoformat(start)
    return [(first + timedelta(days=n)).isoformat() for n in range(days)]


def _label(day: str) -> str:
    d = date.fromisoformat(day)
    return f"{d.month}/{d.day}({WEEK[d.weekday()]})"


def _center(candidates: list):
    """후보 좌표의 중앙값. 좌표가 있는 후보가 없으면 None."""
    # 왜: 지역 대표 좌표 표를 따로 두지 않고, 이미 조건을 통과한 후보들이 몰린 곳의 날씨를 본다(2026-11-13 결정). 한계: 제주처럼 넓은 지역은 한 지점의 날씨다. 어디: 날씨 좌표.
    # 교안: 직접 대응 없음.
    pts = [(c["lat"], c["lon"]) for c in candidates if c.get("lat") is not None and c.get("lon") is not None]
    if not pts:
        return None
    return statistics.median(p[0] for p in pts), statistics.median(p[1] for p in pts)


def _weather(fn, candidates: list, dates: list) -> dict:
    center = _center(candidates)
    if center is None:
        got = {"ok": False, "reason": "후보 장소에 좌표가 없습니다"}
    else:
        try:
            got = fn(center[0], center[1], dates)
        except Exception as e:   # 도구는 실패를 결과로 주지만, 예상 못 한 오류에도 그래프가 멈추지 않게 한다
            got = {"ok": False, "reason": f"날씨 조회 중 오류: {type(e).__name__}"}
    if not got.get("ok"):
        return {"ok": False, "reason": got.get("reason", "날씨 조회 실패"), "days": [], "unavailable": list(dates),
                "notice": " ".join(f"{_label(d)} 날씨 정보를 가져오지 못했습니다." for d in dates)}
    days = []
    for d in got["days"]:
        # 왜: 비 · 눈 판정은 숫자 비교라 코드가 한다. 눈은 조금이라도 오면(snow_cm > 0) 눈 오는 날로 본다(2026-11-13 결정). 어디: 날짜별 판정.
        # 교안: PRD F3 "비 예보(강수 60% 이상)인 날은 실내 위주". 눈 기준은 PRD 에 없어 이번에 정했다.
        rainy = d["available"] and (d["rain_prob"] or 0) >= config.RAIN_PROB_THRESHOLD
        snowy = d["available"] and (d.get("snow_cm") or 0) > 0
        days.append({**d, "rainy": bool(rainy), "snowy": bool(snowy), "indoor": bool(rainy or snowy)})
    missing = [d["date"] for d in days if not d["available"]]
    return {"ok": True, "days": days, "unavailable": missing, "source": got.get("source"),
            "notice": " ".join(f"{_label(d)} 날씨 정보를 가져오지 못했습니다." for d in missing)}


def _festivals(fn, region: str, dates: list, area) -> dict:
    try:
        got = fn(region, dates[0], dates[-1])
    except Exception as e:
        got = {"ok": False, "reason": f"축제 조회 중 오류: {type(e).__name__}"}
    if not got.get("ok"):
        return {"ok": False, "reason": got.get("reason", "축제 조회 실패"), "items": [], "long_running": [],
                "notice": "축제 정보를 가져오지 못했습니다."}
    found = [f for f in got["results"] if area is None or (area_of(f) or "").startswith(area)]
    # 왜: 일수가 긴 행사는 "그때 가야 볼 수 있는 축제"가 아니라 상설 공연에 가깝다. 따로 두어 코스에 축제로 넣지 않는다(2026-11-13 결정). 어디: 축제 분류.
    # 교안: PRD F3 "축제는 여행 날짜가 행사 기간 안일 때만". 일수 기준 30일은 config.FESTIVAL_MAX_DAYS.
    items = [f for f in found if f["duration_days"] <= config.FESTIVAL_MAX_DAYS]
    long_running = [f for f in found if f["duration_days"] > config.FESTIVAL_MAX_DAYS]
    return {"ok": True, "items": items, "long_running": long_running,
            "notice": "" if items else "이 기간에 등록된 축제가 없습니다."}


def rest_table(candidates: list, stored: dict, dates: list) -> dict:
    """{후보 id: {날짜: 'closed' | 'check'}}. 영업일('open')은 적지 않아 표가 작게 유지된다."""
    table = {}
    for c in candidates:
        place = stored.get(c["id"])
        if place is None:   # 저장분이 없으면 모른다고 적는다
            row = {d: "check" for d in dates}
        else:
            row = {d: r for d in dates if (r := rest_on(place, date.fromisoformat(d))) != "open"}
        if row:
            table[c["id"]] = row
    return table


def fetch_update(weather, festivals, stored: dict | None, trace):
    """weather(lat, lon, dates) · festivals(region, start, end) 는 도구와 같은 모양의 dict 를 돌려주는 함수. 바깥에서 받는다."""
    stored = stored or {}

    def update(state) -> dict:
        req = state.get("request", {})
        start, days, cands = req.get("start_date"), req.get("days"), state.get("candidates", [])
        if not start or not days:
            # 왜: 날짜가 없으면 날씨 · 축제 · 휴무 어느 것도 물을 수 없다. 지어내지 않고 알린다(PRD F1: 날짜가 없어도 진행). 어디: 날짜 미정.
            # 교안: 직접 대응 없음.
            note = "여행 날짜가 정해지지 않아 날씨와 축제를 확인하지 못했습니다."
            return {"weather": {"ok": False, "reason": "날짜 미정", "days": [], "unavailable": [], "notice": note},
                    "festivals": {"ok": False, "reason": "날짜 미정", "items": [], "long_running": [], "notice": note},
                    "rest_table": {}}
        dates = trip_dates(start, days)
        timed = {}

        def run(name, fn, *args):
            t0 = time.perf_counter()
            timed[name] = (fn(*args), round((time.perf_counter() - t0) * 1000, 2))

        # 날씨와 축제는 서로 기다릴 이유가 없어 동시에 받는다. 기록은 스레드가 끝난 뒤 한 곳에서 남긴다(순서가 섞이지 않게).
        calls = []
        if weather is not None:
            calls.append(("weather", _weather, weather, cands, dates))
        if festivals is not None:
            calls.append(("festivals", _festivals, festivals, req.get("region"), dates, state.get("area")))
        with ThreadPoolExecutor(max_workers=2) as pool:
            for f in [pool.submit(run, name, fn, *args) for name, fn, *args in calls]:
                f.result()
        out = {}
        for name, (result, ms) in timed.items():
            out[name] = result
            trace.record(f"fetch_context.{name}", "tool", input={"dates": dates}, ok=result["ok"], took_ms=ms,
                         output={"ok": result["ok"], "notice": result["notice"], **({"reason": result["reason"]} if not result["ok"] else {})})
        out["rest_table"] = rest_table(cands, stored, dates)
        return out
    return update
