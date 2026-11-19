"""graph/present.py(요약 · 지도 경로 · 내려받기 문서)를 확인한다. Streamlit · 네트워크를 쓰지 않는다. (14번 7단계)"""
from graph.present import CREDIT, map_view, POLICY_URL, export_markdown, excerpt, map_link, route_by_day, shop_link, visit_info, summary_line, weather_line

SLOT = {"slot": "오전", "id": "1", "title": "안목해변", "type": "관광지", "addr": "강릉시 창해로", "lat": 37.77, "lon": 128.95, "leg_km": None,
        "facts": ["반려동물 동반 가능(전 구역)", "정보 방금 확인"], "access": [("이동 · 시설", ["접근로: 경사로"])], "reason": "바다 산책"}
SLOT2 = {**SLOT, "slot": "점심", "id": "2", "title": "초당두부", "type": "음식점", "lat": 37.79, "lon": 128.91, "leg_km": 4.1, "facts": [], "access": []}
STATE = {"request": {"region": "강릉", "place": "강릉", "companions": "부모님", "preferences": ["걷는 건 적게"]},
         "weather": {"source": "기상청 중기예보", "days": [{"date": "2026-11-21", "available": True, "temp_min": 2, "temp_max": 10, "rain_prob": 10, "rainy": False, "snowy": False}]},
         "answer": {"kind": "course", "days": [{"date": "2026-11-21", "slots": [SLOT, SLOT2]}, {"date": "2026-11-22", "slots": [{**SLOT, "lat": None}]}],
                    "backup": [{"title": "오죽헌", "type": "문화시설", "reason": "실내 전시", "addr": "강릉시 율곡로"}], "notices": ["이 기간에 등록된 축제가 없습니다."]}}
PLACES = {"1": {"overview": "소개 " * 100, "modified": "2026-10-01", "title": "안목해변", "lat": 37.77, "lon": 128.95},
          "2": {"overview": "두부 마을", "modified": "2026-09-01", "title": "초당두부", "type": "음식점", "addr": "강릉시 초당동 (초당)", "lat": 37.79, "lon": 128.91}}


def test_요약_한_줄은_지역_기간_동행_취향():
    assert summary_line(STATE) == "강릉 · 2026-11-21 ~ 2026-11-22 · 부모님 · 걷는 건 적게"
    assert summary_line({"request": {"region": "부산", "place": "해운대"}, "answer": {"days": []}}) == "부산 해운대"


def test_날씨_줄은_값이_있을_때만_숫자를_쓴다():
    assert weather_line(STATE["weather"]["days"][0]) == "최저 2~최고 10℃ · 강수확률 10% · 비·눈 예보 없음"
    assert weather_line(None) == "날씨 정보를 가져오지 못했습니다" and weather_line({"available": False}) == "날씨 정보를 가져오지 못했습니다"


def test_지도_경로는_좌표가_있는_장소만_방문_순서_번호로():
    routes = route_by_day(STATE["answer"])
    assert [(d, [p["n"] for p in pts]) for d, pts in routes] == [("2026-11-21", [1, 2]), ("2026-11-22", [])]


def test_지도_링크는_받은_좌표를_쓰고_쉼표는_이름에서_뺀다():
    assert map_link({"title": "가,나", "lat": 37.5, "lon": 127.1}) == "https://map.kakao.com/link/map/%EA%B0%80%20%EB%82%98,37.5,127.1"
    assert shop_link({"type": "관광지"}) is None and "%EC%B4%88%EB%8B%B9" in shop_link(PLACES["2"])


def test_발췌는_원문_앞부분만_자르고_줄바꿈을_정리한다():
    assert excerpt("가\n나 다") == "가 나 다" and excerpt("가" * 200).endswith("…") and len(excerpt("가" * 200)) == 141


