"""코스 품질 지표(graph/menu.py, eval/quality.py)와 재배열 전 · 후 거리 기록을 확인한다. 모델을 부르지 않는다. (코스 품질 T1)"""
import config
from eval.quality import course_quality, day_km, day_shape, menu_duplicates, request_reflection, route_metrics
from eval.score import score_rows, to_markdown
from graph.menu import menu_keywords, menu_overlaps


def place(i, type_="관광지", lat=37.50, lon=127.0, **kw):
    return {"id": i, "title": f"장소{i}", "type": type_, "region": "서울", "lat": lat, "lon": lon, "showflag": "1",
            "rest_status": "none", "rest_weekdays": [], "rest_nth": [], **kw}


def food(i, menu, **kw):
    return place(i, "음식점", extra={"menu_main": menu}, **kw)


def slots(*pairs):
    return [{"slot": s, "id": i, "title": i, "reason": ""} for s, i in pairs]


# ---- 메뉴 키워드 ----
def test_메뉴_키워드는_구분자로_나누고_정규화한다():
    assert menu_keywords("마라도물회, 물밀면 / 소금빵 아이스크림") == {"마라도물회", "물밀면", "소금빵", "아이스크림"}
    assert menu_keywords("Americano·치즈(수제)") == {"americano", "치즈", "수제"}


def test_메뉴_키워드는_짧은_말_흔한_말_빈_값을_버린다():
    assert menu_keywords("면 / 한우 세트") == {"한우"}
    assert menu_keywords("") == set() and menu_keywords(None) == set() and menu_keywords(123) == set()


def test_메뉴_겹침은_쌍과_장소를_센다():
    got = menu_overlaps([food("a", "돼지국밥, 순대"), food("b", "순대국밥 돼지국밥"), food("c", "칼국수")])
    assert got["pairs"] == [("a", "b", ["돼지국밥"])] and got["places"] == ["a", "b"]
    assert menu_overlaps([food("a", "칼국수"), place("b", "음식점")])["pairs"] == []   # 메뉴가 없는 식당은 겹치지 않는다


# ---- 동선 거리 ----
def test_하루_거리는_연속_칸의_직선거리_합이다():
    pl = {"a": place("a", lat=37.50), "b": place("b", lat=37.51), "c": place("c", lat=37.50)}
    one_leg = day_km(slots(("오전", "a"), ("점심", "b")), pl)
    assert 1.0 < one_leg < 1.2
    assert abs(day_km(slots(("오전", "a"), ("점심", "b"), ("오후", "c")), pl) - 2 * one_leg) < 0.02   # 갔다가 돌아오면 두 배
    assert day_km(slots(("오전", "a"), ("점심", "없음")), pl) is None   # 사본에 없으면 계산하지 않는다


def test_검증기가_재배열_전후_거리를_leg_km_로_남긴다():
    from graph.validate import validate_update
    from harness.trace import Trace
    mk = lambda cid, off, typ: {"id": cid, "title": cid, "type": typ, "kind": "food" if typ == "음식점" else "sight", "lat": 37.5, "lon": 128.9 + off,
                                "region": "강릉", "showflag": "1", "rest_status": "none", "rest_weekdays": [], "rest_nth": [], "category": "", "snippet": ""}
    # 오전 a(서) → 점심 b(동) → 오후 c(동) → 늦은 오후 x(동) → 저녁 d(서): 점심 ↔ 저녁을 맞바꾸면 짧아진다
    cands = [mk("a", 0.00, "관광지"), mk("b", 0.05, "음식점"), mk("c", 0.06, "관광지"), mk("x", 0.07, "관광지"), mk("d", 0.01, "음식점")]
    sl = [{"slot": n, "content_id": c, "reason": "걷기 좋습니다."} for n, c in zip(["오전", "점심", "오후", "늦은 오후", "저녁"], "abcxd")]
    state = {"course": {"days": [{"date": "2026-11-21", "slots": sl}], "backup": [], "cafes": []}, "candidates": cands,
             "request": {"region": "강릉", "start_date": "2026-11-21", "days": 1, "preferences": []}, "retries": {"draft": 1}, "mode": "new"}
    out = validate_update({}, None, Trace(save=False))(state)
    row = out["leg_km"][0]
    assert row["date"] == "2026-11-21" and row["after"] < row["before"]
    assert validate_update({}, None, Trace(save=False))({**state, "mode": "edit"})["leg_km"] == []   # 수정 턴은 재배열하지 않아 기록도 없다


def test_재배열_전_값이_없으면_before_는_None이다():
    rm = route_metrics([{"date": "d", "slots": slots(("오전", "a"))}], {"a": place("a")})
    assert rm["before_km"] is None and rm["gain_km"] is None and rm["after_km"] == 0.0


# ---- 하루 칸 구성 ----
def test_하루_칸_수와_이용시간_있는_칸을_센다():
    pl = {"a": place("a", hours_text="09:00~18:00"), "b": place("b", hours_text="  "), "c": place("c")}
    course = [{"date": "d1", "slots": slots(("오전", "a"), ("오후", "b"))}, {"date": "d2", "slots": slots(("오전", "c"))}]
    s = day_shape(course, pl)
    assert s["slots_per_day"] == [2, 1] and s["slots"] == 3 and s["with_hours"] == 1 and s["hours_ratio"] == 0.333


