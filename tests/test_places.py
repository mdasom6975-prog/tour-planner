"""tools/places.py 의 search_places 를 가짜 검색기로 확인한다. 모델을 불러오지 않는다."""
import config
from tools.places import search_places

PLACES = [
    {"id": "1", "title": "개미집 본점", "type": "음식점", "region": "부산", "addr": "부산광역시 중구", "lat": 35.1, "lon": 129.03,
     "modified": "20261101", "overview": "낙" * 500, "access": {"이동": {"휠체어": "대여 가능"}}, "pet": None, "search_text": "x"},
    {"id": "2", "title": "태종대", "type": "관광지", "region": "부산", "addr": "부산광역시 영도구", "lat": 35.05, "lon": 129.08,
     "modified": "20261020", "overview": "짧은 소개", "pet": {"범위": "일부구역 동반가능"}, "search_text": "y"},
]


class FakeRetriever:
    """검색기 흉내. 받은 인자를 기억해 두고 정해 둔 결과를 돌려준다."""
    def __init__(self, result, places=PLACES):
        self.places, self.result, self.called = places, result, None

    def search(self, query, **kwargs):
        self.called = {"query": query, **kwargs}
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _ok(*ids):
    return {"ok": True, "results": [{"id": i, "title": "?", "score": 0.9 - n * 0.1} for n, i in enumerate(ids)], "took_ms": 12.3}


def test_뒤_단계가_쓰는_칸을_모두_채운다():
    r = search_places("부산 낙곱새", region="부산", retriever=FakeRetriever(_ok("1", "2")))
    assert r["ok"] and r["count"] == 2 and r["top_score"] == 0.9 and r["took_ms"] == 12.3
    first = r["results"][0]
    assert set(first) == {"id", "title", "type", "region", "addr", "lat", "lon", "modified", "is_cafe", "category", "snippet", "score", "access", "pet"}
    assert (first["title"], first["lat"], first["lon"]) == ("개미집 본점", 35.1, 129.03)   # 이름 · 좌표는 검색기가 아니라 저장된 장소에서


def test_발췌는_원문_앞부분_그대로():
    r = search_places("q", retriever=FakeRetriever(_ok("1", "2")))
    assert r["results"][0]["snippet"] == PLACES[0]["overview"][:config.SNIPPET_CHARS]
    assert len(r["results"][0]["snippet"]) == config.SNIPPET_CHARS
    assert r["results"][1]["snippet"] == "짧은 소개"


def test_무장애_반려동물은_저장분_그대로_없으면_빈_dict():
    r = search_places("q", retriever=FakeRetriever(_ok("1", "2")))
    assert r["results"][0]["access"] == {"이동": {"휠체어": "대여 가능"}} and r["results"][0]["pet"] == {}
    assert r["results"][1]["access"] == {} and r["results"][1]["pet"] == {"범위": "일부구역 동반가능"}


def test_인자를_검색기에_그대로_넘긴다():
    fake = FakeRetriever(_ok())
    search_places("강릉 카페", region="강릉", types=["음식점"], k=5, retriever=fake, today="2026-11-13", trace="기록장치")
    assert fake.called == {"query": "강릉 카페", "k": 5, "region": "강릉", "types": ["음식점"], "today": "2026-11-13", "trace": "기록장치", "area": None}


def test_시군_조건도_검색기에_넘긴다():
    fake = FakeRetriever(_ok())
    search_places("전주 한옥", region="전북", area="전주", retriever=fake)
    assert fake.called["area"] == "전주"


def test_결과_0건은_실패가_아니다():
    r = search_places("부산 스키장", retriever=FakeRetriever(_ok()))
    assert r == {"ok": True, "results": [], "count": 0, "top_score": None, "took_ms": 12.3}


def test_검색기의_실패_사유를_그대로_올린다():
    r = search_places("q", region="대구", retriever=FakeRetriever({"ok": False, "reason": "지원하지 않는 지역: 대구"}))
    assert r == {"ok": False, "reason": "지원하지 않는 지역: 대구"}


def test_검색기가_예외를_던져도_죽지_않는다():
    r = search_places("q", retriever=FakeRetriever(RuntimeError("모델 오류")))
    assert r["ok"] is False and "RuntimeError" in r["reason"]


def test_저장된_장소에_없는_ID는_뺀다():
    r = search_places("q", retriever=FakeRetriever(_ok("1", "999")))
    assert [x["id"] for x in r["results"]] == ["1"] and r["count"] == 1
