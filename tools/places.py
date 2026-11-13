"""장소 검색 도구. 2단계 검색기를 감싸 뒤 단계가 쓰는 칸(좌표 · 주소 · 발췌)을 채워 돌려준다. (PRD 9번 search_places, 14번 4단계 중 4-2)

실시간 재확인 도구 get_place_detail(4-5b)도 이 파일에 있다. "찾지 못했습니다" 판단(5단계) · 시군 단위 거르기(조건 이해 단계) · 휴무일과 행사 기간(다른 도구)은 여기 없다.
"""
import time as _time
from datetime import date as _date

import config
from harness.logs import get_logger
from ingest.clean import _text, detail_fields

log = get_logger("tools.places")

FIELDS = ("id", "title", "type", "region", "addr", "lat", "lon", "modified")


def search_places(query: str, region: str | None = None, types: list | None = None, k: int | None = None, *,
                  retriever, today: str | None = None, trace=None, area: str | None = None) -> dict:
    """성공: {"ok": True, "results": [...], "count", "top_score", "took_ms"} / 실패: {"ok": False, "reason"}"""
    # 왜: 검색기는 준비에 14초 · 모델 2GB 라 한 번 만들어 나눠 쓴다. 도구가 직접 만들지 않고 받아 쓰면 테스트에서 가짜로 바꿀 수 있다. 어디: 인자 retriever · today.
    # 교안: 3일차 Part2 도구 5조건 · 4일차 PRD "외부 의존 주입". day3_tools.py 의 도구가 실패를 dict 로 돌려주던 모양.
    try:
        found = retriever.search(query, k=k, region=region, types=types, today=today, trace=trace, area=area)
    except Exception as e:   # 검색기 안에서 예상 못 한 오류가 나도 그래프가 멈추지 않게 한다
        log.exception("검색 중 오류 region=%s types=%s", region, types)
        return {"ok": False, "reason": f"검색 중 오류: {type(e).__name__}"}
    if not found["ok"]:
        return {"ok": False, "reason": found["reason"]}

    # 왜: 검색기는 "잘 찾는 것" 만 맡아 ID · 점수만 준다. 거리 계산 · 지도 · 카드에 필요한 칸은 저장된 장소에서 가져와 붙인다. 어디: 결과 조립.
    # 교안: PRD 8번 "LLM 은 받은 장소 정보를 옮겨 적기만" — 여기서 준 칸만 뒤 단계의 재료가 된다. 결과 0건은 실패가 아니라 빈 목록이다.
    by_id = {p["id"]: p for p in retriever.places}
    results = []
    for r in found["results"]:
        p = by_id.get(r["id"])
        if p is None:   # 검색기와 장소 목록이 어긋난 경우. 지어내지 않고 뺀다.
            continue
        item = {name: p.get(name) for name in FIELDS}
        item["snippet"] = (p.get("overview") or "")[:config.SNIPPET_CHARS]   # 원문 앞부분 그대로 (요약 · 수정 없음)
        item["score"] = r["score"]
        # 무장애 · 반려동물은 실시간 재확인 도구가 받지 않는 정보라 여기서 저장분을 그대로 넘긴다. 없으면 빈 dict.
        item["access"] = p.get("access") or {}
        item["pet"] = p.get("pet") or {}
        results.append(item)
    return {"ok": True, "results": results, "count": len(results),
            "top_score": results[0]["score"] if results else None, "took_ms": found.get("took_ms")}


# --- 실시간 재확인 (4-5b) ---------------------------------------------------
TYPE_ID = {name: code for code, name in config.DETAIL_TYPES.items()}
BASE_FIELDS = ("id", "title", "type", "region", "addr", "lat", "lon", "image", "modified")
DETAIL_FIELDS = ("overview", "homepage", "rest_text", "hours_text", "contact", "parking", "extra", "rest_status", "rest_weekdays", "rest_nth", "rest_note")


def _live_call(operation: str, params: dict) -> dict:
    """실제 관광공사 호출. 수집의 여유분 안에서만 쓴다."""
    from ingest.tourapi import call
    return call(operation, params, margin=config.TOURAPI_LIVE_MARGIN)


