"""검색 결과에 넣어도 되는 장소인지 판정한다. BM25 와 임베딩 검색이 같은 조건을 쓰도록 한 곳에 둔다. (2-1b)

여행 날짜와 행사 기간이 겹치는지는 여기서 보지 않는다 (여행 날짜를 아는 단계의 일).
"""
from datetime import date

import config


def check_filters(region: str | None, types: list | None) -> str | None:
    """조건이 잘못됐으면 사유를, 괜찮으면 None 을 돌려준다."""
    # 왜: 없는 지역 · 유형으로 찾으면 "결과 없음" 과 "잘못된 조건" 을 구분할 수 없다. 어디: 모든 검색기의 입력 검사.
    # 교안: 3일차 Part2 "에러도 결과로" / 4일차 PRD F1 "지원하지 않는 지역이면 지어내지 않고 안내".
    if region is not None and region not in config.REGIONS:
        return f"지원하지 않는 지역: {region}. 가능: {list(config.REGIONS)}"
    known = set(config.DETAIL_TYPES.values())
    if types and not set(types) <= known:
        return f"지원하지 않는 유형: {sorted(set(types) - known)}. 가능: {sorted(known)}"
    return None


def is_visible(place: dict, region: str | None = None, types: list | None = None, today: str | None = None) -> bool:
    # 왜: 지역 · 유형은 점수가 아니라 조건이다. "강릉" 이 본문에 여러 번 나온 부산 식당이 올라오면 안 된다. 어디: 점수 계산 뒤.
    # 교안: PRD F2 "메타데이터 필터". RAG 실습1 에는 없던 부분으로, 장소 데이터라서 필요하다.
    if region is not None and place["region"] != region:
        return False
    if types and place["type"] not in types:
        return False

    # 왜: 여행은 항상 오늘 이후이므로, 이미 끝난 행사는 어떤 여행에도 맞을 수 없다. 뒤 단계로 넘길 이유가 없다. 어디: 모든 검색.
    # 교안: "숫자와 사실 판정은 코드가" — 날짜 비교는 LLM 이 아니라 코드가 한다. 기준일은 시험할 수 있게 인자로 받는다.
    # 종료일이 오늘인 행사는 남긴다(오늘 갈 수 있다). 종료일 정보가 없으면 지우지 않고 남긴다.
    end = place.get("extra", {}).get("event_end", "")
    if end:
        ymd = (today or date.today().isoformat()).replace("-", "")
        if end < ymd:
            return False
    return True
