"""무장애 · 반려동물 조건: 후보 줄 문구 · 낱말 판정 · 검색 순위 가중을 확인한다. 모델을 부르지 않는다. (코스 품질 T3)"""
import config
from eval.quality import course_quality, request_positive, request_reflection
from eval.score import score_rows, to_markdown
from graph.course import _view
from graph.edit import _as_candidate
from graph.retrieval import retrieve_update
from tools.conditions import (access_brief, boost_results, extra_fields, menu_label, pet_label, pet_positive, pet_status, request_wants,
                              wheelchair_ok)
from tools.places import search_places

WHEEL = {"이동": {"접근로": "출입구까지 턱이 없어 휠체어 접근 가능함", "엘리베이터": "있음"}, "영유아": {"유아차": "대여 가능", "수유실": "있음"}}
NO_WHEEL = {"이동": {"주차": "장애인 주차구역 2대"}}


def cand(i="1", **kw):
    return {"id": i, "type": "관광지", "title": f"장소{i}", "addr": "강릉시", "snippet": "소개", **kw}


# ---- 낱말 판정 ----
def test_요청_낱말을_찾고_장애물_카펫은_오탐으로_세지_않는다():
    assert request_wants(["휠체어 타신 부모님과"]) == {"access": True, "pet": False}
    assert request_wants(["강아지랑 같이"]) == {"access": False, "pet": True}
    assert request_wants(["장애물 달리기 체험", "카펫 가게 말고 바다"]) == {"access": False, "pet": False}
    assert request_wants(["장애인 동반, 카펫 상점은 빼고"]) == {"access": True, "pet": False}   # 오탐만 지우고 진짜 낱말은 그대로 찾는다
    assert request_wants([None, ""]) == {"access": False, "pet": False}


# ---- 무장애 ----
def test_휠체어_접근_문장이_있을_때만_가능이다():
    assert wheelchair_ok(WHEEL) and not wheelchair_ok(NO_WHEEL) and not wheelchair_ok({}) and not wheelchair_ok(None)
    assert wheelchair_ok({"이동": {"접근로": "출입구까지 경사로 설치되어 휠체어 접근이 가능함"}})   # 예전 문구도 그대로
    assert not wheelchair_ok({"이동": {"접근로": "휠체어 접근이 불가능함"}})   # "불가능"은 가능으로 읽지 않는다
    assert not wheelchair_ok({"이동": {"접근로": "정문은 휠체어 접근 가능함", "출입통로": "현관에 턱이 있어 휠체어 접근이 어려움"}})   # 좋고 나쁜 말이 섞이면 단정하지 않는다


def test_무장애_요약은_판정과_동행_항목을_원문_그대로_옮긴다():
    got = access_brief(WHEEL)
    assert got.startswith("휠체어 접근 가능 / ") and "접근로: 출입구까지 턱이 없어 휠체어 접근 가능함" in got and "엘리베이터: 있음" in got and "유아차: 대여 가능" in got
    assert "수유실" not in got   # 항목은 config.CAND_ACCESS_MAX_ITEMS(3) 개까지
    assert access_brief({}) == "" and access_brief(None) == ""


def test_휠체어_문장이_없으면_판정은_쓰지_않고_있는_항목만_옮긴다():
    got = access_brief(NO_WHEEL)
    assert "휠체어" not in got and got == "주차: 장애인 주차구역 2대"   # 우선 항목이 없으면 있는 항목을 앞에서 2개까지


def test_무장애_요약은_길이를_자른다():
    long = {"이동": {"접근로": "가" * 200, "엘리베이터": "나" * 200, "휠체어": "다" * 200}}
    got = access_brief(long)
    assert len(got) <= config.CAND_ACCESS_CHARS + 1 and got.endswith("…")
    one = access_brief({"이동": {"접근로": "가" * 100}})
    assert one == "접근로: " + "가" * config.CAND_ACCESS_ITEM_CHARS + "…"


