"""장소 검색 도구. 2단계 검색기를 감싸 뒤 단계가 쓰는 칸(좌표 · 주소 · 발췌)을 채워 돌려준다. (PRD 9번 search_places, 14번 4단계 중 4-2)

"찾지 못했습니다" 판단(5단계) · 시군 단위 거르기(조건 이해 단계) · 휴무일과 행사 기간(다른 도구)은 여기 없다.
"""
import config

FIELDS = ("id", "title", "type", "region", "addr", "lat", "lon", "modified")


def search_places(query: str, region: str | None = None, types: list | None = None, k: int | None = None, *,
                  retriever, today: str | None = None, trace=None) -> dict:
    """성공: {"ok": True, "results": [...], "count", "top_score", "took_ms"} / 실패: {"ok": False, "reason"}"""
    # 왜: 검색기는 준비에 14초 · 모델 2GB 라 한 번 만들어 나눠 쓴다. 도구가 직접 만들지 않고 받아 쓰면 테스트에서 가짜로 바꿀 수 있다. 어디: 인자 retriever · today.
    # 교안: 3일차 Part2 도구 5조건 · 4일차 PRD "외부 의존 주입". day3_tools.py 의 도구가 실패를 dict 로 돌려주던 모양.
    try:
        found = retriever.search(query, k=k, region=region, types=types, today=today, trace=trace)
    except Exception as e:   # 검색기 안에서 예상 못 한 오류가 나도 그래프가 멈추지 않게 한다
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