def get_place_detail(content_id: str, *, places, fetch=None, today: str | None = None) -> dict:
    """성공: {"ok": True, "source": "live"|"stored", "as_of", "withdrawn", "place", "note", "calls", "took_ms"} / 실패: {"ok": False, "reason"}

    places 는 저장된 장소 목록(list) 또는 {id: 장소}. 실시간이 실패해도 저장분이 있으면 성공이고 source 가 "stored" 다.
    """
    started = _time.perf_counter()
    by_id = places if isinstance(places, dict) else {p["id"]: p for p in places}
    stored = by_id.get(str(content_id))
    # 왜: 코스의 장소는 검색 결과에 있던 ID 만 쓴다. 저장된 목록에 없는 ID 는 관광공사에 묻지도 않는다. 어디: 입력 검사.
    # 교안: PRD F3 "없는 장소가 섞이면 코드가 걸러 낸다" / 3일차 Part2 "실패도 결과로".
    if stored is None:
        return {"ok": False, "reason": f"저장된 장소에 없는 ID: {content_id}"}
    today = today or _date.today().isoformat()
    fetch = fetch or _live_call
    type_id = TYPE_ID.get(stored["type"])

    def done(source, place, note="", withdrawn=False, calls=0):
        return {"ok": True, "source": source, "as_of": today if source == "live" else stored.get("fetched", ""),
                "withdrawn": withdrawn, "place": place, "note": note, "calls": calls,
                "took_ms": round((_time.perf_counter() - started) * 1000, 1)}

    def from_stored(reason, calls):
        # 왜: 실시간이 안 되면 멈추지 않고 저장분으로 답하되, 언제 받은 값인지를 함께 준다. 화면이 "○월 ○일 기준" 이라고 밝힌다. 어디: 모든 실패 경로.
        # 교안: PRD 9번 "실시간 우선, 실패하면 저장분". 소개글만 새것이고 휴무일은 옛것인 섞인 답을 만들지 않으려고 통째로 저장분을 쓴다.
        log.warning("저장분으로 대신함 id=%s 사유=%s", content_id, reason)
        return done("stored", {k: stored.get(k) for k in BASE_FIELDS + DETAIL_FIELDS}, note=reason, calls=calls)

    if type_id is None:
        return from_stored(f"실시간 조회를 지원하지 않는 유형: {stored['type']}", 0)
    try:
        common = fetch("detailCommon2", {"contentId": str(content_id)})
        if not common["ok"]:
            return from_stored("오늘 실시간 조회 한도를 다 썼습니다" if common.get("limit") else f"소개글 조회 실패: {common['reason']}", 1 - bool(common.get("limit")))
        # 왜: 관광공사는 내려간(비표출) 콘텐츠를 보여 주지 말라고 요구한다. 조회는 성공했는데 내용이 없으면 저장분으로 되살리지 않고 내려간 장소로 표시한다. 어디: 빈 응답.
        # 교안: 2일차 Part4 "출력 전에 코드로 거른다". 검증기(6단계)가 withdrawn 인 장소를 코스에서 뺀다.
        if not common["items"]:
            log.warning("관광공사에 없는 장소 id=%s (내려간 것으로 표시)", content_id)
            return done("live", None, note="관광공사에서 더 이상 제공하지 않는 장소입니다", withdrawn=True, calls=1)
        intro = fetch("detailIntro2", {"contentId": str(content_id), "contentTypeId": type_id})
        if not intro["ok"]:
            return from_stored("오늘 실시간 조회 한도를 다 썼습니다" if intro.get("limit") else f"휴무일 조회 실패: {intro['reason']}", 2 - bool(intro.get("limit")))

        c, i = common["items"][0], (intro["items"][0] if intro["items"] else {})
        modified = c.get("modifiedtime") or ""
        # 좌표 · 지역 · 유형은 검색과 거리 계산에 이미 쓴 값이라 저장분을 그대로 둔다. 보여 주는 글만 방금 받은 것으로 바꾼다.
        place = {k: stored.get(k) for k in BASE_FIELDS}
        place.update({"title": _text(c.get("title")) or stored["title"],
                      "addr": _text(f"{c.get('addr1', '')} {c.get('addr2', '')}") or stored.get("addr"),
                      "image": c.get("firstimage") or "",
                      "modified": f"{modified[:4]}-{modified[4:6]}-{modified[6:8]}" if len(modified) >= 8 else stored.get("modified")})
        place.update(detail_fields(type_id, c, i))   # 저장분 정제와 같은 함수로 해석한다 (4-5a)
        log.info("실시간 조회 id=%s 수정일=%s", content_id, place["modified"])
        return done("live", place, calls=2)
    except Exception:   # 응답 모양이 예상과 다른 경우 등. 그래프가 멈추지 않게 저장분으로 답하고 추적을 error.log 에 남긴다.
        log.exception("실시간 조회 중 예상하지 못한 오류 id=%s", content_id)
        return from_stored("실시간 조회 중 오류", 0)
