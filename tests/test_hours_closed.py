"""칸 시간대와 장소 이용시간의 충돌(hours_closed)을 찾고 고치는지 가짜 데이터로 확인한다 (코스 품질 T4). 네트워크 · 모델을 쓰지 않는다."""
import config
from eval.quality import course_quality, hours_fit
from graph.build import after_validate
from graph.validate import find_violations, hours_of, reorder_day, repair_slots, validate_update
from harness.trace import Trace

D1, D2 = "2026-11-21", "2026-11-22"
OPEN = "09:00~22:00"   # 모든 대표 시각에 여는 문장


def place(i, kind, type_, lon=128.90, hours=OPEN, **kw):
    return {"id": i, "kind": kind, "type": type_, "title": f"장소{i}", "addr": "강릉시", "lat": 37.7, "lon": lon, "snippet": "소개", "hours_text": hours, **kw}


def sight(i, lon=128.90, hours=OPEN):
    return place(i, "sight", "관광지", lon=lon, hours=hours)


def food(i, lon=128.90, hours=OPEN, **kw):
    return place(i, "food", "음식점", lon=lon, hours=hours, **kw)


def slots(ids, names=config.COURSE_SLOTS):
    return [{"slot": n, "content_id": i, "reason": "r"} for n, i in zip(names, ids)]


def world(*rows):
    base = [sight(f"g{n}", lon=128.90 + n * 0.01) for n in range(6)] + [food(f"f{n}", lon=128.90 + n * 0.01) for n in range(4)]
    cands = {c["id"]: c for c in base}
    cands.update({c["id"]: c for c in rows})   # 같은 id 는 덮어쓴다
    return cands


def day(ids, date=D1, names=config.COURSE_SLOTS):
    return {"date": date, "slots": slots(ids, names)}


BASIC = ["g0", "f0", "g1", "g2", "f1"]   # 오전 · 점심 · 오후 · 늦은 오후 · 저녁
vio = lambda course, cands, hours="auto", dates=(D1,), names=None: [(v["rule"], v["id"], v["date"], v["slot"]) for v in find_violations(
    course, cands, list(dates), {}, "강릉", names, None, None, {i: c["hours_text"] for i, c in cands.items()} if hours == "auto" else hours)]


# --- 판정 ---
def test_오전_칸에_11시_개장_장소는_위반이고_slot과_date를_채운다():
    cands = world(sight("g0", hours="11:00~20:00"))
    assert vio({"days": [day(BASIC)]}, cands) == [("hours_closed", "g0", D1, "오전")]
    v = find_violations({"days": [day(BASIC)]}, cands, [D1], {}, "강릉", None, None, None, {"g0": "11:00~20:00"})[0]
    assert v["slot"] == "오전" and v["date"] == D1 and "11:00" in v["reason"] and "10:00" in v["reason"]


def test_열려_있으면_위반이_없다():
    assert vio({"days": [day(BASIC)]}, world()) == []


def test_저녁_칸에_17시에_닫는_식당과_점심_칸에_저녁만_하는_식당():
    cands = world(food("f1", hours="11:00~17:00"), food("f0", hours="17:00~22:00"))
    assert vio({"days": [day(BASIC)]}, cands) == [("hours_closed", "f0", D1, "점심"), ("hours_closed", "f1", D1, "저녁")]


def test_쉬는_시간이_칸_시각과_겹치면_위반():
    cands = world(food("f0", hours="11:00~21:00 (준비시간 12:00~13:00)"))   # 점심 12:30 이 쉬는 시간
    assert vio({"days": [day(BASIC)]}, cands) == [("hours_closed", "f0", D1, "점심")]


def test_읽을_수_없거나_정보가_없으면_위반으로_보지_않는다():
    for text in ("- 평일 11:00~20:00- 주말 09:00~18:00", "공연 별로 상이함", "", None):
        assert vio({"days": [day(BASIC)]}, world(sight("g0", hours=text), food("f1", hours=text))) == [], text
    assert vio({"days": [day(BASIC)]}, world(sight("g0", hours="11:00~20:00")), hours={}) == []   # 이용시간 값을 아예 주지 않으면 규칙을 켜지 않는다
    assert vio({"days": [day(BASIC)]}, world(sight("g0", hours="11:00~20:00")), hours=None) == []


def test_자정_넘김과_상시개방은_충돌이_아니다():
    cands = world(food("f1", hours="17:00~02:00"), sight("g0", hours="상시 개방"))
    assert vio({"days": [day(BASIC)]}, cands) == []


def test_카페_칸은_14시_기준():
    names = config.COURSE_SLOTS_WITH_CAFE
    cands = world(food("c1", is_cafe=True, hours="15:00~22:00"))
    got = vio({"days": [day(["g0", "f0", "c1", "g1", "g2", "f1"], names=names)]}, cands, names=names)
    assert got == [("hours_closed", "c1", D1, "카페")]


