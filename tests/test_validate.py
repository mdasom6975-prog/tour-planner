"""validate_course · 재작성 루프 · "매월 ○째 요일" 휴무 판정을 가짜 응답으로 확인한다 (14번 6단계). 네트워크 · 실제 모델을 쓰지 않는다."""
from datetime import date

import pytest

import config
from graph.build import build_graph
from graph.schemas import Course, Grade, TripRequest
from graph.validate import find_violations
from harness.trace import Trace
from ingest.rest_days import parse_rest
from tools.rest import rest_on

D1, D2 = "2026-11-21", "2026-11-22"   # 토 · 일


def place(i, kind, type_, lon=128.90, lat=37.7, **kw):
    return {"id": i, "kind": kind, "type": type_, "title": f"장소{i}", "addr": "강릉시", "lat": lat, "lon": lon, "snippet": "소개", **kw}


CANDS = ([place(f"s{n}", "sight", "관광지", lon=128.90 + n * 0.01) for n in range(4)] + [place(f"m{n}", "sight", "문화시설") for n in range(2)]
         + [place(f"f{n}", "food", "음식점", lon=128.90 + n * 0.01) for n in range(4)] + [place("far", "sight", "관광지", lon=129.60)])   # far: 약 61km
BY_ID = {c["id"]: c for c in CANDS}


def slots(ids):
    return [{"slot": n, "content_id": i, "reason": "r"} for n, i in zip(config.COURSE_SLOTS, ids)]


def good():
    return {"days": [{"date": D1, "slots": slots(["s0", "f0", "s1", "f1"])}, {"date": D2, "slots": slots(["s2", "f2", "s3", "f3"])}]}


def live(status="always_open", weekdays=(), nth=(), note=False, withdrawn=False):
    return {"source": "live", "as_of": "2026-11-13", "withdrawn": withdrawn,
            "place": {"rest_status": status, "rest_weekdays": list(weekdays), "rest_nth": list(nth), "rest_note": note}}


def rules(course, rechecked=None, region="강릉", dates=(D1, D2)):
    return [(v["rule"], v["id"]) for v in find_violations(course, BY_ID, list(dates), rechecked or {}, region)]


# --- 검사 항목 --------------------------------------------------------------
def test_규칙을_지킨_코스는_위반이_없다():
    assert rules(good()) == []


def test_후보에_없는_장소와_칸_유형과_중복을_찾는다():
    c = good()
    c["days"][0]["slots"][0]["content_id"] = "없는곳"     # 후보 밖
    c["days"][0]["slots"][1]["content_id"] = "s2"         # 점심 칸에 관광지
    c["days"][1]["slots"][0]["content_id"] = "s1"         # 11/21 오후와 중복
    got = rules(c)
    assert ("unknown_place", "없는곳") in got and ("slot_type", "s2") in got and ("duplicate", "s1") in got


def test_칸_구성과_날짜가_다르면_찾는다():
    c = good()
    c["days"][0]["slots"].pop()
    assert ("slots", None) in rules(c)
    assert [r for r, _ in rules({"days": [good()["days"][0]]})] == ["dates"]


def test_연속한_두_장소가_지역_상한을_넘으면_찾는다():
    c = good()
    c["days"][0]["slots"][2]["content_id"] = "far"       # f0 → far 약 60km
    assert ("distance", "far") in rules(c)
    # 하루가 바뀌면 이어지지 않는다: 11/21 마지막(f1) → 11/22 첫 장소는 검사하지 않는다
    c = good()
    c["days"][1]["slots"][0]["content_id"] = "far"
    assert ("distance", "far") not in rules(c)


def test_거리_상한은_지역마다_다르다():
    # s0 → f1: 경도 0.01도 차 ≈ 0.9km. 강릉 25 · 기본 30 로는 통과, 상한을 줄이면 걸린다
    c = good()
    c["days"][0]["slots"][1]["content_id"] = "f3"        # s0(128.90) → f3(128.93) ≈ 2.6km
    assert ("distance", "f3") not in rules(c, region="강릉")
    old = config.MAX_LEG_KM_BY_REGION["강릉"]
    config.MAX_LEG_KM_BY_REGION["강릉"] = 1
    try:
        assert ("distance", "f3") in rules(c, region="강릉")
    finally:
        config.MAX_LEG_KM_BY_REGION["강릉"] = old
    assert config.MAX_LEG_KM_BY_REGION == {"서울": 20, "강릉": 25, "부산": 25}


def test_휴무와_철수는_다시_받은_값으로_판정한다():
    rc = {"s0": live("weekly", ["토"]), "s1": live(withdrawn=True), "s2": live("weekly", ["월"])}
    got = rules(good(), rc)
    assert ("closed", "s0") in got and ("withdrawn", "s1") in got and ("closed", "s2") not in got   # s2 는 일요일 영업