# ---- 메뉴 중복 ----
def test_코스의_메뉴_중복은_식당_칸만_본다():
    pl = {"a": food("a", "돼지국밥"), "b": food("b", "돼지국밥 순대"), "c": food("c", "칼국수"),
          "k": food("k", "아메리카노", is_cafe=True), "k2": food("k2", "아메리카노", is_cafe=True), "s": place("s", extra={"menu_main": "돼지국밥"})}
    course = [{"date": "d1", "slots": slots(("점심", "a"), ("오후", "s"), ("카페", "k"), ("저녁", "b"))}, {"date": "d2", "slots": slots(("점심", "c"), ("카페", "k2"))}]
    m = menu_duplicates(course, pl)
    assert (m["restaurants"], m["pairs"], m["places"]) == (3, 1, 2)   # 카페 둘의 아메리카노는 세지 않는다


# ---- 요청 반영 ----
def test_요청에_낱말이_없으면_해당_없음이다():
    pl = {"a": place("a", access={"이동": {"접근로": "턱 없음"}})}
    got = request_reflection(["부산 1박 2일, 바다 보고 싶어"], [{"date": "d", "slots": slots(("오전", "a"))}], pl)
    assert got == {"access": None, "pet": None}


def test_무장애_반려동물_정보가_있는_장소_비율을_센다():
    pl = {"a": place("a", access={"이동": {"접근로": "턱 없음"}}), "b": place("b"), "c": place("c", pet={"범위": "전구역 동반가능"}),
          "d": place("d", extra={"pet": "가능"})}
    course = [{"date": "d", "slots": slots(("오전", "a"), ("오후", "b"), ("저녁", "c"), ("점심", "d"))}]
    got = request_reflection(["휠체어로 다닐 수 있는 곳, 강아지도 같이"], course, pl)
    assert got["access"] == {"places": 4, "with_info": 1, "ratio": 0.25}
    assert got["pet"] == {"places": 4, "with_info": 2, "ratio": 0.5}
    assert request_reflection(["유모차"], course, pl)["pet"] is None   # 낱말은 config 의 목록
    assert "유모차" in config.ACCESS_REQUEST_WORDS


# ---- 한 문항 · 채점 연결 ----
def _turn(kind="course", **kw):
    return {"kind": kind, "message": "서울 1박 2일, 강아지랑 휠체어", "request": {"region": "서울", "companions": ["가족"], "preferences": ["산책"], "exclusions": []},
            "course": [{"date": "2026-11-21", "slots": slots(("오전", "a"), ("점심", "f"), ("오후", "b"), ("저녁", "g"))}],
            "leg_km": [{"date": "2026-11-21", "before": 9.0, "after": 3.0}], "missing": [], "text": "", "notices": [], "festivals": [], "backup": [], "cafes": [],
            "violations": [], "removed": 0, "steps": [], "llm_calls": 1, "input_tokens": 1, "output_tokens": 1, **kw}


PLACES = {p["id"]: p for p in [place("a", pet={"범위": "전구역 동반가능"}, hours_text="상시"), place("b", lat=37.52), food("f", "돼지국밥"), food("g", "돼지국밥 면")]}


def test_코스_품질은_코스가_아니면_None이고_코스면_네_지표를_낸다():
    assert course_quality([_turn(kind="ask_back")], PLACES) is None
    q = course_quality([_turn()], PLACES)
    assert q["route"]["before_km"] == 9.0 and q["menu"]["pairs"] == 1 and q["shape"]["with_hours"] == 1
    assert q["request"]["pet"]["with_info"] == 1 and q["request"]["access"]["with_info"] == 0


def test_채점표에_품질_지표가_나오고_기존_값은_그대로다():
    row = {"id": "x", "case": "정상", "split": "dev", "expect": {"kind": "course"}, "turns": [_turn()], "error": "", "took_sec": 10.0}
    s = score_rows([row], PLACES)
    assert s["quality"]["courses"] == 1 and s["quality"]["menu_pairs"] == 1 and s["quality"]["km_paired_before"] == 9.0
    assert s["items"][0]["quality"]["shape"]["slots_per_day"] == [4]
    md = to_markdown("run", "p", "m", {}, s)
    assert "코스 품질 지표" in md and "| 기대 동작 일치 |" in md
    ask = score_rows([{**row, "expect": {"kind": "ask_back"}, "turns": [_turn(kind="ask_back", course=[])]}], PLACES)
    assert ask["quality"]["courses"] == 0 and "코스 품질 지표" not in to_markdown("run", "p", "m", {}, ask)


def test_동선_전후_합계는_전후가_모두_있는_코스끼리만_합친다():
    mk = lambda i, leg: {"id": i, "case": "정상", "split": "dev", "expect": {"kind": "course"}, "turns": [_turn(leg_km=leg)], "error": "", "took_sec": 1.0}
    rows = [mk("p", [{"date": "2026-11-21", "before": 9.0, "after": 3.0}]), mk("q", [])]   # q 는 재배열 전 값이 없다
    q = score_rows(rows, PLACES)["quality"]
    assert q["courses"] == 2 and q["km_paired"] == 1
    assert q["km_paired_before"] == 9.0 and q["km_paired_after"] == q["km_after_total"] / 2 and q["km_paired_gain"] == round(9.0 - q["km_paired_after"], 2)
