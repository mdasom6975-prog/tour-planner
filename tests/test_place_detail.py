"""tools/places.py 의 get_place_detail 을 가짜 관광공사 응답으로 확인한다. 네트워크와 한도를 쓰지 않는다. (4-5b)"""
import pytest

from tools.places import get_place_detail

STORED = {"id": "1", "title": "옛 이름", "type": "문화시설", "region": "부산", "addr": "옛 주소", "lat": 35.1, "lon": 129.0,
          "image": "old.jpg", "modified": "2026-11-01", "fetched": "2026-11-11", "overview": "옛 소개", "homepage": "", "rest_text": "매주 월요일",
          "hours_text": "09:00~18:00", "contact": "", "parking": "", "extra": {}, "rest_status": "weekly", "rest_weekdays": ["월"], "rest_note": False}
COMMON = {"ok": True, "items": [{"title": "새 이름", "addr1": "새 주소", "addr2": "2층", "firstimage": "new.jpg", "modifiedtime": "20261113090000", "overview": "새 소개"}]}
INTRO = {"ok": True, "items": [{"restdateculture": "매주 화요일", "usetimeculture": "10:00~17:00"}]}
TODAY = "2026-11-13"


class FakeFetch:
    def __init__(self, common=COMMON, intro=INTRO):
        self.answers, self.calls = {"detailCommon2": common, "detailIntro2": intro}, []

    def __call__(self, operation, params):
        self.calls.append((operation, params))
        out = self.answers[operation]
        if isinstance(out, Exception):
            raise out
        return out


def _get(fake, cid="1"):
    return get_place_detail(cid, places=[STORED], fetch=fake, today=TODAY)


def test_실시간으로_받은_값이_저장분을_덮는다():
    fake = FakeFetch()
    r = _get(fake)
    assert (r["ok"], r["source"], r["as_of"], r["withdrawn"], r["calls"]) == (True, "live", TODAY, False, 2)
    p = r["place"]
    assert (p["title"], p["addr"], p["image"], p["modified"], p["overview"]) == ("새 이름", "새 주소 2층", "new.jpg", "2026-11-13", "새 소개")
    assert (p["rest_text"], p["rest_status"], p["rest_weekdays"], p["hours_text"]) == ("매주 화요일", "weekly", ["화"], "10:00~17:00")
    assert (p["id"], p["lat"], p["lon"], p["region"], p["type"]) == ("1", 35.1, 129.0, "부산", "문화시설")   # 좌표 · 지역 · 유형은 저장분
    assert fake.calls == [("detailCommon2", {"contentId": "1"}), ("detailIntro2", {"contentId": "1", "contentTypeId": "14"})]


def test_저장된_목록에_없는_ID는_묻지도_않는다():
    fake = FakeFetch()
    r = _get(fake, cid="999")
    assert r["ok"] is False and "999" in r["reason"] and fake.calls == []


@pytest.mark.parametrize("common, intro, calls, word", [
    ({"ok": False, "reason": "연결 실패: Timeout"}, INTRO, 1, "소개글 조회 실패"),
    (COMMON, {"ok": False, "reason": "resultCode=99"}, 2, "휴무일 조회 실패"),
    ({"ok": False, "limit": True, "reason": "한도"}, INTRO, 0, "한도"),
    (COMMON, {"ok": False, "limit": True, "reason": "한도"}, 1, "한도"),
    (RuntimeError("깨짐"), INTRO, 0, "오류"),
    ({"ok": True, "items": ["글자"]}, INTRO, 0, "오류"),
])
def test_하나라도_실패하면_통째로_저장분(common, intro, calls, word):
    r = _get(FakeFetch(common, intro))
    assert (r["ok"], r["source"], r["as_of"], r["calls"]) == (True, "stored", "2026-11-11", calls) and word in r["note"]
    assert (r["place"]["title"], r["place"]["overview"], r["place"]["rest_weekdays"]) == ("옛 이름", "옛 소개", ["월"])   # 섞이지 않는다


def test_소개글이_실패하면_휴무일은_부르지_않는다():
    fake = FakeFetch(common={"ok": False, "reason": "실패"})
    _get(fake)
    assert [c[0] for c in fake.calls] == ["detailCommon2"]


def test_관광공사에_없는_장소는_저장분으로_되살리지_않는다():
    fake = FakeFetch(common={"ok": True, "items": []})
    r = _get(fake)
    assert (r["ok"], r["source"], r["withdrawn"], r["place"], r["calls"]) == (True, "live", True, None, 1)
    assert [c[0] for c in fake.calls] == ["detailCommon2"]


def test_휴무일_응답이_비어_있으면_빈_칸으로():
    r = _get(FakeFetch(intro={"ok": True, "items": []}))
    assert r["source"] == "live" and r["place"]["rest_text"] == "" and r["place"]["rest_status"] == "unknown"


def test_장소_목록을_dict_로_줘도_된다():
    r = get_place_detail("1", places={"1": STORED}, fetch=FakeFetch(), today=TODAY)
    assert r["source"] == "live"


class FakeLog:
    """로그 흉내. 어떤 수준으로 불렸는지만 기억한다."""
    def __init__(self):
        self.levels = []

    def __getattr__(self, level):
        return lambda *args, **kwargs: self.levels.append(level)


def test_실시간_성공은_정보_저장분_대체는_경고_예외는_오류로_남는다(monkeypatch):
    fake_log = FakeLog()
    monkeypatch.setattr("tools.places.log", fake_log)
    _get(FakeFetch(common={"ok": False, "reason": "연결 실패"}))
    _get(FakeFetch())
    _get(FakeFetch(common=RuntimeError("깨짐")))
    _get(FakeFetch(common={"ok": True, "items": []}))
    assert fake_log.levels == ["warning", "info", "exception", "warning", "warning"]
