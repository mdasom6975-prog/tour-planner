"""tools/rest.py · fetch_context 를 가짜 날씨 · 가짜 축제로 확인한다 (14번 5-4). 네트워크를 쓰지 않는다."""
import threading
from datetime import date

import config
from graph.build import build_graph
from graph.context import fetch_update, rest_table, trip_dates
from harness.trace import Trace
from tools.rest import rest_on

# 2026-11-21 토 · 22 일 · 23 월
SUN, MON = date(2026, 11, 22), date(2026, 11, 23)


def stored_place(status, weekdays=(), note=False):
    return {"rest_status": status, "rest_weekdays": list(weekdays), "rest_note": note}


def cand(i, lat=37.0, lon=128.0):
    return {"id": i, "kind": "sight", "lat": lat, "lon": lon}


def w_day(day, rain=10, snow=0.0, available=True):
    return {"date": day, "available": available, "temp_max": 8 if available else None, "temp_min": 1 if available else None,
            "rain_prob": rain if available else None, "snow_cm": snow if available else None, "note": ""}


def fest(i, days, addr="강릉시 어딘가"):
    return {"id": i, "title": f"행사{i}", "addr": addr, "duration_days": days, "days_in_trip": ["2026-11-22"]}


# --- tools/rest.py ---------------------------------------------------------
def test_연중무휴는_영업_매주는_요일을_비교한다():
    assert rest_on(stored_place("always_open"), MON) == "open"
    assert rest_on(stored_place("weekly", ["월"]), MON) == "closed"
    assert rest_on(stored_place("weekly", ["월"]), SUN) == "open"
    assert rest_on(stored_place("weekly", ["토", "일"]), SUN) == "closed"


def test_공휴일_단서가_있어도_요일은_확정으로_본다():
    assert rest_on(stored_place("weekly", ["월"], note=True), MON) == "closed"


def test_휴무를_알_수_없으면_확인_필요다():
    assert rest_on(stored_place("unknown"), MON) == "check"
    assert rest_on({}, MON) == "check"


# --- 날짜 · 휴무 표 ----------------------------------------------------------
def test_여행일_목록은_코드가_만든다():
    assert trip_dates("2026-11-22", 3) == ["2026-11-22", "2026-11-23", "2026-11-24"]


def test_휴무_표는_휴무와_확인_필요만_적는다():
    stored = {"a": stored_place("weekly", ["월"]), "b": stored_place("always_open"), "c": stored_place("unknown")}
    table = rest_table([cand("a"), cand("b"), cand("c"), cand("없음")], stored, ["2026-11-22", "2026-11-23"])
    assert table == {"a": {"2026-11-23": "closed"},
                     "c": {"2026-11-22": "check", "2026-11-23": "check"},
                     "없음": {"2026-11-22": "check", "2026-11-23": "check"}}   # 저장분이 없으면 모른다고 적는다


# --- fetch_context ---------------------------------------------------------
def state(**req):
    base = {"region": "강릉", "days": 2, "start_date": "2026-11-22", "place": None}
    return {"request": {**base, **req}, "candidates": [cand("a", 37.0, 128.0), cand("b", 37.2, 128.2), cand("c", 37.4, 128.4)]}


def run(weather=None, festivals=None, stored=None, st=None):
    trace = Trace(save=False)
    out = fetch_update(weather, festivals, stored, trace)(st or state())
    return out, trace


def ok_weather(calls=None, days=None):
    def fn(lat, lon, dates):
        if calls is not None:
            calls.append((lat, lon, dates))
        return {"ok": True, "days": days or [w_day(d) for d in dates], "source": "Open-Meteo"}
    return fn


def ok_fest(results=()):
    return lambda region, start, end: {"ok": True, "results": list(results), "count": len(results)}


def test_날씨는_후보_좌표의_중앙값과_여행일로_묻는다():
    calls = []
    run(weather=ok_weather(calls), festivals=ok_fest())
    assert calls == [(37.2, 128.2, ["2026-11-22", "2026-11-23"])]


def test_비와_눈_판정은_코드가_한다():
    days = [w_day("2026-11-22", rain=config.RAIN_PROB_THRESHOLD), w_day("2026-11-23", rain=10, snow=0.1)]
    out, _ = run(weather=ok_weather(days=days), festivals=ok_fest())
    d1, d2 = out["weather"]["days"]
    assert (d1["rainy"], d1["snowy"], d1["indoor"]) == (True, False, True)
    assert (d2["rainy"], d2["snowy"], d2["indoor"]) == (False, True, True)
    assert out["weather"]["notice"] == ""


def test_맑고_눈이_없으면_실내_위주가_아니다():
    out, _ = run(weather=ok_weather(), festivals=ok_fest())
    assert [d["indoor"] for d in out["weather"]["days"]] == [False, False]


def test_받지_못한_날은_알림_문장으로_알린다():
    days = [w_day("2026-11-22"), w_day("2026-11-23", available=False)]
    out, _ = run(weather=ok_weather(days=days), festivals=ok_fest())
    assert out["weather"]["unavailable"] == ["2026-11-23"]
    assert out["weather"]["notice"] == "11/23(월) 날씨 정보를 가져오지 못했습니다."
    assert out["weather"]["days"][1]["indoor"] is False   # 값을 지어내 비 오는 날로 만들지 않는다