def test_내려받기_문서에_출처와_정책_링크와_기준일이_붙는다():
    md = export_markdown(STATE, PLACES, "2026-11-13")
    assert md.startswith("# 어디갈래 여행 코스") and "## 2026-11-21" in md and "날씨: 최저 2~최고 10℃" in md
    assert "### 오전 — 안목해변 (관광지)" in md and "- 고른 이유: 바다 산책" in md and "직전 장소에서 직선 약 4.1km" in md
    assert "- 소개(관광공사 원문 발췌): 소개 소개" in md and "정보 기준일 2026-10-01" in md and "  - 무장애 — 이동 · 시설: 접근로: 경사로" in md
    assert "- 오죽헌 (문화시설) — 실내 전시" in md and "- 이 기간에 등록된 축제가 없습니다." in md
    assert md.rstrip().endswith(f"{CREDIT} · [저작권 정책 안내]({POLICY_URL}) · 날씨: 기상청 중기예보 · 데이터 기준일 2026-11-13")


def test_부가_코스가_없으면_없다고_적는다():
    s = {**STATE, "answer": {**STATE["answer"], "backup": []}}
    assert "- 이 조건에서 실내 후보를 찾지 못했습니다." in export_markdown(s, PLACES, "2026-11-13")


def test_지도_중심과_확대는_핀_범위에서_정한다():
    lat, lon, zoom = map_view(route_by_day(STATE["answer"]))
    assert (round(lat, 2), round(lon, 3)) == (37.78, 128.93) and zoom == 14    # 위도 0.02 · 경도 0.04도(보정 후 0.03) 범위
    assert map_view([("2026-11-21", [])]) is None
    far = [("d", [{"lat": 33.2, "lon": 126.2}, {"lat": 38.0, "lon": 129.4}])]
    assert map_view(far)[2] == 7                                              # 아주 넓으면 최소 7
    assert map_view([("d", [{"lat": 37.0, "lon": 127.0}])])[2] == 15          # 한 곳이면 최대 15


# --- 축제 · 장기 행사 갤러리 -------------------------------------------------
def test_갤러리_카드는_축제를_먼저_장기_행사를_뒤에_두고_저장된_사진과_원문을_쓴다():
    from graph.present import festival_cards
    fest = {"items": [{"id": "a", "title": "축제A", "event_start": "2026-11-14", "event_end": "2026-11-16", "days_in_trip": ["2026-11-14"], "lat": 1, "lon": 2}],
            "long_running": [{"id": "b", "title": "장기B", "event_start": "2026-10-01", "event_end": "2026-12-31", "days_in_trip": [], "lat": 1, "lon": 2}]}
    places = {"a": {"image": "https://x/a.jpg", "overview": "원문 소개", "homepage": "javascript:alert(1)", "extra": {"fee": "무료", "host": "주최"}},
              "b": {"image": "", "overview": "장기 소개", "homepage": "https://b.kr"}}
    cards = festival_cards(fest, places)
    assert [(c["id"], c["label"]) for c in cards] == [("a", "축제"), ("b", "상설 · 장기 행사")]
    assert cards[0]["image"] == "https://x/a.jpg" and cards[0]["fee"] == "무료" and cards[0]["homepage"] == ""   # 위험한 주소는 버린다
    assert cards[1]["homepage"] == "https://b.kr" and cards[1]["image"] == ""


def test_갤러리는_가로_스크롤과_클릭_정보를_갖고_글자는_이스케이프한다():
    from graph.present import festival_cards, gallery_html
    fest = {"items": [{"id": "a", "title": '<script>alert(1)</script>', "event_start": "2026-11-14", "event_end": "2026-11-16", "days_in_trip": [], "lat": 1, "lon": 2}],
            "long_running": []}
    out = gallery_html(festival_cards(fest, {"a": {"image": 'x" onerror="alert(2)', "overview": "<b>소개</b>"}}))
    assert "overflow-x:auto" in out and 'class="card"' in out and "addEventListener('click'" in out
    assert "<script>alert(1)</script>" not in out and '" onerror="' not in out and "&lt;script&gt;" in out
    assert "object-fit:contain" in out   # 사진을 자르지 않고 전체를 보인다
    assert out.count("<script>") == 1     # 우리 스크립트 하나뿐


