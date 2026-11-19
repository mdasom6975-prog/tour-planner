"""카페는 점심 · 저녁 칸이 아니라 '근처 카페 추천'으로 따로 둔다 (2026-11-13 결정). 네트워크 · 실제 모델을 쓰지 않는다."""
import config
from graph.course import pack_course, respond_update
from graph.retrieval import retrieve_update
from graph.schemas import Course
from graph.validate import find_violations
from tests.test_draft_respond import CANDS, D1, D2, WEATHER, course, place
from tests.test_validate import BY_ID, good

CAFES = [place(f"c{n}", "cafe", "음식점", is_cafe=True) for n in range(3)]
ALL = CANDS + CAFES


def test_점심_저녁에_카페가_들어가면_위반이다():
    c = good()
    by_id = {**BY_ID, "c0": place("c0", "cafe", "음식점", is_cafe=True)}
    c["days"][0]["slots"][1]["content_id"] = "c0"   # 점심
    c["days"][1]["slots"][4]["content_id"] = "c0"   # 저녁(중복도 걸린다)
    rules = [(v["rule"], v["slot"]) for v in find_violations(c, by_id, [D1, D2], {}, "강릉")]
    assert ("cafe_meal", "점심") in rules and ("cafe_meal", "저녁") in rules


def test_음식점_결과를_식당과_카페로_나누고_식당만_센다():
    def search(query, *, region, types, area):
        if types == config.FOOD_TYPES:
            rows = [{"id": f"f{n}", "title": f"식당{n}", "type": "음식점", "is_cafe": False} for n in range(12)]
            rows[1:1] = [{"id": f"c{n}", "title": f"카페{n}", "type": "음식점", "is_cafe": True} for n in range(4)]   # 위쪽에 카페가 섞여 있다
            return {"ok": True, "results": rows}
        return {"ok": True, "results": []}
    out = retrieve_update(search)({"request": {"region": "서울"}})
    kinds = {}
    for c in out["candidates"]:
        kinds.setdefault(c["kind"], []).append(c["id"])
    assert len(kinds["food"]) == config.SEARCH_K and not any(i.startswith("c") for i in kinds["food"])
    assert kinds["cafe"] == ["c0", "c1", "c2", "c3"]


def test_카페_추천은_카페_후보_안에서_본_코스와_겹치지_않게_정해진_수만():
    got = Course.model_validate({**course(), "cafes": [{"content_id": i, "reason": "r"} for i in ("c0", "f0", "zzz", "c0", "c1", "c2")]})
    packed = pack_course(got, [], CAFES)
    assert [c["content_id"] for c in packed["cafes"]] == ["c0", "c1"] and len(packed["cafes"]) == config.CAFE_PICKS


def test_답에_근처_카페_추천이_따로_나오고_칸에는_없다():
    cs = course()
    cs["cafes"] = [{"content_id": "c0", "reason": "산책 뒤 쉬기 좋음"}, {"content_id": "c1", "reason": "조용함"}]
    st = {"request": {"region": "강원", "start_date": D1, "days": 2}, "candidates": ALL, "weather": WEATHER, "festivals": {}, "course": cs,
          "rest_table": {"c1": {D2: "closed"}}}
    ans = respond_update(st)["answer"]
    assert [c["id"] for c in ans["cafes"]] == ["c0", "c1"]
    assert "## 근처 카페 추천" in ans["text"]
    assert any("휴무로 보임" in f for f in ans["cafes"][1]["facts"])      # 여행일 중 휴무로 보이는 날을 알린다
    assert all(s["id"] not in ("c0", "c1") for d in ans["days"] for s in d["slots"])


# --- 박물관류 1곳 제한 · 부가 코스 다양화 (2026-11-13 결정) -------------------------------------
def museum(i, **kw):
    return place(i, "sight", "문화시설", category=config.MUSEUM_CLASS, **kw)


def test_박물관류가_코스에_두_곳_이상이면_위반이다():
    c = good()
    by_id = {**BY_ID, "mu0": museum("mu0"), "mu1": museum("mu1")}
    c["days"][0]["slots"][0]["content_id"] = "mu0"
    c["days"][1]["slots"][0]["content_id"] = "mu1"
    got = [(v["rule"], v["id"]) for v in find_violations(c, by_id, [D1, D2], {}, "강릉")]
    assert ("museum_limit", "mu1") in got and ("museum_limit", "mu0") not in got   # 첫 곳은 허용, 두 번째부터 위반