def test_저장분으로_대신했어도_같은_규칙으로_판정한다():
    rc = {"s0": {"source": "stored", "as_of": "2026-11-10", "withdrawn": False, "place": live("weekly", ["토"])["place"]}}
    assert ("closed", "s0") in rules(good(), rc)


# --- 매월 ○째 요일 ----------------------------------------------------------
@pytest.mark.parametrize("text, weeks, weekday, note", [
    ("매달 첫째 월요일", [1], "월", False), ("매월 2, 4번째 월요일", [2, 4], "월", False), ("매월 둘째 주 ·넷째 주 목요일", [2, 4], "목", False),
    ("매월 마지막 주 일요일", [-1], "일", False), ("매월 첫째, 둘째 월요일 / 국가지정 공휴일(공휴일이 일요일인 경우 휴관)", [1, 2], "월", True)])
def test_몇째_요일_문장을_읽는다(text, weeks, weekday, note):
    r = parse_rest(text)
    assert (r["rest_status"], r["rest_nth"], r["rest_note"]) == ("nth", [{"weeks": weeks, "weekday": weekday}], note)


def test_매주와_몇째가_함께_있으면_둘_다_읽고_모호하면_읽지_않는다():
    r = parse_rest("매주 일요일 / 매월 셋째 월요일")
    assert (r["rest_weekdays"], r["rest_nth"]) == (["일"], [{"weeks": [3], "weekday": "월"}])
    for text in ("격주 월요일", "매월 첫째 월요일, 셋째 화요일", "매월 1일 휴무"):
        assert parse_rest(text)["rest_status"] == "unknown" and parse_rest(text)["rest_nth"] == []
    assert parse_rest("매주 월요일")["rest_nth"] == [] and parse_rest("")["rest_status"] == "unknown"


def test_몇째_요일은_그_달_날짜로_센다():
    first_mon = {"rest_status": "nth", "rest_weekdays": [], "rest_nth": [{"weeks": [1], "weekday": "월"}], "rest_note": False}
    assert rest_on(first_mon, date(2026, 11, 2)) == "closed"      # 11월 첫 월요일
    assert rest_on(first_mon, date(2026, 11, 9)) == "open"        # 둘째 월요일
    assert rest_on(first_mon, date(2026, 11, 3)) == "open"        # 다른 요일
    last_sun = {**first_mon, "rest_nth": [{"weeks": [-1], "weekday": "일"}]}
    assert rest_on(last_sun, date(2026, 11, 29)) == "closed" and rest_on(last_sun, date(2026, 11, 22)) == "open"
    assert rest_on({**first_mon, "rest_note": True}, date(2026, 11, 9)) == "check"   # 공휴일 같은 단서가 있으면 열었다고 확정하지 않는다
    assert rest_on({**first_mon, "rest_nth": [{"weeks": [5], "weekday": "월"}]}, date(2026, 11, 30)) == "closed"   # 11월 다섯째 월요일


# --- 그래프: 다시 받기 · 재작성 루프 · 위반 장소 제거 ---------------------------
class Harness:
    def __init__(self, drafts, detail_map=None):
        self.drafts, self.detail_map, self.prompts, self.detail_calls = list(drafts), detail_map or {}, [], []

    def search(self, query, *, region, types, area):
        kind = "sight" if "관광지" in types else "food" if "음식점" in types else "indoor"
        pick = {"sight": [c for c in CANDS if c["kind"] == "sight" and c["type"] == "관광지"], "food": [c for c in CANDS if c["kind"] == "food"],
                "indoor": [c for c in CANDS if c["type"] == "문화시설"]}[kind]
        return {"ok": True, "results": [{k: v for k, v in c.items() if k != "kind"} for c in pick]}

    def llm(self, system, user, schema):
        if schema is TripRequest:
            return {"region": "강릉", "days": 2, "start_date": D1}
        if schema is Grade:
            return {"relevant_ids": [l.split("|")[0].replace("id=", "").strip() for l in user.splitlines() if l.startswith("id=")], "reason": ""}
        self.prompts.append(user)
        return Course.model_validate(self.drafts.pop(0) if len(self.drafts) > 1 else self.drafts[0])

    def detail(self, cid):
        self.detail_calls.append(cid)
        got = self.detail_map.get(cid)
        if got is None:
            return {"ok": False, "reason": "실시간 조회 실패"}
        return {"ok": True, "source": "live", "as_of": "2026-11-13", "withdrawn": got.get("withdrawn", False), "note": "", "place": {k: got.get(k) for k in ("rest_status", "rest_weekdays", "rest_nth", "rest_note")}}

    def run(self, stored=None):
        weather = lambda la, lo, d: {"ok": True, "days": [{"date": x, "available": True, "temp_min": 1, "temp_max": 8, "rain_prob": 10, "snow_cm": 0.0, "note": ""} for x in d], "source": "t"}
        festivals = lambda r, s, e: {"ok": True, "results": []}
        g = build_graph(Trace(save=False), llm=self.llm, today="2026-11-13", search=self.search, weather=weather, festivals=festivals,
                        stored=stored if stored is not None else {c["id"]: {"rest_status": "always_open", "rest_weekdays": [], "rest_nth": [], "rest_note": False} for c in CANDS}, detail=self.detail)
        return g.invoke({"message": "x"})