def test_여러_날은_충돌이_난_날의_칸만_위반으로_표시한다():
    cands = world(food("f3", hours="11:00~16:00"))
    course = {"days": [day(BASIC), day(["g3", "f2", "g4", "g5", "f3"], D2)]}
    assert vio(course, cands, dates=(D1, D2)) == [("hours_closed", "f3", D2, "저녁")]


def test_후보에_없는_장소는_시간_검사에서_멈추지_않고_unknown_place_만_걸린다():
    cands = world()
    got = vio({"days": [day(["g0", "nope", "g1", "g2", "f1"])]}, cands, hours={"g0": OPEN})
    assert [g[0] for g in got] == ["unknown_place"]


def test_시간_정보가_없거나_충돌이_없으면_검증_결과가_이전과_같다():
    cands = world(sight("g6", lon=129.60))   # 거리 위반이 있는 코스
    course = {"days": [day(["g0", "f0", "g6", "g2", "f1"])]}
    base = vio(course, cands, hours=None)
    assert base and vio(course, cands, hours="auto") == base and vio(course, cands, hours={}) == base
    assert vio(course, cands, hours={i: None for i in cands}) == base


def test_hours_of는_다시_받은_값이_있으면_그것_없으면_저장분():
    cands = world()
    stored = {"g0": {"hours_text": "09:00~18:00"}, "g1": {"hours_text": "10:00~17:00"}, "g2": {}}
    rechecked = {"g0": {"place": {"hours_text": "11:00~20:00"}}, "g1": {"place": {"hours_text": None}}, "zz": {"place": {"hours_text": "1:00~2:00"}}}
    got = hours_of(cands, stored, rechecked)
    assert got["g0"] == "11:00~20:00" and got["g1"] == "10:00~17:00" and got["g2"] is None and "zz" not in got


# --- 고치기 ---
def fix(course, cands, hours="auto", rest=None):
    hours = {i: c["hours_text"] for i, c in cands.items()} if hours == "auto" else hours
    return repair_slots(course, cands, [D1], {}, "강릉", None, None, rest, None, hours)


def only(*rows):
    return {c["id"]: c for c in rows}


def test_충돌_칸은_그_시간에_여는_가까운_후보로_바꾸고_새_위반이_없다():
    # near(가장 가깝다)는 오전에 닫아서 건너뛰고, 그다음 mid 를 고른다
    cands = only(sight("g0", lon=128.90, hours="11:00~20:00"), food("f0"), sight("g1"), sight("g2"), food("f1"), sight("near", lon=128.905, hours="12:00~20:00"), sight("mid", lon=128.93))
    course = {"days": [day(BASIC)]}
    fixed, replaced = fix(course, cands)
    assert replaced == [{"date": D1, "slot": "오전", "old_id": "g0", "id": "mid", "rule": "hours_closed"}]
    assert vio(fixed, cands) == [] and fixed["days"][0]["slots"][0]["reason"] == config.REPLACED_REASON
    assert course["days"][0]["slots"][0]["content_id"] == "g0"   # 원본은 그대로


def test_바꿀_후보가_모두_그_시간에_닫으면_그대로_두고_위반이_남는다():
    cands = only(sight("g0", hours="11:00~20:00"), food("f0"), sight("g1"), sight("g2"), food("f1"), sight("x", hours="12:00~20:00"))
    course = {"days": [day(BASIC)]}
    fixed, replaced = fix(course, cands)
    assert replaced == [] and fixed == course and [v[0] for v in vio(fixed, cands)] == ["hours_closed"]


def test_시간_정보를_모르는_후보는_바꿔_넣을_수_있다():
    cands = world(sight("g0", hours="11:00~20:00"), sight("u", lon=128.91, hours=None))
    for h in (None, ""):
        cands["u"]["hours_text"] = h
        fixed, replaced = fix({"days": [day(BASIC)]}, cands)
        assert [r["id"] for r in replaced] == ["u"]


def test_다른_규칙으로_바꿔_넣는_장소도_시간이_맞아야_한다():
    cands = only(sight("g0"), food("f0"), sight("g1", hours="09:00~20:00"), sight("g2"), food("f1"), sight("near", lon=128.915, hours="09:00~12:00"), sight("ok", lon=128.96))   # 오후 칸을 내려간 장소로 바꾼다
    rechecked = {"g1": {"source": "live", "as_of": "x", "withdrawn": True, "place": {}}}
    hours = {i: c["hours_text"] for i, c in cands.items()}
    fixed, replaced = repair_slots({"days": [day(BASIC)]}, cands, [D1], rechecked, "강릉", None, None, None, None, hours)
    assert [r["id"] for r in replaced] == ["ok"] and replaced[0]["rule"] == "withdrawn"   # near 는 오후 14:30 에 이미 닫는다