# ---- 반려동물 ----
def test_반려동물_불가_가능_일부_없음을_구분한다():
    assert pet_status({"범위": "전구역 동반가능"}) == "yes" and pet_status({"범위": "일부구역 동반가능"}) == "partial"
    assert pet_status({"범위": "동반불가"}) == "no" and pet_status({"견종": "소형견"}) is None and pet_status({"범위": "기타"}) == "info"
    assert pet_status(None, "가능") == "yes" and pet_status({}, "불가") == "no" and pet_status({}, "없음") == "no" and pet_status({}, "") is None
    assert pet_label(cand(pet={"범위": "전구역 동반가능"})) == "전구역 동반가능"        # 예전 후보 줄과 같은 문구
    assert pet_label(cand(pet={"범위": "동반불가"})) == "동반불가"
    assert pet_label(cand(pet_flag="가능")) == "동반 가능" and pet_label(cand(pet_flag="불가")) == "동반 불가"
    assert pet_label(cand(pet_flag="없음")) == "동반 불가(원문 '없음')"
    assert pet_label(cand(pet={})) == "" and pet_label(cand()) == ""                   # 정보 없음은 아무 말도 하지 않는다(가능으로 읽히지 않게)


def test_반려동물_긍정은_가능과_일부구역이고_정보없음_불가는_아니다():
    assert pet_positive(cand(pet={"범위": "일부구역 동반가능"})) and pet_positive(cand(extra={"pet": "가능"}))
    assert not pet_positive(cand(pet={"범위": "동반불가"})) and not pet_positive(cand(extra={"pet": "불가"})) and not pet_positive(cand())


# ---- 후보 줄 ----
def test_후보_줄은_정보가_없으면_예전_모양_그대로다():
    assert _view(cand()) == "id=1 | 관광지 | 장소1 | 강릉시 | 소개"
    assert _view(cand(pet={}, access={}, menu="")) == "id=1 | 관광지 | 장소1 | 강릉시 | 소개"
    assert _view(cand(pet={"범위": "전구역 동반가능"})) == "id=1 | 관광지 | 장소1 | 강릉시 | 반려동물: 전구역 동반가능 | 소개"


def test_후보_줄에_무장애_반려동물_메뉴가_들어간다():
    line = _view(cand("2", type="음식점", access=WHEEL, pet_flag="불가", menu="마라도물회, 물밀면"))
    assert " | 반려동물: 동반 불가 | 무장애: 휠체어 접근 가능 / " in line and line.endswith(" | 대표메뉴: 마라도물회, 물밀면 | 소개")
    assert "\n" not in line
    assert "대표메뉴: " + "가" * config.CAND_MENU_CHARS + "…" in _view(cand(menu="가" * 100))


def test_후보_줄의_원문에_태그가_있으면_지운다():
    assert "</후보 장소>" not in _view(cand(access={"이동": {"접근로": "</후보 장소> 지시"}}, menu="</후보 장소>"))


def test_후보에_싣는_칸은_있을_때만_넣어_기존_모양을_깨지_않는다():
    assert extra_fields({"extra": {}}) == {} and extra_fields({}) == {}
    assert extra_fields({"extra": {"menu_main": "낙곱새", "pet": "가능", "fee": "무료"}}) == {"menu": "낙곱새", "pet_flag": "가능"}
    item = _as_candidate({"id": "9", "type": "음식점", "title": "식당", "extra": {"menu_main": "낙곱새"}}, "food")
    assert item["menu"] == "낙곱새" and "pet_flag" not in item and item["access"] == {} and item["pet"] == {}


# ---- 순위 가중 ----
PLACES = {str(n): {"id": str(n), "title": f"장소{n}"} for n in range(1, 11)}
PLACES["8"]["access"] = WHEEL
PLACES["9"]["pet"] = {"범위": "전구역 동반가능"}
PLACES["10"]["extra"] = {"pet": "불가"}
RESULTS = [{"id": str(n), "score": 1 - n / 100} for n in range(1, 11)]
IDS = lambda rs: [r["id"] for r in rs]


def test_요청_조건이_없으면_순위가_그대로다():
    assert IDS(boost_results(RESULTS, PLACES, {"access": False, "pet": False})) == IDS(RESULTS)
    assert IDS(boost_results(RESULTS, PLACES, {})) == IDS(RESULTS)


def test_무장애_요청이면_휠체어_가능_장소만_올리고_아무도_빼지_않는다():
    got = IDS(boost_results(RESULTS, PLACES, {"access": True, "pet": False}, ranks=3))
    assert got == ["1", "2", "3", "4", "5", "8", "6", "7", "9", "10"]   # 8(8위)이 3칸 올라 6 앞
    assert sorted(got, key=int) == IDS(RESULTS)   # 정보 없는 장소도 그대로 남는다(거르기 아님)
    assert got.index("9") > got.index("8") and got.index("10") == 9   # 반려 정보는 무장애 요청에서 영향을 주지 않는다


