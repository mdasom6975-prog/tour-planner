"""그래프 뼈대 테스트 (14번 5-1). 노드 안은 비어 있으므로 State 에 값을 미리 넣어 분기만 확인한다."""
import config
from graph.build import build_graph
from harness.trace import Trace


def run(state):
    trace = Trace(save=False)
    out = build_graph(trace).invoke(state)
    return [e["step"] for e in out["trace"]], out


def test_조건이_충분하고_후보도_충분하면_끝까지_간다():
    path, _ = run({"request": {}, "enough": True})
    assert path == ["route", "parse_request", "retrieve", "grade_documents", "fetch_context",
                    "draft_course", "validate_course", "respond"]


def test_조건이_부족하면_되묻고_끝난다():
    path, _ = run({"request": {"missing": ["날짜"]}})
    assert path == ["route", "parse_request", "ask_back"]


def test_후보가_부족하면_두번_다시_찾고_포기한다():
    path, out = run({"request": {}, "enough": False})
    assert path == ["route", "parse_request", "retrieve", "grade_documents", "transform_query",
                    "retrieve", "grade_documents", "transform_query",
                    "retrieve", "grade_documents", "abstain"]
    assert out["retries"]["search"] == config.MAX_SEARCH_RETRIES


def test_위반이_계속되면_두번_다시_쓰고_내보낸다():
    path, out = run({"request": {}, "enough": True, "violations": ["x"]})
    assert path.count("draft_course") == config.MAX_REDRAFTS + 1
    assert path[-1] == "respond"
    assert out["retries"]["draft"] == config.MAX_REDRAFTS + 1
