"""코스 안 식당 대표메뉴 겹침(menu_duplicate)을 찾고 코드가 다른 식당으로 바꾸는지 가짜 데이터로 확인한다 (코스 품질 T2). 네트워크 · 모델을 쓰지 않는다."""
import config
from graph.menu import place_menu_keywords
from graph.validate import find_violations, repair_slots, validate_update
from harness.trace import Trace

D1, D2 = "2026-11-21", "2026-11-22"


def place(i, kind, type_, lon=128.90, **kw):
    return {"id": i, "kind": kind, "type": type_, "title": f"장소{i}", "addr": "강릉시", "lat": 37.7, "lon": lon, "snippet": "소개", **kw}


def food(i, menu, lon=128.90, **kw):
    return place(i, "food", "음식점", lon=lon, extra={"menu_main": menu}, **kw)


def slots(ids):
    return [{"slot": n, "content_id": i, "reason": "r"} for n, i in zip(config.COURSE_SLOTS, ids)]


def world(*foods, extra_sights=()):
    rows = [place(f"g{n}", "sight", "관광지", lon=128.90 + n * 0.01) for n in range(6)] + list(extra_sights) + list(foods)
    return {c["id"]: c for c in rows}


def menus_of(cands):
    return {i: kw for i, c in cands.items() if (kw := place_menu_keywords(c))}


def one_day(lunch, dinner):   # 오전 g0 · 점심 · 오후 g1 · 늦은 오후 g2 · 저녁
    return {"days": [{"date": D1, "slots": slots(["g0", lunch, "g1", "g2", dinner])}]}


def vio(course, cands, dates=(D1,), menus="auto", slot_names=None):
    menus = menus_of(cands) if menus == "auto" else menus
    return [(v["rule"], v["id"], v["date"], v["slot"]) for v in find_violations(course, cands, list(dates), {}, "강릉", slot_names, None, menus)]


# --- 판정 ---
def test_대표메뉴가_겹치면_뒤에_나온_칸을_위반으로_표시한다():
    cands = world(food("a", "물회, 물밀면"), food("b", "물회 / 곰탕"), food("c", "곰탕"))
    got = vio(one_day("a", "b"), cands)
    assert got == [("menu_duplicate", "b", D1, "저녁")]   # 먼저 나온 점심 a 는 두고 뒤의 저녁 b 만


def test_메뉴가_겹치지_않으면_위반이_없다():
    cands = world(food("a", "물회"), food("b", "곰탕"))
    assert vio(one_day("a", "b"), cands) == []


def test_메뉴_정보가_없는_식당은_위반으로_보지_않는다():
    cands = world(food("a", "물회"), place("b", "food", "음식점"), food("c", ""), food("d", "세트"))   # 없음 · 빈 문장 · 흔한 말(불용어)만
    for other in ("b", "c", "d"):
        assert vio(one_day("a", other), cands) == []
    assert vio(one_day("a", "b"), cands, menus=None) == []   # 메뉴 정보를 주지 않으면 규칙을 켜지 않는다


def test_카페는_메뉴가_겹쳐도_보지_않는다():
    cands = world(food("a", "아메리카노"), food("b", "곰탕"), food("cf", "아메리카노", is_cafe=True), food("cf2", "아메리카노", is_cafe=True))
    # 카페 칸의 카페 · 식사 칸에 잘못 들어간 카페 모두 메뉴 겹침으로 세지 않는다(식사 칸의 카페는 cafe_meal 위반만)
    names = ["오전", "점심", "카페", "오후", "늦은 오후", "저녁"]
    course = {"days": [{"date": D1, "slots": [{"slot": n, "content_id": i, "reason": "r"} for n, i in zip(names, ["g0", "a", "cf", "g1", "g2", "b"])]}]}
    assert "menu_duplicate" not in [r for r, *_ in vio(course, cands, slot_names=config.COURSE_SLOTS_WITH_CAFE)]
    got = vio(one_day("a", "cf2"), cands)
    assert ("cafe_meal", "cf2", D1, "저녁") in got and not [g for g in got if g[0] == "menu_duplicate"]


