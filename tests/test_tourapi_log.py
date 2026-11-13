"""ingest/tourapi.py: 실패가 결과와 로그 양쪽에 남는지 확인한다. 네트워크와 한도 기록을 건드리지 않는 경로만 본다. (L-2)"""
from ingest import tourapi


def test_키가_없으면_호출하지_않고_오류_로그를_남긴다(monkeypatch):
    seen = []
    monkeypatch.delenv("TOURAPI_KEY", raising=False)
    monkeypatch.setattr(tourapi.log, "error", lambda *args: seen.append(args))
    monkeypatch.setattr(tourapi.requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("호출하면 안 된다")))
    r = tourapi.call("detailCommon2", {"contentId": "1"})
    assert r == {"ok": False, "reason": ".env 에 TOURAPI_KEY 가 없습니다"}
    assert len(seen) == 1 and seen[0][1] == "detailCommon2"


def test_실패_결과의_모양은_전과_같다():
    assert tourapi._fail("op", "사유") == {"ok": False, "reason": "사유"}
    assert tourapi._fail("op", "한도", "info", limit=True) == {"ok": False, "limit": True, "reason": "한도"}