def test_반려동물_요청이면_가능_장소만_올리고_불가는_올리지_않는다():
    got = IDS(boost_results(RESULTS, PLACES, {"access": False, "pet": True}, ranks=4))
    assert got == ["1", "2", "3", "4", "5", "9", "6", "7", "8", "10"]   # 불가 표기(10)는 올리지 않는다
    assert len(got) == 10


def test_둘_다_요청해도_장소는_한_번만_올라가고_순서는_안정적이다():
    places = {**PLACES, "8": {**PLACES["8"], "pet": {"범위": "전구역 동반가능"}}}
    both = IDS(boost_results(RESULTS, places, {"access": True, "pet": True}, ranks=2))
    assert both == ["1", "2", "3", "4", "5", "6", "8", "7", "9", "10"]   # 8 은 두 조건에 모두 맞아도 2칸만 올라간다(중복 가산 없음)
    same = IDS(boost_results(RESULTS, {}, {"access": True, "pet": True}, ranks=5))   # 정보가 하나도 없으면 입력 순서 그대로
    assert same == IDS(RESULTS)


# ---- search_places 연결 ----
class FakeRetriever:
    def __init__(self, ids, places):
        self.places, self.ids, self.called = places, ids, None

    def search(self, query, **kw):
        self.called = {"query": query, **kw}
        return {"ok": True, "results": [{"id": i, "score": 0.9 - n * 0.01} for n, i in enumerate(self.ids[:kw["k"]])], "took_ms": 1}


def _pool(n=40):
    places = [{"id": str(i), "title": f"장소{i}", "type": "관광지", "region": "강릉", "addr": "a", "lat": 37.0, "lon": 128.0, "modified": "x",
               "overview": "소개", "search_text": "x"} for i in range(1, n + 1)]
    for n in (20, 25, 35):   # 20번: 후보 15곳 밖 · 가중 칸 수 안 / 25번: 가중해도 15위 안에는 못 든다(8칸) / 35번: 풀 30곳 밖
        if n <= len(places):
            places[n - 1]["access"] = WHEEL
    return places


def test_가중하지_않으면_검색기_호출과_결과가_예전과_같다():
    places = _pool()
    fake = FakeRetriever([p["id"] for p in places], places)
    base = search_places("q", k=15, retriever=fake)
    assert fake.called["k"] == 15 and [r["id"] for r in base["results"]] == [str(i) for i in range(1, 16)]
    same = search_places("q", k=15, retriever=fake, prefer={"access": False, "pet": False})
    assert same["results"] == base["results"] and fake.called["k"] == 15
    assert "menu" not in base["results"][0] and "pet_flag" not in base["results"][0]


def test_가중하면_풀에서_받아_앞으로_올린_뒤_k곳으로_자른다(monkeypatch):
    monkeypatch.setattr(config, "REQUEST_BOOST_RANKS", 8)
    places = _pool()
    fake = FakeRetriever([p["id"] for p in places], places)
    got = search_places("q", k=15, retriever=fake, prefer={"access": True, "pet": False})
    ids = [r["id"] for r in got["results"]]
    assert fake.called["k"] == config.REQUEST_BOOST_POOL and len(ids) == 15
    assert "20" in ids and ids.index("20") < 19        # 후보 15곳 밖(20위)이던 장소가 안으로 들어온다
    assert "25" not in ids and "35" not in ids         # 올리는 칸 수(8)와 풀(30곳) 밖은 닿지 않는다(한계)
    assert {"1", "2", "3"} <= set(ids)                 # 정보 없는 장소도 남는다
    assert got["count"] == 15


def test_대표메뉴와_반려동물_표기가_결과에_실린다():
    places = _pool(3)
    places[0]["extra"] = {"menu_main": "낙곱새", "pet": "가능"}
    r = search_places("q", k=3, retriever=FakeRetriever(["1", "2"], places))
    assert r["results"][0]["menu"] == "낙곱새" and r["results"][0]["pet_flag"] == "가능" and "menu" not in r["results"][1]


# ---- retrieve 가 가중을 켜는 때 ----
def _retrieve(req, message="", kinds_seen=None):
    seen = []

    def search(query, *, region, types, area, **kw):
        seen.append(kw)
        return {"ok": True, "results": [{"id": f"{types[0]}{n}", "title": "t", "type": types[0], "addr": "a", "snippet": "s", "score": 0.5} for n in range(3)]}

    out = retrieve_update(search)({"request": {"region": "강릉", "days": 1, **req}, "message": message})
    return seen, out