def test_날씨_조회가_실패해도_축제와_휴무는_계속된다():
    bad = lambda lat, lon, dates: {"ok": False, "reason": "날씨를 가져오지 못했습니다: Timeout"}
    out, trace = run(weather=bad, festivals=ok_fest([fest("f1", 2)]), stored={"a": stored_place("weekly", ["월"])})
    assert out["weather"]["ok"] is False
    assert out["weather"]["notice"] == "11/22(일) 날씨 정보를 가져오지 못했습니다. 11/23(월) 날씨 정보를 가져오지 못했습니다."
    assert [f["id"] for f in out["festivals"]["items"]] == ["f1"]
    assert out["rest_table"]["a"] == {"2026-11-23": "closed"}
    assert [s["ok"] for s in trace.steps if s["step"] == "fetch_context.weather"] == [False]


def test_도구가_예외를_던져도_그래프가_멈추지_않는다():
    def boom(*a):
        raise RuntimeError("x")
    out, _ = run(weather=boom, festivals=boom)
    assert out["weather"]["ok"] is False and out["festivals"]["ok"] is False
    assert out["festivals"]["notice"] == "축제 정보를 가져오지 못했습니다."


def test_일수가_긴_행사는_축제가_아니라_상설_장기_행사로_분리한다():
    results = [fest("short", 3), fest("edge", config.FESTIVAL_MAX_DAYS), fest("long", config.FESTIVAL_MAX_DAYS + 1), fest("year", 365)]
    out, _ = run(weather=ok_weather(), festivals=ok_fest(results))
    assert [f["id"] for f in out["festivals"]["items"]] == ["short", "edge"]
    assert [f["id"] for f in out["festivals"]["long_running"]] == ["long", "year"]


def test_축제가_없으면_등록된_축제가_없다고_알린다():
    out, _ = run(weather=ok_weather(), festivals=ok_fest([fest("year", 365)]))
    assert out["festivals"]["items"] == []
    assert out["festivals"]["notice"] == "이 기간에 등록된 축제가 없습니다."


def test_시군을_거른_경우_그_시군_축제만_남긴다():
    results = [fest("in", 2, "전북특별자치도 전주시 덕진구"), fest("out", 2, "전북특별자치도 군산시 중앙로")]
    st = {**state(region="전북"), "area": "전주"}
    out, _ = run(weather=ok_weather(), festivals=ok_fest(results), st=st)
    assert [f["id"] for f in out["festivals"]["items"]] == ["in"]


def test_날짜가_없으면_아무것도_묻지_않고_알린다():
    def never(*a):
        raise AssertionError("부르면 안 된다")
    out, _ = run(weather=never, festivals=never, st=state(start_date=None))
    assert out["weather"]["notice"] == "여행 날짜가 정해지지 않아 날씨와 축제를 확인하지 못했습니다."
    assert out["festivals"]["items"] == [] and out["rest_table"] == {}


def test_날씨와_축제는_동시에_받는다():
    gate = threading.Barrier(2, timeout=3)   # 두 호출이 동시에 들어와야만 통과한다

    def weather(lat, lon, dates):
        gate.wait()
        return {"ok": True, "days": [w_day(d) for d in dates]}

    def festivals(region, start, end):
        gate.wait()
        return {"ok": True, "results": []}
    out, _ = run(weather=weather, festivals=festivals)
    assert out["weather"]["ok"] and out["festivals"]["ok"]


def test_기록에_두_도구_호출이_남는다():
    _, trace = run(weather=ok_weather(), festivals=ok_fest())
    assert sorted(s["step"] for s in trace.steps) == ["fetch_context.festivals", "fetch_context.weather"]


# --- 그래프 안에서 ----------------------------------------------------------
def test_그래프에서_조건_검색_판정_다음에_context가_채워진다():
    def llm(system, user, schema):
        if schema.__name__ == "TripRequest":
            return {"region": "강릉", "days": 1, "start_date": "2026-11-23"}
        ids = [ln.split("|")[0].replace("id=", "").strip() for ln in user.splitlines() if ln.startswith("id=")]
        return {"relevant_ids": ids, "reason": ""}

    def search(query, *, region, types, area):
        return {"ok": True, "results": [{"id": f"{types[0]}{n}", "title": "t", "type": types[0], "addr": "강릉시", "lat": 37.0,
                                         "lon": 128.0, "snippet": "", "score": 1} for n in range(2)]}
    stored = {"관광지0": stored_place("weekly", ["월"])}
    g = build_graph(Trace(save=False), llm=llm, today="2026-11-13", search=search, weather=ok_weather(), festivals=ok_fest(), stored=stored)
    out = g.invoke({"message": "x"})
    steps = [e["step"] for e in out["trace"]]
    assert steps.index("fetch_context") == steps.index("grade_documents") + 1
    assert out["rest_table"]["관광지0"] == {"2026-11-23": "closed"}
    assert out["weather"]["ok"] and "area" in out
