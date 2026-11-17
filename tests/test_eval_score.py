"""평가 채점기(eval/score.py)에 위반을 일부러 심어 잡는지 확인한다. 모델을 부르지 않는다. (14번 8-3)"""
import config
from eval.score import expect_failures, rule_violations, score_rows

SEOUL = {"lat": 37.57, "lon": 126.98}


def place(i, type_="관광지", region="서울", lat=37.57, lon=126.98, **kw):
    return {"id": i, "title": f"장소{i}", "type": type_, "region": region, "lat": lat, "lon": lon, "showflag": "1",
            "rest_status": "none", "rest_weekdays": [], "rest_nth": [], **kw}


PLACES = {p["id"]: p for p in [
    place("s1"), place("s2", lat=37.58), place("f1", "음식점"), place("f2", "음식점"),
    place("far", lat=37.80),                                    # 서울 상한 10km 를 넘는 곳(약 25km)
    place("busan", region="부산"), place("hidden", showflag="0"),
    place("mon", rest_status="weekly", rest_weekdays=["월"]),    # 매주 월요일 휴무
    place("m1", category="VE07"), place("m2", category="VE07"),
    place("fest", "축제·행사", extra={"event_start": "20261101", "event_end": "20261110"}),
]}


def turn(ids=("s1", "f1", "s2", "f2"), day="2026-11-21", kind="course", **kw):
    slots = [{"slot": s, "id": i, "title": PLACES.get(i, {}).get("title", i)} for s, i in zip(config.COURSE_SLOTS, ids)]
    return {"kind": kind, "mode": "new", "request": {"region": "서울", "days": 1, "start_date": day}, "missing": [], "text": "", "notices": [],
            "course": [{"date": day, "slots": slots}], "backup": [], "cafes": [], "festivals": [], "violations": [], "removed": 0,
            "steps": [{"step": "draft_course", "kind": "node", "ok": True, "took_ms": 1000.0}], "llm_calls": 3, "input_tokens": 10, "output_tokens": 5, **kw}


def row(t=None, expect=None, turns=None, took=10.0):
    return {"id": "x", "case": "정상", "split": "dev", "expect": expect or {"kind": "course"}, "turns": turns or [t or turn()], "error": "", "took_sec": took}


def rules(t):
    return [v["rule"] for v in rule_violations(t, PLACES)]


def test_깨끗한_코스는_위반이_없다():
    assert rules(turn()) == []


def test_없는_장소_다른_지역_비표출_장소를_잡는다():
    assert rules(turn(("없는id", "f1", "s2", "f2"))) == ["unknown_place"]
    assert rules(turn(("busan", "f1", "s2", "f2"))) == ["unknown_place"]
    assert rules(turn(("hidden", "f1", "s2", "f2"))) == ["unknown_place"]


def test_거리_상한을_넘는_연속_구간을_잡는다():
    got = rule_violations(turn(("s1", "f1", "far", "f2")), PLACES)
    assert [v["rule"] for v in got] == ["distance", "distance"] and got[0]["km"] > config.MAX_LEG_KM_BY_REGION["서울"]


def test_휴무일에_넣은_장소를_잡는다():
    assert rules(turn(("mon", "f1", "s2", "f2"), day="2026-11-23")) == ["closed"]   # 월요일
    assert rules(turn(("mon", "f1", "s2", "f2"), day="2026-11-21")) == []           # 토요일


def test_기간_밖_축제를_칸과_안내_양쪽에서_잡는다():
    assert rules(turn(("fest", "f1", "s2", "f2"))) == ["festival_period"]
    out = {"id": "z", "title": "지난 축제", "event_start": "2026-11-01", "event_end": "2026-11-10"}
    inside = {"id": "y", "title": "지금 축제", "event_start": "2026-11-20", "event_end": "2026-11-22"}
    assert rules(turn(festivals=[out, inside])) == ["festival_period"]


def test_기대값과_다른_점을_글로_알린다():
    assert expect_failures(row(), PLACES) == []
    assert expect_failures(row(turn(kind="ask_back")), PLACES) == ["답 종류 ask_back (기대 course)"]
    bad = expect_failures(row(expect={"kind": "course", "region": "부산", "days": 2, "title_not": ["장소s1"], "title_has": ["성산"],
                                      "notice_has": "1곳만", "text_not": ["비밀"], "mode": "edit"}, t=turn(text="비밀 값")), PLACES)
    assert len(bad) == 7
    assert expect_failures(row(turn(("m1", "f1", "m2", "f2")), expect={"kind": "course", "museum_max": 1}), PLACES) == ["박물관류 2곳 (최대 1)"]
    assert expect_failures({**row(), "error": "RuntimeError", "turns": []}, PLACES) == ["실행 오류: RuntimeError"]


def test_되묻기_사유는_적힌_것이_모두_있어야_한다():
    t = turn(kind="ask_back", missing=["region", "days", "start_date"])
    assert expect_failures(row(t, {"kind": "ask_back", "missing": ["region", "days"]}), PLACES) == []
    assert expect_failures(row(t, {"kind": "ask_back", "missing": ["days_too_long"]}), PLACES) == ["되묻기 사유에 없음: ['days_too_long']"]


def test_후속_수정은_지정한_칸만_바뀌어야_한다():
    exp = {"kind": "course", "changed": [["2026-11-21", "점심"]]}
    assert expect_failures(row(expect=exp, turns=[turn(), turn(("s1", "f2", "s2", "f2"))]), PLACES) == []
    assert expect_failures(row(expect=exp, turns=[turn(), turn()]), PLACES) == ["바뀌지 않음: 2026-11-21 점심"]
    assert expect_failures(row(expect=exp, turns=[turn(), turn(("s2", "f2", "s2", "f2"))]), PLACES) == ["요청하지 않은 칸이 바뀜: 2026-11-21 오전"]


def test_합계는_위반_수와_느린_문항과_단계_시간을_센다():
    s = score_rows([row(), row(turn(("s1", "f1", "far", "f2")), took=45.0), row(turn(kind="ask_back"), {"kind": "ask_back"}, took=2.0)], PLACES)
    assert (s["count"], s["expect_ok"], s["courses"], s["rule_total"], s["slow"]) == (3, 3, 2, 2, 1)
    assert s["rule_violations"]["distance"] == 2 and s["step_ms_avg"] == {"draft_course": 1000} and s["course_sec_max"] == 45.0


def test_있어야_하는_칸이_없으면_알린다():
    assert expect_failures(row(expect={"kind": "course", "slots_has": ["카페"]}), PLACES) == ["코스에 없는 칸: 카페"]
    assert expect_failures(row(expect={"kind": "course", "slots_has": ["오전"]}), PLACES) == []


def test_맞는_답이_둘인_문항은_한쪽만_맞아도_통과다():
    exp = {"kind": "ask_back", "missing": ["start_date"], "alt": {"kind": "course", "notice_has": "먼 날짜"}}
    assert expect_failures(row(turn(kind="ask_back", missing=["start_date"]), exp), PLACES) == []
    assert expect_failures(row(turn(notices=["먼 날짜입니다"]), exp), PLACES) == []
    assert expect_failures(row(turn(), exp), PLACES) == ["답 종류 course (기대 ask_back)"]