def test_부가_코스는_본_코스와_합쳐_박물관류_1곳이고_카페가_섞인다():
    indoor = [museum("mu0"), museum("mu1"), place("v0", "sight", "문화시설", category="VE06")]
    cafes = [place("c0", "cafe", "음식점", is_cafe=True), place("c1", "cafe", "음식점", is_cafe=True)]
    base = course(days=[{"date": D1, "slots": [{"slot": "오전", "content_id": "mu0", "reason": "r"}]}], backup=())
    got = Course.model_validate({**base, "backup": [{"content_id": i, "reason": "r"} for i in ("mu1", "v0", "c0", "c1")], "cafes": [{"content_id": "c0", "reason": "r"}]})
    packed = pack_course(got, indoor, cafes)
    assert [b["content_id"] for b in packed["backup"]] == ["v0", "c1"]   # mu1: 본 코스에 이미 박물관 · c0: 카페 추천과 겹침
    only_backup = Course.model_validate({**base, "days": [], "backup": [{"content_id": i, "reason": "r"} for i in ("mu0", "mu1", "v0")]})
    assert [b["content_id"] for b in pack_course(only_backup, indoor, cafes)["backup"]] == ["mu0", "v0"]   # 박물관 하나만


def test_후보에_박물관류는_정해진_수까지만_남는다():
    def search(query, *, region, types, area):
        if types == config.INDOOR_TYPES:
            rows = [{"id": f"mu{n}", "title": f"박물관{n}", "type": "문화시설", "category": config.MUSEUM_CLASS} for n in range(8)]
            rows += [{"id": f"v{n}", "title": f"공연장{n}", "type": "문화시설", "category": "VE06"} for n in range(3)]
            return {"ok": True, "results": rows}
        return {"ok": True, "results": []}
    out = retrieve_update(search)({"request": {"region": "강릉"}})
    ids = [c["id"] for c in out["candidates"]]
    assert sum(i.startswith("mu") for i in ids) == config.MUSEUM_CANDIDATES and sum(i.startswith("v") for i in ids) == 3


# --- 카페 칸 (2026-11-16 결정: 커피 · 디저트 취향이면 하루에 카페 칸 하나) ---
def test_커피_취향이고_카페_후보가_일수만큼_있어야_카페_칸이_생긴다():
    from graph.state import slots_for, wants_cafe
    cafes = [{"id": f"c{n}", "kind": "cafe"} for n in range(2)]
    assert wants_cafe({"preferences": ["커피 좋아함"]}) and not wants_cafe({"preferences": ["바다"]}) and not wants_cafe({})
    assert slots_for({"preferences": ["디저트"], "days": 2}, cafes) == config.COURSE_SLOTS_WITH_CAFE
    assert slots_for({"preferences": ["디저트"], "days": 3}, cafes) == config.COURSE_SLOTS      # 카페 후보가 모자라면 늘리지 않는다
    assert slots_for({"preferences": ["바다"], "days": 1}, cafes) == config.COURSE_SLOTS        # 취향이 없으면 네 칸 그대로


def test_카페_칸은_카페만_받고_칸이_빠지면_위반이다():
    from graph.validate import find_violations
    cands = {c["id"]: c for c in [place("s0", "sight", "관광지"), place("s1", "sight", "관광지"), place("s2", "sight", "관광지"), place("f0", "food", "음식점", is_cafe=False),
                                  place("f1", "food", "음식점", is_cafe=False), place("c0", "cafe", "음식점", is_cafe=True)]}

    def course(names, ids):
        return {"days": [{"date": "2026-11-21", "slots": [{"slot": n, "content_id": i, "reason": "r"} for n, i in zip(names, ids)]}]}

    def rules(c, slots=config.COURSE_SLOTS_WITH_CAFE):
        return [v["rule"] for v in find_violations(c, cands, ["2026-11-21"], {}, "강릉", slots)]
    assert rules(course(config.COURSE_SLOTS_WITH_CAFE, ["s0", "f0", "c0", "s1", "s2", "f1"])) == []
    assert rules(course(config.COURSE_SLOTS_WITH_CAFE, ["s0", "f0", "f1", "s1", "s2", "f1"]))[0] == "cafe_slot"   # 카페 칸에 식당
    assert rules(course(config.COURSE_SLOTS, ["s0", "f0", "s1", "s2", "f1"])) == ["slots"]                         # 카페 칸이 빠짐
    assert rules(course(config.COURSE_SLOTS, ["s0", "f0", "s1", "s2", "f1"]), config.COURSE_SLOTS) == []      # 취향이 없으면 다섯 칸이 맞다
