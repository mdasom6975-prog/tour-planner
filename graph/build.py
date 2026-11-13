"""LangGraph 뼈대. 노드 11개를 PRD 10번 순서로 잇고 분기 세 곳만 정한다. (14번 5-1)

노드 안은 아직 비어 있다. 실행 기록 한 줄만 남기고 State 를 그대로 넘긴다. Streamlit 을 알지 못한다.
"""
import time

from langgraph.graph import END, START, StateGraph

import config
from graph.state import State
from harness.trace import Trace

NODES = [
    "parse_request", "ask_back", "retrieve", "grade_documents", "transform_query", "abstain",
    "fetch_context", "draft_course", "validate_course", "respond",
]


def _retries(state: State) -> dict:
    return {"search": 0, "draft": 0, **state.get("retries", {})}


# --- 분기: State 값만 보고 정한다 -------------------------------------------
def after_parse(state: State) -> str:
    # 왜: 조건이 빠졌으면 검색하지 않고 되묻는다. 어디: parse_request 뒤.
    # 교안: PRD 10번 [조건 부족?] 분기.
    return "ask_back" if state.get("request", {}).get("missing") else "retrieve"


def after_grade(state: State) -> str:
    # 왜: 후보가 부족해도 두 번까지만 다시 찾고, 그래도 부족하면 포기한다(무한 반복 방지). 어디: grade_documents 뒤.
    # 교안: 3일차 05 조건부 엣지 — 반복 상한은 config.MAX_SEARCH_RETRIES.
    if state.get("enough"):
        return "fetch_context"
    return "transform_query" if _retries(state)["search"] < config.MAX_SEARCH_RETRIES else "abstain"


def after_validate(state: State) -> str:
    # 왜: 작성 횟수를 세면 최초 1회 + 재작성 MAX_REDRAFTS회가 되어, 위반 여부와 무관하게 같은 식이 선다. 어디: validate_course 뒤.
    # 교안: 3일차 평가자 · 최적화 루프 — 반복 상한은 config.MAX_REDRAFTS. 위반 표시는 6단계.
    if state.get("violations") and _retries(state)["draft"] <= config.MAX_REDRAFTS:
        return "draft_course"
    return "respond"


# --- 노드 ------------------------------------------------------------------
def _make_node(name: str, trace: Trace, update=None):
    # 왜: 모든 노드가 같은 모양으로 기록을 남겨야 화면과 평가가 한 가지로 읽는다. 어디: 노드마다.
    # 교안: 직접 대응 없음 (harness/trace.py 의 node 종류 기록).
    def run(state: State) -> dict:
        t0 = time.perf_counter()
        changes = update(state) if update else {}
        entry = trace.record(name, "node", output=changes, took_ms=round((time.perf_counter() - t0) * 1000, 2))
        return {**changes, "trace": [entry]}
    return run


def _count(key: str):
    def update(state: State) -> dict:
        return {"retries": {**_retries(state), key: _retries(state)[key] + 1}}
    return update


def build_graph(trace: Trace | None = None, checkpointer=None):
    """노드 뼈대를 잇는다. trace 는 바깥에서 받는다(평가 · 테스트가 바꿔 끼운다)."""
    trace = trace or Trace(save=False)
    g = StateGraph(State)
    updates = {"transform_query": _count("search"), "draft_course": _count("draft")}
    for name in NODES:
        g.add_node(name, _make_node(name, trace, updates.get(name)))
    # fetch_context 의 날씨 · 축제 · 휴무 병렬 처리는 5-4에서 안쪽에 넣는다.

    g.add_edge(START, "parse_request")
    g.add_conditional_edges("parse_request", after_parse, ["ask_back", "retrieve"])
    g.add_edge("ask_back", END)
    g.add_edge("retrieve", "grade_documents")
    g.add_conditional_edges("grade_documents", after_grade, ["fetch_context", "transform_query", "abstain"])
    g.add_edge("transform_query", "retrieve")
    g.add_edge("abstain", END)
    g.add_edge("fetch_context", "draft_course")
    g.add_edge("draft_course", "validate_course")
    g.add_conditional_edges("validate_course", after_validate, ["draft_course", "respond"])
    g.add_edge("respond", END)
    return g.compile(checkpointer=checkpointer)