def test_여러_날에_걸친_겹침은_뒤_날의_칸을_위반으로_표시한다():
    cands = world(food("a", "칼국수"), food("b", "곰탕"), food("c", "칼국수 · 수제비"), food("d", "순두부"), extra_sights=[place("g6", "sight", "관광지")])
    course = {"days": [{"date": D1, "slots": slots(["g0", "a", "g1", "g2", "b"])}, {"date": D2, "slots": slots(["g3", "c", "g4", "g5", "d"])}]}
    assert vio(course, cands, dates=(D1, D2)) == [("menu_duplicate", "c", D2, "점심")]


def test_같은_장소가_두_번이면_duplicate_만_걸리고_메뉴_위반은_더하지_않는다():
    cands = world(food("a", "물회"))
    got = vio(one_day("a", "a"), cands)
    assert [g[0] for g in got] == ["duplicate"]


def test_메뉴_겹침이_없는_코스의_검증_결과는_메뉴_정보를_줘도_같다():
    cands = world(food("a", "물회"), food("b", "곰탕"), place("g6", "sight", "관광지", lon=129.60))   # 거리 위반 등 다른 위반이 있어도
    c = {"days": [{"date": D1, "slots": slots(["g0", "a", "g6", "g2", "b"])}]}
    assert vio(c, cands, menus="auto") == vio(c, cands, menus=None) and vio(c, cands)   # 비어 있지 않은 목록이 똑같다


# --- 고치기 ---
def fix(course, cands, **kw):
    return repair_slots(course, cands, [D1], {}, "강릉", None, None, kw.get("rest"), menus_of(cands))


def test_겹치는_칸은_다른_메뉴의_가장_가까운_식당으로_바꾸고_새_위반이_없다():
    # near 는 가깝지만 점심 a 와 메뉴가 같아 고르지 않고, 그다음으로 가까운 mid(다른 메뉴)를 고른다
    cands = world(food("a", "물회", lon=128.90), food("b", "물회", lon=128.91), food("near", "물회 · 막국수", lon=128.92), food("mid", "곰탕", lon=128.95), food("far", "칼국수", lon=128.99))
    course = one_day("a", "b")
    fixed, replaced = fix(course, cands)
    assert replaced == [{"date": D1, "slot": "저녁", "old_id": "b", "id": "mid", "rule": "menu_duplicate"}]
    assert vio(fixed, cands) == [] and fixed["days"][0]["slots"][4]["reason"] == config.REPLACED_REASON
    assert course["days"][0]["slots"][4]["content_id"] == "b"   # 원본은 그대로


def test_바꿔_넣을_후보가_메뉴를_모르면_겹침으로_단정하지_않고_쓸_수_있다():
    cands = world(food("a", "물회"), food("b", "물회", lon=128.91), place("u", "food", "음식점", lon=128.92))
    fixed, replaced = fix(one_day("a", "b"), cands)
    assert [r["id"] for r in replaced] == ["u"]


def test_바꿀_후보가_없으면_그대로_두고_위반이_남는다():
    cands = world(food("a", "물회"), food("b", "물회", lon=128.91), food("c", "물회 · 회", lon=128.92))   # 쓸 수 있는 다른 식당이 모두 같은 메뉴
    course = one_day("a", "b")
    fixed, replaced = fix(course, cands)
    assert replaced == [] and fixed == course and [g[0] for g in vio(fixed, cands)] == ["menu_duplicate"]


def test_다른_규칙으로_바꿔_넣는_식당도_앞_식당과_메뉴가_겹치지_않는다():
    # 저녁 b 가 휴무라 바꿔야 하는데 가장 가까운 near 는 점심 a 와 메뉴가 같다 → 건너뛰고 다른 것을 고른다
    cands = world(food("a", "물회"), food("b", "곰탕", lon=128.91), food("near", "물회", lon=128.92), food("ok", "칼국수", lon=128.95))
    rest = {"b": {D1: "closed"}}
    rechecked = {"b": {"source": "live", "as_of": "x", "withdrawn": True, "place": {}}}   # 내려간 장소(withdrawn)로 바꿀 이유를 만든다
    fixed, replaced = repair_slots(one_day("a", "b"), cands, [D1], rechecked, "강릉", None, None, rest, menus_of(cands))
    assert [r["id"] for r in replaced] == ["ok"] and replaced[0]["rule"] == "withdrawn"


