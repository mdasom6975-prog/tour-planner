"""진행 중이거나 앞으로 열리는 축제 · 행사의 목록을 받아 data/raw/festivals_active.jsonl 로 저장한다. (S-2a)

상세(소개글 · 프로그램)는 여기서 받지 않는다. 그것은 ingest.collect_detail 의 일이다.
실행:  python -m ingest.collect_festivals
"""
import json
from datetime import date
from pathlib import Path

import config
from ingest.tourapi import call

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUT_PATH = RAW_DIR / "festivals_active.jsonl"


def _list_ids(region: str) -> set:
    # 왜: 대기열은 지역 목록에서 만들므로, 목록에 없는 행사는 대기열에 넣을 수 없다. 어디: 받은 ID 대조.
    # 교안: 2일차 Part4 "출력 검증" 과 같은 생각 — 받은 값을 쓰기 전에 이미 가진 것과 맞춰 본다.
    path = RAW_DIR / f"list_{region}.jsonl"
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return {json.loads(line)["contentid"] for line in f if line.strip()}


def collect_active_festivals(today: str | None = None) -> dict:
    """성공: {"ok": True, "count", "by_region", "not_in_list", "calls", "path"} / 실패: {"ok": False, "reason"}"""
    # 왜: "지금 쓸 수 있는 축제" 는 날짜에 따라 달라지므로 기준일을 인자로 받는다. 어디: 조회 조건과 상태 판정.
    # 교안: 4일차 PRD "가짜 날씨 데이터를 주입" — 오늘 날짜도 바꿔 끼울 수 있어야 시험할 수 있다.
    today = today or date.today().isoformat()
    ymd = today.replace("-", "")

    rows, by_region, not_in_list, calls = [], {}, 0, 0
    for region, spec in config.REGIONS.items():
        # 왜: 행사 기간 조회는 목록 단계에서 시작일 · 종료일을 준다. 상세를 장소마다 부르지 않아도 된다. 어디: 지역당 1건.
        # 교안: 3일차 Part2 "도구는 한 가지 일만" — 지역 목록 수집(areaBasedList2)과 다른 오퍼레이션이라 함수도 따로 둔다.
        r = call("searchFestival2", {**spec["codes"], "eventStartDate": ymd, "numOfRows": config.LIST_PAGE_SIZE})
        calls += 1
        if not r["ok"]:
            return {"ok": False, "reason": f"{region} 실패: {r['reason']} (파일을 만들지 않았습니다)"}
        # 한 번에 다 오지 않으면 일부만 저장하게 되므로 멈춘다. (2026-11-11 측정: 가장 많은 서울이 28건)
        if int(r["total"]) != len(r["items"]):
            return {"ok": False, "reason": f"{region}: 전체 {r['total']}건 중 {len(r['items'])}건만 왔습니다. 쪽 넘기기가 필요합니다"}

        known = _list_ids(region)
        for item in r["items"]:
            start, end = item.get("eventstartdate", ""), item.get("eventenddate", "")
            in_list = item["contentid"] in known
            not_in_list += not in_list
            rows.append({
                "contentid": item["contentid"],
                "title": item.get("title", ""),
                "region": region,
                "event_start": start,
                "event_end": end,
                # 왜: 시작일이 기준일보다 뒤면 예정, 아니면 진행 중이다. 날짜 비교는 코드가 한다. 어디: 화면 · 대기열.
                # 교안: "숫자와 사실 판정은 코드가".
                "status": "예정" if start > ymd else "진행 중",
                "in_list": in_list,
                "as_of": today,
            })
        by_region[region] = len(r["items"])

    # 왜: 날짜가 지나면 바뀌는 값이라 "있으면 건너뛰기" 를 하지 않고 매번 새로 쓴다. 어디: 저장.
    # 교안: 직접 대응 없음. 목록 수집(1-3)의 캐시와 반대 방향의 판단이다.
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {"ok": True, "as_of": today, "count": len(rows), "by_region": by_region,
            "not_in_list": not_in_list, "calls": calls, "path": str(OUT_PATH)}


if __name__ == "__main__":
    print(collect_active_festivals())
