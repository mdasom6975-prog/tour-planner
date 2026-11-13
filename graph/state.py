"""그래프 State. 노드가 읽고 쓰는 값을 한곳에 적는다. (PRD 10번, 14번 5단계)"""
import operator
from typing import Annotated, TypedDict


class State(TypedDict, total=False):
    query: str           # 지금 검색에 쓰는 질의. 처음에는 코드가 조건으로 만들고, transform_query 가 고쳐 쓴다
    grade: dict          # grade_documents 판정 결과: 종류별 후보 수 · 필요한 수 · 사유
    search_error: str    # 검색이 실패했을 때의 사유 (없으면 키 없음)
    message: str         # 사용자가 입력한 문장 (parse_request 가 읽는다)
    request: dict        # parse_request 가 만든 조건 JSON. missing(빠진 조건 목록)을 함께 담는다
    candidates: list     # retrieve 가 찾은 후보 장소
    enough: bool         # grade_documents 판정: 조건에 맞는 후보가 충분한가
    area: str | None     # retrieve 가 실제로 거른 시 · 군 (place 가 주소와 맞았을 때만 값이 있다)
    weather: dict        # fetch_context: 날짜별 날씨 · 비 · 눈 판정 · 알림 문장
    festivals: dict      # fetch_context: 축제(items) · 상설 장기 행사(long_running) · 알림 문장
    rest_table: dict     # fetch_context: {후보 id: {날짜: "closed" | "check"}} (영업일은 적지 않는다)
    course: dict         # draft_course 가 만든 일자별 배치
    course_error: str    # draft_course 가 쓰지 못했을 때의 오류 이름
    rechecked: dict      # validate_course 가 관광공사에서 다시 받은 장소별 휴무 값 · 출처(live/stored) · 기준일
    removed: list       # 재작성을 다 쓰고도 남아 코스에서 뺀 위반 장소
    violations: list     # validate_course 가 찾은 규칙 위반 (6단계)
    retries: dict        # {"search": 검색 재시도 수, "draft": 코스를 쓴 횟수(최초 1회 + 재작성)}
    mode: str            # route 가 정한 이번 턴의 종류: new(새 요청) | edit(이미 나온 코스 고치기)
    edit_note: str       # edit_course 가 후보에 없어 반영하지 못한 부분(없으면 빈 문자열)
    edit_error: str      # edit_course 의 LLM 호출이 실패했을 때의 오류 이름(이전 코스를 그대로 둔다)
    answer: dict         # 끝에 나가는 값: 되묻기 · 찾지 못함 · 코스
    # 왜: 노드마다 한 줄씩 덧붙여야 해서 합치는 방식(덧붙이기)을 정한다. 어디: 실행 기록 줄 목록.
    # 교안: 3일차 05 State 의 reducer — 같은 칸에 여러 노드가 쓸 때 어떻게 합칠지 지정한다.
    trace: Annotated[list, operator.add]


def retries_of(state: State) -> dict:
    """반복 횟수. 칸이 비어 있어도 0 으로 읽는다. search: 질의를 고쳐 다시 찾은 수, draft: 코스를 쓴 횟수(최초 1회 + 재작성)."""
    return {"search": 0, "draft": 0, **state.get("retries", {})}