def test_취향_반복과_메뉴_겹침이_같은_칸에_함께_걸려도_그_칸을_한_번만_바꾼다():
    # b0(점심)와 b1(저녁)이 둘 다 취향 음식(theme)이고 메뉴도 같다: 저녁 칸에 theme_repeat · menu_duplicate 가 함께 걸린다.
    cands = world(food("b0", "닭강정", theme=True), food("b1", "닭강정", lon=128.91, theme=True), food("o0", "곰탕", lon=128.92), food("o1", "순두부", lon=128.93), food("t2", "닭강정 세트", lon=128.915, theme=True))
    course = one_day("b0", "b1")
    got = vio(course, cands)
    assert ("theme_repeat", "b1", D1, "저녁") in got and ("menu_duplicate", "b1", D1, "저녁") in got
    fixed, replaced = fix(course, cands)
    assert len(replaced) == 1 and replaced[0]["slot"] == "저녁" and replaced[0]["id"] == "o0"   # 취향 음식이 아니고 메뉴도 다른 식당
    assert vio(fixed, cands) == []


# --- 노드(validate_course) ---
def node_state(course, cands, **kw):
    return {"course": course, "candidates": list(cands.values()), "request": {"region": "강릉", "start_date": D1, "days": 1}, "retries": {"draft": 1}, **kw}


def test_새_요청은_모자란_초안을_바로_바꿔_메뉴_겹침이_없는_코스로_낸다():
    cands = world(food("a", "물회"), food("b", "물회", lon=128.91), food("mid", "곰탕", lon=128.95))
    out = validate_update(cands, None, Trace(save=False))(node_state(one_day("a", "b"), cands))
    assert out["violations"] == [] and [r["id"] for r in out["replaced"]] == ["mid"]
    assert out["course"]["days"][0]["slots"][4]["content_id"] == "mid"


def test_수정_턴은_메뉴_겹침을_보지_않아_요청하지_않은_칸을_바꾸지_않는다():
    # 사용자가 "저녁도 물회로"처럼 같은 메뉴를 고를 수 있다. 수정 턴은 재작성을 다 써도 코드가 몰래 바꾸지 않는다
    cands = world(food("a", "물회"), food("b", "물회", lon=128.91), food("mid", "곰탕", lon=128.95))
    for retries in ({"draft": 1}, {"draft": config.MAX_REDRAFTS + 1}):
        out = validate_update(cands, None, Trace(save=False))(node_state(one_day("a", "b"), cands, mode="edit", retries=retries))
        assert out["violations"] == [] and out["replaced"] == [] and "course" not in out


def test_재작성을_다_써도_바꿀_후보가_없으면_칸을_비우지_않고_위반만_남긴다():
    cands = world(food("a", "물회"), food("b", "물회", lon=128.91))
    out = validate_update(cands, None, Trace(save=False))(node_state(one_day("a", "b"), cands, retries={"draft": config.MAX_REDRAFTS + 1}))
    assert [v["rule"] for v in out["violations"]] == ["menu_duplicate"] and not out.get("removed")
    kept = [s["content_id"] for s in out.get("course", one_day("a", "b"))["days"][0]["slots"]]
    assert len(kept) == 5 and "a" in kept and "b" in kept   # 칸 순서는 끝에서 거리 재배열이 바꿀 수 있어 구성만 본다


def test_다시_쓸_수_있는_동안은_바꿀_후보가_없으면_위반이_남아_재작성으로_간다():
    cands = world(food("a", "물회"), food("b", "물회", lon=128.91))
    out = validate_update(cands, None, Trace(save=False))(node_state(one_day("a", "b"), cands))
    assert [v["rule"] for v in out["violations"]] == ["menu_duplicate"] and out["replaced"] == [] and "course" not in out
    from graph.build import after_validate
    assert after_validate({**node_state(one_day("a", "b"), cands), **out}) == "draft_course"


def test_안내_문구가_있다():
    assert config.REPAIR_WHY["menu_duplicate"] and "menu_duplicate" in config.REPAIR_RULES and "menu_duplicate" in config.SOFT_RULES