# --- 재배열 ---
def far_world(g0="09:00~22:00", g1="09:00~22:00"):
    # 오전 g0(0) · 점심 f0(.02) · 오후 g1(.10 멀다) · 늦은 오후 g2(.03) · 저녁 f1(.04). 시간 제약이 없으면 하루 전체를 거꾸로 놓은 배치가 가장 짧다
    return {c["id"]: c for c in [sight("g0", 128.90, hours=g0), food("f0", 128.92), sight("g1", 129.00, hours=g1), sight("g2", 128.93), food("f1", 128.94)]}


order = lambda slots_: [s["content_id"] for s in slots_]
hours_map = lambda cands: {i: c["hours_text"] for i, c in cands.items()}
REVERSED = ["g1", "f1", "g2", "g0", "f0"]


def test_재배열은_시간_정보가_없으면_예전처럼_가까운_순서로_바꾼다():
    cands = far_world()
    s = slots(BASIC)
    new, changed = reorder_day(s, cands, 25)
    assert changed and order(new) == REVERSED
    assert reorder_day(s, cands, 25, None) == (new, True) and reorder_day(s, cands, 25, hours_map(cands)) == (new, True)   # 시간 정보가 있어도 충돌이 없으면 같다
    unknown = {i: None for i in cands}
    assert reorder_day(s, cands, 25, unknown) == (new, True)


def test_재배열이_새_시간_충돌을_만들면_그_배치는_고르지_않는다():
    cands = far_world(g1="12:00~16:00")   # g1 은 오후 칸(14:30)에서만 열려 있다: 오전 · 늦은 오후로 옮기면 충돌
    s = slots(BASIC)
    new, changed = reorder_day(s, cands, 25, hours_map(cands))
    assert not changed and new is s


def test_원래_있던_충돌이_같은_칸에_남는_배치는_허용한다():
    cands = far_world(g0="11:00~11:30")   # 오전 g0 는 원래 충돌이고 어느 칸으로 옮겨도 닫는다. 오전에 두고 g1 · g2 만 맞바꾸는 배치는 고른다
    new, changed = reorder_day(slots(BASIC), cands, 25, hours_map(cands))
    assert changed and order(new) == ["g0", "f0", "g2", "g1", "f1"]


def test_재배열이_충돌을_옮기거나_새로_만들면_막는다():
    cands = far_world(g0="11:00~11:30", g1="09:00~16:00")   # g1 을 늦은 오후로 옮기는 배치도, g0 를 옮기는 배치도 새 충돌
    assert reorder_day(slots(BASIC), cands, 25, hours_map(cands))[1] is False


def test_재배열이_충돌을_없애는_배치는_허용한다():
    cands = far_world(g0="11:00~20:00")   # g0 는 오전에 닫지만 늦은 오후에는 연다: 거꾸로 놓으면 충돌이 사라진다
    new, changed = reorder_day(slots(BASIC), cands, 25, hours_map(cands))
    assert changed and order(new) == REVERSED


# --- 노드(validate_course) ---
def node_state(course, cands, **kw):
    return {"course": course, "candidates": list(cands.values()), "request": {"region": "강릉", "start_date": D1, "days": 1}, "retries": {"draft": 1}, **kw}


def run(stored, state, detail=None):
    return validate_update(stored, detail, Trace(save=False))(state)


def test_새_요청은_충돌_초안을_바로_바꿔_시간이_맞는_코스로_낸다():
    cands = world(sight("g0", hours="11:00~20:00"))
    out = run(cands, node_state({"days": [day(BASIC)]}, cands))
    assert out["violations"] == [] and [r["rule"] for r in out["replaced"]] == ["hours_closed"]
    assert out["course"]["days"][0]["slots"][0]["content_id"] != "g0"


def test_다시_받은_이용시간이_저장분보다_우선한다():
    cands = world()   # 저장분은 모두 연다
    live = lambda cid: {"ok": True, "source": "live", "as_of": "2026-11-19", "withdrawn": False, "note": "",
                        "place": {"hours_text": "11:00~20:00" if cid == "g0" else OPEN}}
    out = run(cands, node_state({"days": [day(BASIC)]}, cands, retries={"draft": config.MAX_REDRAFTS + 1}), detail=live)
    assert [r["rule"] for r in out["replaced"]] == ["hours_closed"] and out["replaced"][0]["old_id"] == "g0"
    assert out["rechecked"]["g0"]["place"]["hours_text"] == "11:00~20:00"


