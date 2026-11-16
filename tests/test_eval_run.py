"""평가 실행기(eval/run.py)를 가짜 LLM 으로 확인한다. 모델 · 관광공사 · 날씨 서버를 부르지 않는다. (14번 8-2)"""
import json

import config
import eval.run as run
from graph.build import build_graph
from tools.places import get_place_detail
from tools.weather import get_weather

TODAY = "2026-11-16"


class FakeRetriever:
    places = []


def use_fake_graph(monkeypatch, answers):
    """make_graph 를 가짜 LLM 그래프로 바꾼다. answers 는 조건 이해가 차례로 돌려줄 값."""
    seen = {}

    def fake_make_graph(retriever, trace, *, llm, checkpointer, today, weather_fetch, detail_fetch):
        seen.update(today=today, weather_fetch=weather_fetch, detail_fetch=detail_fetch)
        return build_graph(trace, checkpointer, llm=lambda system, user, schema: answers.pop(0), today=today)
    monkeypatch.setattr(run, "make_graph", fake_make_graph)
    return seen


def item(i="x01", turns=("문장",), kind="ask_back"):
    return {"id": i, "case": "경계", "split": "dev", "today": TODAY, "turns": list(turns), "expect": {"kind": kind}}


def test_문항을_돌리면_턴마다_답과_단계와_시간이_남는다(monkeypatch):
    seen = use_fake_graph(monkeypatch, [dict(region="제주", days=3), dict(start_date="2026-11-10")])
    row = run.run_item(item(turns=("제주 사흘", "11월 10일")), FakeRetriever(), llm=object())
    assert [t["kind"] for t in row["turns"]] == ["ask_back", "ask_back"] and row["error"] == ""
    assert row["turns"][0]["missing"] == ["start_date"] and row["turns"][1]["request"]["region"] == "제주"   # 되묻기 뒤 조건이 이어진다
    assert [s["step"] for s in row["turns"][0]["steps"]] == ["route", "parse_request.llm", "parse_request", "ask_back"]
    assert row["turns"][1]["steps"][0]["step"] == "route"   # 둘째 턴에는 둘째 턴의 단계만 남는다
    assert seen == {"today": TODAY, "weather_fetch": run.fixed_weather, "detail_fetch": run.stored_only}


def test_문항이_죽어도_오류_종류만_남기고_계속한다(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("주소와 키가 섞인 문구")
    monkeypatch.setattr(run, "make_graph", lambda *a, **k: type("G", (), {"invoke": boom})())
    row = run.run_item(item(), FakeRetriever(), llm=object())
    assert row["error"] == "RuntimeError" and row["turns"] == [] and "키" not in json.dumps(row, ensure_ascii=False)


def test_실행_기록과_설정과_요약이_파일로_남는다(monkeypatch, tmp_path):
    use_fake_graph(monkeypatch, [dict(days=2), dict(region="부산", days=1, start_date="2026-11-21")])
    summary = run.run_all([item("x01"), item("x02", kind="course")], FakeRetriever(), ["claude"], tmp_path, llm=object(), say=lambda s: None)
    rows = [json.loads(line) for line in (tmp_path / "claude.jsonl").read_text(encoding="utf-8").splitlines()]
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert [r["id"] for r in rows] == ["x01", "x02"] and meta["items"] == ["x01", "x02"]
    assert meta["weather"] == "fixed" and meta["detail"] == "stored" and meta["models"] == {"claude": config.MODELS["claude"]}
    assert summary["claude"]["items"] == 2 and summary["claude"]["kind_match"] == 1   # x02 는 검색이 없어 코스가 안 나온다


def test_고정_날씨표는_정한_날만_비_눈이고_다시_불러도_같다():
    dates = ["2026-11-21", "2026-11-22", "2026-11-29"]
    got = get_weather(37.5, 127.0, dates, fetch=run.fixed_weather, today=TODAY)
    assert got == {**get_weather(37.5, 127.0, dates, fetch=run.fixed_weather, today=TODAY), "took_ms": got["took_ms"]}
    by = {d["date"]: d for d in got["days"]}
    assert by["2026-11-21"]["rain_prob"] == 10 and by["2026-11-22"]["rain_prob"] == 80 and by["2026-11-29"]["snow_cm"] == 2.0


def test_평가의_실시간_재확인은_호출_없이_저장분을_쓴다():
    place = {"id": "1", "title": "장소", "type": "관광지", "fetched": "2026-11-16"}
    got = get_place_detail("1", places=[place], fetch=run.stored_only, today=TODAY)
    assert (got["ok"], got["source"], got["calls"]) == (True, "stored", 0)


def test_평가셋은_분할로_고르고_id를_주면_그_문항만_고른다():
    assert len(run.load_set("dev")) == 28 and len(run.load_set("holdout")) == 12 and len(run.load_set("all")) == 40
    assert [r["id"] for r in run.load_set("dev", ["a08", "c01"])] == ["c01", "a08"]
