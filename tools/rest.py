"""저장된 휴무 정보로 "그 날 쉬는가"를 가볍게 판정한다. 코스를 짜기 전에 후보 × 여행일 표를 만드는 데 쓴다. (14번 5-4)

최종 판정은 6단계 검증기가 실시간 재확인 값으로 한다. 여기서는 처음부터 휴무 장소를 피해 재작성을 줄이는 것이 목적이다.
"매월 ○째 요일" · 공휴일 달력은 6단계에서 더한다. 지금은 "확인 필요"(check)로 남는다.
"""
from datetime import date

WEEK = "월화수목금토일"


def rest_on(place: dict, day: date) -> str:
    """'closed'(휴무로 확정) · 'open'(영업) · 'check'(저장분으로는 알 수 없음)."""
    # 왜: 요일 비교는 LLM 이 아니라 코드가 한다(PRD 8번). 공휴일 같은 단서가 붙은 "매주 월요일 / 공휴일"도 월요일은 확정이라 휴무로 본다. 어디: 후보 × 날짜 표.
    # 교안: "숫자와 사실 판정은 코드가". 측정(2026-11-13): 가볼 곳 · 음식점 2,621곳 중 연중무휴 1,340 · 매주 942(단서 있음 464) · 확정 못 함 339.
    status = place.get("rest_status")
    if status == "always_open":
        return "open"
    if status == "weekly":
        return "closed" if WEEK[day.weekday()] in (place.get("rest_weekdays") or []) else "open"
    return "check"
