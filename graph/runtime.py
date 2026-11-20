"""실제 의존(검색 · 날씨 · 축제 · 상세 · LLM)을 꽂아 그래프를 만든다. 화면과 평가가 같이 쓴다. Streamlit 을 모른다. (14번 7-1)

핵심 로직(graph/)은 의존을 인자로 받는다. 어떤 실제 함수를 꽂는지는 여기 한 곳에 적는다.
"""
import sqlite3
from datetime import date
from pathlib import Path

import config
from graph.build import build_graph
from graph.llm import make_llm
from harness.trace import Trace
from langgraph.checkpoint.sqlite import SqliteSaver
from rag.filters import areas_in
from tools.festivals import search_festivals
from tools.places import get_place_detail, search_places
from tools.weather import get_weather



def make_graph(retriever, trace: Trace | None = None, *, provider: str | None = None, llm=None, checkpointer=None, today: str | None = None,
               weather_fetch=None, detail_fetch=None):
    """질문 한 건을 처리할 그래프. retriever 는 비싸서(준비 14초) 바깥에서 한 번 만들어 넘긴다."""
    # 왜: 날짜는 질문마다 새로 읽어야 앱을 며칠 켜 둬도 어제 날짜로 날씨를 묻지 않는다. 어디: 그래프를 만드는 시점.
    # 교안: 4일차 PRD "외부 의존 주입" — 오늘 날짜 · LLM · 검색 · 날씨를 인자로 받아 평가에서 가짜로 바꾼다.
    today = today or date.today().isoformat()
    places = {p["id"]: p for p in retriever.places}
    areas = {region: areas_in(retriever.places, region) for region in config.REGIONS}
    return build_graph(
        trace or Trace(), checkpointer, llm=llm or make_llm(provider), today=today,
        # 왜: 음식점 결과에는 카페가 섞여 있어 걸러 내면 식당이 모자란다. 음식점은 넉넉히 받고 retrieve 가 식당 · 카페로 나눠 자른다. 어디: 검색 k.
        # 교안: 직접 대응 없음.
        search=lambda q, region=None, types=None, area=None, prefer=None: search_places(
            q, region=region, types=types, area=area, k=config.SEARCH_K * (config.OVERFETCH if types in (config.FOOD_TYPES, config.INDOOR_TYPES) else 1),
            retriever=retriever, today=today, prefer=prefer),
        areas=areas,
        # 왜: 평가는 고정 날씨표와 저장분만 쓴다(2026-11-16 결정). 조회 함수를 넘기면 그것만 쓰고, 안 넘기면 화면처럼 실제 호출이다. 어디: 날씨 · 실시간 재확인.
        # 교안: 4일차 PRD "가짜 날씨 데이터를 주입".
        weather=lambda lat, lon, dates: get_weather(lat, lon, dates, today=today, **({"fetch": weather_fetch} if weather_fetch else {})),
        festivals=lambda region, start, end: search_festivals(region, start, end, places=retriever.places),
        stored=places,
        detail=lambda cid: get_place_detail(cid, places=places, today=today, **({"fetch": detail_fetch} if detail_fetch else {})),
    )


def open_checkpointer(path: str | None = None) -> SqliteSaver:
    """대화(thread_id)별 State 를 파일에 저장하는 저장소. 화면 스레드가 바뀌어도 쓰도록 check_same_thread 를 끈다."""
    # 왜: 새로고침 · 재시작 뒤에도 같은 대화의 코스를 이어 받는다. 어디: 후속 수정(7-4).
    # 교안: 3일차 05 checkpointer — 메모리 저장소(MemorySaver)를 파일 저장소로 바꾼 것.
    target = Path(path or config.CHAT_DB_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(str(target), check_same_thread=False))
