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
    c["days"][1]["slots"][3]["content_id"] = "c0"   # 저녁(중복도 걸린다)
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