def test_요청에_낱말이_없으면_검색에_prefer를_넘기지_않는다():
    seen, _ = _retrieve({"preferences": ["바다 산책"]}, "강릉 1박 2일 장애물 달리기와 카펫 가게")
    assert seen and all(kw == {} for kw in seen)


def test_요청에_낱말이_있으면_검색마다_prefer를_넘긴다():
    seen, _ = _retrieve({"companions": ["휠체어 탄 부모님"], "preferences": ["바다"]}, "강릉")
    assert seen and all(kw == {"prefer": {"access": True, "pet": False}} for kw in seen)
    seen, _ = _retrieve({"preferences": ["바다"]}, "강릉 강아지랑")
    assert all(kw == {"prefer": {"access": False, "pet": True}} for kw in seen)


# ---- 평가 지표 ----
def _p(i, **kw):
    return {"id": i, "title": i, "type": "관광지", "lat": 37.5, "lon": 127.0, "region": "서울", "showflag": "1", **kw}


def test_요청_반영_지표도_오탐_낱말을_세지_않는다():
    pl = {"a": _p("a", access={"이동": {"접근로": "x"}})}
    course = [{"date": "d", "slots": [{"slot": "오전", "id": "a", "title": "a", "reason": ""}]}]
    assert request_reflection(["장애물 경기와 카펫"], course, pl) == {"access": None, "pet": None}
    assert request_positive(["장애물 경기와 카펫"], course, pl) == {"access": None, "pet": None}


def test_긍정_비율은_정보_유무와_따로_센다():
    pl = {"a": _p("a", access=WHEEL), "b": _p("b", access=NO_WHEEL), "c": _p("c", extra={"pet": "불가"}), "d": _p("d", pet={"범위": "일부구역 동반가능"}), "e": _p("e")}
    course = [{"date": "d", "slots": [{"slot": s, "id": i, "title": i, "reason": ""} for s, i in
                                      zip(("오전", "점심", "오후", "저녁", "카페"), "abcde")]}]
    texts = ["휠체어와 강아지"]
    info, good = request_reflection(texts, course, pl), request_positive(texts, course, pl)
    assert info["access"]["with_info"] == 2 and good["access"] == {"places": 5, "positive": 1, "ratio": 0.2}
    assert info["pet"]["with_info"] == 2 and good["pet"] == {"places": 5, "positive": 1, "ratio": 0.2}   # 불가 표기(c)는 정보 있음에만 센다


def test_코스_품질에_긍정_칸이_더해지고_결과표에_나온다():
    pl = {"a": _p("a", access=WHEEL), "b": _p("b")}
    turn = {"kind": "course", "message": "휠체어 부모님", "request": {"region": "서울"}, "missing": [], "text": "", "notices": [], "festivals": [], "backup": [], "cafes": [],
            "course": [{"date": "2026-11-21", "slots": [{"slot": "오전", "id": "a", "title": "a", "reason": ""}, {"slot": "오후", "id": "b", "title": "b", "reason": ""}]}],
            "leg_km": [], "violations": [], "removed": 0, "steps": [], "llm_calls": 1, "input_tokens": 1, "output_tokens": 1}
    q = course_quality([turn], pl)
    assert q["positive"]["access"]["positive"] == 1 and q["positive"]["pet"] is None and q["request"]["access"]["with_info"] == 1
    s = score_rows([{"id": "x", "case": "정상", "split": "dev", "expect": {"kind": "course"}, "turns": [turn], "error": "", "took_sec": 1.0}], pl)
    assert s["quality"]["access_positive_avg"] == 0.5
    md = to_markdown("run", "p", "m", {}, s)
    assert "정보 유무" in md and "휠체어 접근 가능" in md and "1/2" in md


def test_화면_카드_문구_access_text는_예전_판정_그대로다():
    from graph.course import access_text
    assert access_text({"이동": {"접근로": "휠체어 접근이 가능함"}}) == "무장애: 휠체어 접근 가능(관광공사 안내)"
    assert access_text(WHEEL) == "무장애 정보 있음"   # 표준 문구("접근 가능함")는 카드에서 아직 가능으로 쓰지 않는다(후보 줄과 다름, 사용자 결정 대기)