def test_위반이_없으면_한_번에_끝나고_코스_장소만_한_번씩_다시_받는다():
    ok = {"rest_status": "always_open", "rest_weekdays": [], "rest_nth": [], "rest_note": False}
    h = Harness([good()], {i: ok for i in ("s0", "s1", "s2", "s3", "f0", "f1", "f2", "f3")})
    out = h.run()
    assert out["violations"] == [] and out["retries"]["draft"] == 1 and out["answer"]["kind"] == "course"
    assert sorted(h.detail_calls) == ["f0", "f1", "f2", "f3", "s0", "s1", "s2", "s3"]     # 코스에 든 8곳만
    assert set(out["rechecked"]) == set(h.detail_calls)
    assert out["answer"]["text"].count("정보 방금 확인") == 8


def test_휴무를_찾으면_사유를_넣어_다시_쓰고_이미_받은_장소는_다시_받지_않는다():
    bad, fixed = good(), good()
    fixed["days"][0]["slots"][0]["content_id"] = "m0"      # s0 → m0 로 교체
    h = Harness([bad, fixed], {"s0": {"rest_status": "weekly", "rest_weekdays": ["토"], "rest_nth": [], "rest_note": False},
                               **{i: {"rest_status": "always_open", "rest_weekdays": [], "rest_nth": [], "rest_note": False} for i in ("s1", "s2", "s3", "f0", "f1", "f2", "f3", "m0")}})
    out = h.run()
    assert out["retries"]["draft"] == 2 and out["violations"] == []
    assert "장소s0 은(는) 11/21(토) 휴무입니다" in h.prompts[1]        # 위반 사유가 재작성 입력에 들어갔다
    assert h.detail_calls.count("s0") == 1 and h.detail_calls.count("s1") == 1 and h.detail_calls.count("m0") == 1
    assert out["rest_table"]["s0"] == {D1: "closed"}                    # 다시 받은 값으로 표가 갱신된다


def test_두_번_고쳐도_남으면_위반_장소를_빼고_확인_필요로_알린다():
    bad = good()
    bad["days"][0]["slots"][0]["content_id"] = "없는곳"
    h = Harness([bad])
    out = h.run()
    assert out["retries"]["draft"] == config.MAX_REDRAFTS + 1 and out["violations"]
    assert all(s["content_id"] != "없는곳" for d in out["course"]["days"] for s in d["slots"]) and len(out["course"]["days"][0]["slots"]) == 3
    assert any("확인 필요: 11/21(토) 오전 없는곳" in n for n in out["answer"]["notices"]) and out["answer"]["kind"] == "course"
    assert "없는곳" not in "".join(s["id"] for d in out["answer"]["days"] for s in d["slots"])


def test_다시_받기에_실패하면_저장분으로_판정하고_기준일을_밝힌다():
    stored = {c["id"]: {"rest_status": "weekly", "rest_weekdays": ["토"] if c["id"] == "s0" else [], "rest_nth": [], "rest_note": False, "fetched": "2026-11-10"} for c in CANDS}
    h = Harness([good()], {})          # 실시간은 전부 실패
    out = h.run(stored)
    assert any(v["rule"] == "closed" and v["id"] == "s0" for v in out["violations"])
    assert out["rechecked"]["s1"]["source"] == "stored" and out["rechecked"]["s1"]["as_of"] == "2026-11-10"
    assert "정보 2026-11-10 기준(저장분)" in out["answer"]["text"]


def test_다시_받기는_한_스레드에서_차례로_한다():
    import threading
    seen = set()
    h = Harness([good()])
    orig = h.detail
    h.detail = lambda cid: (seen.add(threading.current_thread().name), orig(cid))[1]   # 호출 한도 기록 파일이 동시 쓰기로 깨지지 않게
    h.run()
    assert seen == {threading.current_thread().name}
