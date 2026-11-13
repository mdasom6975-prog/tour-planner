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
    weather: dict
    festivals: dict
    course: dict         # draft_course 가 만든 일자별 배치
    violations: list     # validate_course 가 찾은 규칙 위반 (6단계)
    retries: dict        # {"search": 검색 재시도 수, "draft": 코스를 쓴 횟수(최초 1회 + 재작성)}
    answer: dict         # 끝에 나가는 값: 되묻기 · 찾지 못함 · 코스
    # 왜: 노드마다 한 줄씩 덧붙여야 해서 합치는 방식(덧붙이기)을 정한다. 어디: 실행 기록 줄 목록.
    # 교안: 3일차 05 State 의 reducer — 같은 칸에 여러 노드가 쓸 때 어떻게 합칠지 지정한다.
    trace: Annotated[list, operator.add]


def retries_of(state: State) -> dict:
    """반복 횟수. 칸이 비어 있어도 0 으로 읽는다. search: 질의를 고쳐 다시 찾은 수, draft: 코스를 쓴 횟수(최초 1회 + 재작성)."""
    return {"search": 0, "draft": 0, **state.get("retries", {})}