def test_갤러리_카드는_정해진_수까지만():
    from graph.present import festival_cards
    import config
    fest = {"items": [{"id": str(n), "title": f"t{n}", "event_start": "a", "event_end": "b", "days_in_trip": []} for n in range(config.GALLERY_MAX + 5)], "long_running": []}
    assert len(festival_cards(fest, {})) == config.GALLERY_MAX


def test_장소_ID가_있으면_카카오_장소_링크_하나_없으면_기존_두_링크():
    from graph.present import place_links
    with_id = place_links({**PLACES["2"], "id": "2"}, {"2": "123"})
    assert with_id == [("카카오맵에서 보기", "https://place.map.kakao.com/123")]
    without = place_links({**PLACES["2"], "id": "2"}, {})
    assert [t for t, _ in without] == ["지도에서 보기", "가게 정보"]
    assert [t for t, _ in place_links({"id": "9", "type": "관광지", "title": "공원", "lat": 1, "lon": 2}, {"2": "123"})] == ["지도에서 보기"]


def test_ID_파일을_읽고_없는_파일과_못_찾은_곳은_뺀다(tmp_path):
    from graph.present import load_kakao_ids
    assert load_kakao_ids(tmp_path / "none.jsonl") == {}
    f = tmp_path / "ids.jsonl"
    f.write_text('{"contentid":"1","place_id":"11","date":"d"}\n{"contentid":"2","place_id":null,"reason":"후보 없음","date":"d"}\n', encoding="utf-8")
    assert load_kakao_ids(f) == {"1": "11"}


def test_내려받기_문서에도_장소_ID가_있으면_장소_링크():
    md = export_markdown(STATE, {k: {**v, "id": k} for k, v in PLACES.items()}, "2026-11-13", {k: "77" for k in PLACES})
    assert "[카카오맵에서 보기](https://place.map.kakao.com/77)" in md


def test_칩_선택은_문장으로_덧붙는다():
    from graph.present import compose_question
    assert compose_question("2박 3일 여행", "제주", ["바다", "오름"], False) == "2박 3일 여행 (지역: 제주, 취향: 바다, 오름)"
    assert compose_question("2박 3일 여행", None, [], False) == "2박 3일 여행"
    assert compose_question("", None, ["산"], True) == "취향 추가: 산"
    assert compose_question("점심 빼 줘", None, ["산"], True) == "점심 빼 줘 취향 추가: 산"


def test_지역을_이미_알면_지역_칩을_다시_그리지_않는다():
    from graph.present import known_region
    assert known_region({"answer": {"kind": "course"}, "request": {"region": "강릉"}}) == "강릉"
    assert known_region({"answer": {"kind": "ask_back"}, "request": {"region": "제주"}}) == "제주"   # 날짜만 되묻는 중
    assert known_region({"answer": {"kind": "ask_back"}, "request": {"region": None}}) is None   # 지역을 되묻는 중이면 칩을 그린다
    assert known_region({"answer": {"kind": "abstain"}, "request": {"region": "강릉"}}) is None and known_region({}) is None


def test_비_오는_날에만_실내_위주_이유를_보인다():
    from graph.present import rain_note
    assert rain_note({"indoor": True}, "실내 테마파크 위주로 골랐습니다.") == "비·눈 예보로 실내 위주로 짰습니다. 실내 테마파크 위주로 골랐습니다."
    assert rain_note({"indoor": False}, "이유") == "" and rain_note({"indoor": True}, "") == "" and rain_note(None, "이유") == ""


def test_이용_시간과_휴무일_원문을_줄로_만들고_빈_값은_뺀다():
    assert visit_info({"hours_text": "09:00~18:00", "rest_text": "매주 월요일"}) == ["이용 시간: 09:00~18:00", "휴무일: 매주 월요일"]
    assert visit_info({"hours_text": "상시 개방", "rest_text": ""}) == ["이용 시간: 상시 개방"] and visit_info({}) == []
    assert visit_info({"hours_text": "가" * 200})[0].endswith("…")
