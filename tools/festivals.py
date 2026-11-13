"""여행 기간과 행사 기간이 겹치는 축제를 찾는다. 글로 찾는 검색이 아니라 날짜 비교다. (PRD 9번 search_festivals, 14번 4단계 중 4-3)

그날 실제로 열리는지(주말만 운영 등)와 상설 공연인지의 판단은 여기 없다. 행사 일수만 돌려준다.
"""
from datetime import date, timedelta

import config
from rag.filters import check_filters, is_visible

FESTIVAL = config.DETAIL_TYPES["15"]
FIELDS = ("id", "title", "type", "region", "addr", "lat", "lon", "modified")


def _day(text, name: str):
    """'2026-11-14' 를 날짜로. 읽지 못하면 사유를 돌려준다."""
    try:
        return date.fromisoformat(text), None
    except (TypeError, ValueError):
        return None, f"{name} 날짜를 읽지 못했습니다: {text!r} (예: 2026-11-14)"


def _ymd(text: str):
    """저장된 '20261114' 를 날짜로. 형식이 다르면 None."""
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8])) if len(text) == 8 else None
    except (TypeError, ValueError):
        return None


def search_festivals(region: str | None, start: str, end: str, *, places: list) -> dict:
    """성공: {"ok": True, "results": [...], "count"} / 실패: {"ok": False, "reason"}. start · end 는 여행 첫날 · 마지막 날."""
    (trip_start, why_s), (trip_end, why_e) = _day(start, "시작"), _day(end, "종료")
    problem = why_s or why_e or check_filters(region, None)
    if not problem and trip_start > trip_end:
        problem = f"시작일({start})이 종료일({end})보다 늦습니다"
    if problem:
        return {"ok": False, "reason": problem}

    results = []
    for p in places:
        # 왜: 지역 · 비표출 · "여행 첫날 전에 끝난 행사" 는 검색과 같은 판정을 쓴다. 기준일로 여행 첫날을 주면 실행하는 날과 상관없이 같은 결과가 나온다. 어디: 1차 거르기.
        # 교안: 4일차 PRD "외부 의존 주입" — 오늘 날짜에 기대지 않아 테스트와 평가가 재현된다.
        if not is_visible(p, region=region, types=[FESTIVAL], today=start):
            continue
        ev_start, ev_end = _ymd(p.get("extra", {}).get("event_start", "")), _ymd(p.get("extra", {}).get("event_end", ""))
        if ev_start is None or ev_end is None:   # 기간을 모르는 행사는 "기간 안" 이라고 말할 수 없어 넣지 않는다
            continue

        # 왜: 두 기간이 겹친다 = 행사가 여행 마지막 날 이전에 시작하고 여행 첫날 이후에 끝난다. 하루만 겹쳐도 넣고, 어느 날인지를 함께 준다. 어디: 날짜 판정.
        # 교안: "숫자와 사실 판정은 코드가" (PRD F3 "축제는 여행 날짜가 행사 기간 안일 때만"). LLM 은 days_in_trip 을 옮겨 적기만 한다.
        first, last = max(trip_start, ev_start), min(trip_end, ev_end)
        if first > last:
            continue
        item = {name: p.get(name) for name in FIELDS}
        item["snippet"] = (p.get("overview") or "")[:config.SNIPPET_CHARS]
        item["event_start"], item["event_end"] = ev_start.isoformat(), ev_end.isoformat()
        item["event_place"] = p.get("extra", {}).get("event_place", "")
        item["days_in_trip"] = [(first + timedelta(days=n)).isoformat() for n in range((last - first).days + 1)]
        item["duration_days"] = (ev_end - ev_start).days + 1   # 상설 공연인지는 여기서 판단하지 않고 일수만 준다
        results.append(item)

    # 기간이 짧은 행사가 "그때만 볼 수 있는 것" 에 가깝다. 일수가 같으면 먼저 시작하는 순, 그다음 이름 순(순서 고정).
    results.sort(key=lambda x: (x["duration_days"], x["event_start"], x["title"]))
    return {"ok": True, "results": results, "count": len(results)}
