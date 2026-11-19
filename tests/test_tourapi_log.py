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


def test_한도_기록은_쓰는_도중에_읽혀도_깨지지_않는다(tmp_path, monkeypatch):
    # 왜: 다른 프로세스가 파일을 쓰는 틈에 읽어 빈 내용이 읽히면서 수집이 죽었다(2026-11-19). 임시 파일에 쓰고 이름을 바꾸며, 읽기는 잠깐 기다렸다 다시 읽는다.
    import json
    import pytest
    from ingest import tourapi
    path = tmp_path / "_usage.json"
    monkeypatch.setattr(tourapi, "USAGE_PATH", path)
    tourapi._save_usage({"date": "2026-11-19", "counts": {"detailCommon2": 3}})
    assert tourapi._load_usage("2026-11-19")["counts"] == {"detailCommon2": 3} and not list(tmp_path.glob("*.tmp"))
    # 빈 내용이 한 번 읽혀도 다시 읽어 낸다
    texts = iter(["", json.dumps({"date": "2026-11-19", "counts": {"a": 1}})])
    monkeypatch.setattr(type(path), "read_text", lambda self, encoding=None: next(texts))
    assert tourapi._read_usage()["counts"] == {"a": 1}
    # 끝까지 깨져 있으면 0건으로 보지 않고 오류를 낸다(한도를 넘기지 않기 위해)
    monkeypatch.setattr(type(path), "read_text", lambda self, encoding=None: "")
    monkeypatch.setattr(tourapi.time, "sleep", lambda s: None)
    with pytest.raises(json.JSONDecodeError):
        tourapi._read_usage()
