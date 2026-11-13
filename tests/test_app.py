"""화면(app.py)을 Streamlit 의 헤드리스 실행기로 확인한다. 가짜 LLM · 가짜 검색기를 꽂아 네트워크를 쓰지 않는다. (14번 7단계)

브라우저 화면 확인(스크린샷)은 이 테스트가 대신하지 않는다.
"""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")   # 가상환경(.venv) 밖의 파이썬에는 화면 라이브러리가 없다
pytest.importorskip("streamlit_folium")
from streamlit.testing.v1 import AppTest  # noqa: E402

import graph.runtime
import rag.retriever
from graph.build import build_graph
from graph.schemas import TripRequest
from harness.trace import Trace
from test_validate import CANDS, D1, Harness, good


class FakeIndex:
    places = [{**c, "image": "", "overview": f"{c['title']} 원문 소개", "modified": "2026-10-01", "type": c["type"]} for c in CANDS]


@pytest.fixture
def app(monkeypatch, tmp_path):
    h = Harness([good()], {})
    mode = {"parsed": None}   # 되묻기 시험에서 조건 이해 결과를 바꾼다
    llm = lambda system, user, schema: mode["parsed"] if schema is TripRequest and mode["parsed"] else h.llm(system, user, schema)
    monkeypatch.setattr(rag.retriever.Retriever, "from_file", classmethod(lambda cls, *a, **k: FakeIndex()))
    weather = lambda la, lo, d: {"ok": True, "days": [{"date": x, "available": True, "temp_min": 1, "temp_max": 8, "rain_prob": 10, "snow_cm": 0.0, "note": ""} for x in d], "source": "가짜"}
    festivals = lambda r, s, e: {"ok": True, "results": []}
    stored = {c["id"]: {"rest_status": "always_open", "rest_weekdays": [], "rest_nth": [], "rest_note": False} for c in CANDS}
    monkeypatch.setattr(graph.runtime, "make_graph", lambda index, trace=None, **k: build_graph(
        Trace(base_dir=tmp_path), llm=llm, today="2026-11-13", search=h.search, weather=weather, festivals=festivals, stored=stored, detail=h.detail))
    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app.py"), default_timeout=60)
    at.mode = mode
    at.run()
    return at


def test_처음_화면에는_안내만_있고_오류가_없다(app):
    assert not app.exception and any("코스가 여기에 나옵니다" in c.value for c in app.caption)


def test_질문하면_일자_탭과_카드와_내려받기가_나온다(app):
    app.chat_input[0].set_value("다음 주 토요일부터 1박 2일 강릉").run()
    assert not app.exception
    assert len(app.tabs) == 2 and [t.label for t in app.tabs] == ["11-21", "11-22"]
    text = " ".join(m.value for m in app.markdown)
    assert "고른 이유" in text and "장소s0" in text and "원문 소개" in text
    assert any("직전 장소에서 직선 약" in c.value for c in app.caption)
    assert any("규칙 검사를 모두 통과했습니다" in m.value for m in app.markdown)      # 대화 답
    assert any(d.proto.label == "코스 내려받기 (.md)" for d in app.get("download_button"))
    assert any("출처 : ⓒ한국관광공사" in c.value for c in app.caption)


def test_조건이_빠진_질문은_되묻고_코스를_그리지_않는다(app):
    app.mode["parsed"] = {"region": None, "days": None}
    app.chat_input[0].set_value("주말에 어디 갈까").run()
    assert not app.exception and len(app.tabs) == 0
    assert any("어느 지역" in m.value or "지역" in m.value for m in app.markdown)
    assert not app.get("download_button")


def test_처리_중_오류가_나도_화면은_사유를_말한다(monkeypatch, app):
    def boom(*a, **k):
        raise TimeoutError("느림")
    monkeypatch.setattr(graph.runtime, "make_graph", boom)
    app.chat_input[0].set_value("강릉 1박 2일").run()
    assert not app.exception and any("처리 중 문제가 생겼습니다(TimeoutError)" in m.value.replace("\\", "") for m in app.markdown)
