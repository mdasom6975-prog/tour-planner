"""실제 의존(검색 · 날씨 · 축제 · 상세 · LLM)을 꽂아 그래프를 만든다. 화면과 평가가 같이 쓴다. Streamlit 을 모른다. (14번 7-1)

핵심 로직(graph/)은 의존을 인자로 받는다. 어떤 실제 함수를 꽂는지는 여기 한 곳에 적는다.
"""
from datetime import date

import config
from graph.build import build_graph
from graph.llm import make_llm
from harness.trace import Trace
from rag.filters import areas_in
from tools.festivals import search_festivals
from tools.places import get_place_detail, search_places
from tools.weather import get_weather

SEARCH_K = 10   # 종류(가볼 곳 · 음식점 · 실내)마다 가져오는 후보 수. 5-5 실행에서 쓴 값


def make_graph(retriever, trace: Trace | None = None, *, provider: str | None = None, llm=None, checkpointer=None, today: str | None = None):
    """질문 한 건을 처리할 그래프. retriever 는 비싸서(준비 14초) 바깥에서 한 번 만들어 넘긴다."""
    # 왜: 날짜는 질문마다 새로 읽어야 앱을 며칠 켜 둬도 어제 날짜로 날씨를 묻지 않는다. 어디: 그래프를 만드는 시점.
    # 교안: 4일차 PRD "외부 의존 주입" — 오늘 날짜 · LLM · 검색 · 날씨를 인자로 받아 평가에서 가짜로 바꾼다.
    today = today or date.today().isoformat()
    places = {p["id"]: p for p in retriever.places}
    areas = {region: areas_in(retriever.places, region) for region in config.REGIONS}
    return build_graph(
        trace or Trace(), checkpointer, llm=llm or make_llm(provider), today=today,
        search=lambda q, region=None, types=None, area=None: search_places(q, region=region, types=types, area=area, k=SEARCH_K, retriever=retriever, today=today),
        areas=areas,
        weather=lambda lat, lon, dates: get_weather(lat, lon, dates, today=today),
        festivals=lambda region, start, end: search_festivals(region, start, end, places=retriever.places),
        stored=places,
        detail=lambda cid: get_place_detail(cid, places=places, today=today),
    )
