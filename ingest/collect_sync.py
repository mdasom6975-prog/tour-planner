"""지역 하나의 동기화 목록(표출 여부 · 수정일)을 받아 data/raw/sync_지역.jsonl 로 저장한다. (PRD 9번 갱신 표, 1-7a)

비표출을 검색 · 화면에서 빼는 일(1-7b) · 바뀐 곳만 다시 받는 일(1-7c)은 여기 없다.
실행:  python -m ingest.collect_sync 강릉
"""
import json
import math
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import config
from ingest.tourapi import call

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

def collect_sync(region: str, today: str | None = None) -> dict:
    """성공: {"ok": True, "region", "count", "hidden", "calls", "path"} / 실패: {"ok": False, "reason"}"""
    if region not in config.REGIONS:
        return {"ok": False, "reason": f"config.REGIONS 에 '{region}' 이 없습니다"}
    spec = config.REGIONS[region]

    # 왜: 표출 여부(showflag)는 평소 목록에는 없고 이 오퍼레이션에만 있다. 관광공사가 비표출 콘텐츠의 노출 금지를 요구했다. 어디: 수집.
    # 교안: 직접 대응 없음 (쪽 넘기기). collect_list 와 같은 방식이고 "도구는 한 가지 일만" 에 따라 받기만 한다.
    size = config.LIST_PAGE_SIZE
    items, pages, page = [], 1, 1
    while page <= pages:
        r = call("areaBasedSyncList2", {**spec["codes"], "numOfRows": size, "pageNo": page}, today=today)
        if not r["ok"]:
            return {"ok": False, "reason": f"{page}/{pages}쪽 실패: {r['reason']} (기존 파일을 그대로 둡니다)"}
        total = int(r["total"])
        pages = math.ceil(total / size)
        items.extend(r["items"])
        page += 1

    ids = [i.get("contentid") for i in items]
    if not items or len(items) != total or len(set(ids)) != len(ids):
        return {"ok": False, "reason": f"건수 불일치: 받은 {len(items)}건, 중복 없는 ID {len(set(ids))}건, 서버 전체 {total}건 (기존 파일을 그대로 둡니다)"}

    # 왜: 표출 여부는 날마다 바뀔 수 있어 목록 수집과 달리 건너뛰지 않고 매번 새로 쓴다. 다 받고 검사한 뒤에만 써서 실패하면 어제 파일이 남는다. 어디: 저장.
    # 교안: 3일차 Part2 "에러도 결과로" — 중간 실패가 반쪽 파일을 만들지 않게 한다.
    collected = today or date.today().isoformat()
    path = RAW_DIR / f"sync_{region}.jsonl"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            # 응답 항목을 전부 남긴다. 평소 목록과 항목이 같아(showflag 만 추가) 1-7c-1 이 이것으로 목록을 고친다.
            f.write(json.dumps({**item, "region": region, "collected_at": collected}, ensure_ascii=False) + "\n")

    flags = Counter(i.get("showflag") for i in items)
    return {"ok": True, "region": region, "count": len(items), "hidden": flags.get("0", 0),
            "flags": dict(flags), "calls": pages, "path": str(path)}


if __name__ == "__main__":
    for name in sys.argv[1:]:
        print(name, collect_sync(name))
