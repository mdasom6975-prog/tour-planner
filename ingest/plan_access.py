"""무장애 정보를 받을 장소와 순서를 정해 data/raw/access_queue.jsonl 로 저장한다. (A-3)

상세(휠체어 · 엘리베이터 · 유모차 등)는 여기서 받지 않는다. 그것은 ingest.collect_detail detailWithTour2 의 일이다.
실행:  python -m ingest.plan_access
"""
import json
import math
from pathlib import Path

import config
from ingest.tourapi import call

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
MAIN_QUEUE = RAW_DIR / "detail_queue.jsonl"
OUT_PATH = RAW_DIR / "access_queue.jsonl"
SERVICE = "KorWithService2"


def build_access_queue(today: str | None = None) -> dict:
    """성공: {"ok": True, "count", "by_region", "listed", "calls", "path"} / 실패: {"ok": False, "reason"}"""
    # 왜: 무장애 정보는 우리가 다루는 장소(1차 범위)에 해당하는 것만 받는다. 범위는 기존 대기열이 정한다. 어디: 함수 맨 앞.
    # 교안: 3일차 Part2 "에러도 결과로".
    if not MAIN_QUEUE.exists():
        return {"ok": False, "reason": "기존 대기열이 없습니다. 먼저 ingest.plan_detail 을 실행하세요"}
    with MAIN_QUEUE.open(encoding="utf-8") as f:
        main = [json.loads(line) for line in f if line.strip()]

    # 왜: 어느 장소에 무장애 정보가 있는지는 무장애 서비스의 목록이 알려 준다. 지역당 1~2건이면 된다. 어디: 대상 고르기.
    # 교안: 1-3 목록 수집과 같은 쪽 넘기기. 다른 점은 서비스가 다르다는 것뿐이라 call() 의 service 인자만 바꾼다.
    has_info, listed, calls = set(), {}, 0
    size = config.LIST_PAGE_SIZE
    for region, spec in config.REGIONS.items():
        first = call("areaBasedList2", {**spec["codes"], "numOfRows": size, "pageNo": 1}, today=today, service=SERVICE)
        calls += 1
        if not first["ok"]:
            return {"ok": False, "reason": f"{region} 1쪽 실패: {first['reason']} (파일을 만들지 않았습니다)"}
        items = list(first["items"])
        for page in range(2, math.ceil(int(first["total"]) / size) + 1):
            r = call("areaBasedList2", {**spec["codes"], "numOfRows": size, "pageNo": page}, today=today, service=SERVICE)
            calls += 1
            if not r["ok"]:
                return {"ok": False, "reason": f"{region} {page}쪽 실패: {r['reason']} (파일을 만들지 않았습니다)"}
            items.extend(r["items"])
        if len(items) != int(first["total"]):
            return {"ok": False, "reason": f"{region}: 전체 {first['total']}건 중 {len(items)}건만 왔습니다 (파일을 만들지 않았습니다)"}
        listed[region] = len(items)
        has_info.update(i["contentid"] for i in items)

    # 왜: 기존 대기열의 순서를 그대로 따르면, 소개글을 먼저 받는 장소가 접근성 정보도 먼저 받는다. 어느 날 멈춰도 둘 다 갖춘 곳이 최대가 된다. 어디: 순서.
    # 교안: 1-5a 대기열과 같은 생각. 순서 규칙을 두 번 만들지 않고 이미 정한 순서를 다시 쓴다.
    rows, by_region = [], {}
    for place in main:
        if place["contentid"] in has_info:
            rows.append({k: place[k] for k in ("contentid", "contenttypeid", "region", "title")})
            by_region[place["region"]] = by_region.get(place["region"], 0) + 1

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for order, row in enumerate(rows, start=1):
            f.write(json.dumps({"order": order, **row}, ensure_ascii=False) + "\n")

    return {"ok": True, "count": len(rows), "by_region": by_region, "listed": listed, "calls": calls, "path": str(OUT_PATH)}


if __name__ == "__main__":
    print(build_access_queue())