def test_다시_받지_못하면_저장분_이용시간을_쓴다():
    cands = world(sight("g0", hours="11:00~20:00"))
    detail = lambda cid: {"ok": False, "reason": "한도"}
    out = run(cands, node_state({"days": [day(BASIC)]}, cands), detail=detail)
    assert out["violations"] == [] and [r["rule"] for r in out["replaced"]] == ["hours_closed"]


def test_수정_턴은_시간_충돌을_보지_않아_요청하지_않은_칸을_바꾸지_않는다():
    cands = world(sight("g0", hours="11:00~20:00"))
    for retries in ({"draft": 1}, {"draft": config.MAX_REDRAFTS + 1}):
        out = run(cands, node_state({"days": [day(BASIC)]}, cands, mode="edit", retries=retries))
        assert out["violations"] == [] and out["replaced"] == [] and "course" not in out and not out.get("removed")


def test_재작성을_다_써도_바꿀_후보가_없으면_칸을_비우지_않고_위반만_남긴다():
    cands = {c["id"]: c for c in [sight("g0", hours="11:00~20:00"), food("f0"), sight("g1"), sight("g2"), food("f1")]}
    out = run(cands, node_state({"days": [day(BASIC)]}, cands, retries={"draft": config.MAX_REDRAFTS + 1}))
    assert [v["rule"] for v in out["violations"]] == ["hours_closed"] and not out.get("removed")
    assert len(out.get("course", {"days": [day(BASIC)]})["days"][0]["slots"]) == 5


def test_다시_쓸_수_있는_동안은_바꿀_후보가_없으면_재작성으로_간다():
    cands = {c["id"]: c for c in [sight("g0", hours="11:00~20:00"), food("f0"), sight("g1"), sight("g2"), food("f1")]}
    state = node_state({"days": [day(BASIC)]}, cands)
    out = run(cands, state)
    assert [v["rule"] for v in out["violations"]] == ["hours_closed"] and "course" not in out
    assert after_validate({**state, **out}) == "draft_course"


def test_시간_정보가_없는_코스는_결과가_이전과_같다():
    cands = {c["id"]: {k: v for k, v in c.items() if k != "hours_text"} for c in world().values()}
    out = run(cands, node_state({"days": [day(BASIC)]}, cands))
    assert out["violations"] == [] and out["replaced"] == []
    assert {s["content_id"] for s in out["course"]["days"][0]["slots"]} == set(BASIC)   # 거리 재배열로 순서만 바뀔 수 있고, 시간 때문에 바뀐 장소는 없다


def test_설정이_연결돼_있다():
    assert "hours_closed" in config.REPAIR_RULES and "hours_closed" in config.SOFT_RULES and config.REPAIR_WHY["hours_closed"]
    assert set(config.COURSE_SLOTS_WITH_CAFE) <= set(config.SLOT_MINUTES)


# --- 품질 지표 ---
def test_hours_fit은_판정_가능_충돌_판정_불가_칸을_센다():
    places = {"a": sight("a", hours="11:00~20:00"), "b": sight("b"), "c": sight("c", hours="공연 별로 상이함"), "d": food("d", hours="17:00~22:00"), "e": food("e", hours=None)}
    course = [{"date": D1, "slots": [{"slot": s, "id": i, "title": f"장소{i}"} for s, i in zip(config.COURSE_SLOTS, "abcde")]}]
    got = hours_fit(course, places)
    # 오전 a(충돌) · 점심 b(열림) · 오후 c(불가) · 늦은 오후 d(17시 개장이라 충돌) · 저녁 e(정보 없음 → 불가)
    assert (got["slots"], got["judged"], got["closed"], got["unknown"]) == (5, 3, 2, 2) and got["closed_ratio"] == round(2 / 3, 3)
    assert got["judged"] + got["unknown"] == got["slots"] and len(got["examples"]) == 2 and "공연" not in str(got)   # 원문 문장은 옮기지 않는다


def test_hours_fit은_사본에_없는_장소와_모르는_칸을_판정_불가로_센다():
    course = [{"date": D1, "slots": [{"slot": "오전", "id": "zz", "title": "?"}, {"slot": "새벽", "id": "a", "title": "a"}]}]
    got = hours_fit(course, {"a": sight("a")})
    assert (got["slots"], got["judged"], got["closed"], got["unknown"], got["closed_ratio"]) == (2, 0, 0, 2, None)
    assert hours_fit([], {})["closed_ratio"] is None


def test_course_quality에_시간_지표가_들어간다():
    places = {i: sight(i) for i in "abc"}
    turn = {"kind": "course", "course": [{"date": D1, "slots": [{"slot": "오전", "id": "a", "title": "a"}]}], "message": "x", "request": {}}
    assert course_quality([turn], places)["hours"]["judged"] == 1
