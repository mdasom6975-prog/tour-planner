"""지역 하나의 장소 목록을 받아 data/raw/list_지역.jsonl 로 저장한다. (PRD 14번 1단계 중 1-3)

상세 조회 · 정제 · 유형별 집계는 여기 없다.
실행:  python -m ingest.collect_list 강릉
"""
import json
import math
import sys
from datetime import date
from pathlib import Path

import config
from ingest.tourapi import call

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def _check_region(items: list, keyword: str) -> tuple[bool, str]:
    # 왜: 행정구역 개편으로 코드가 바뀌면 엉뚱한 지역이 오므로 주소로 감지한다. 어디: 첫 페이지 직후.
    # 교안: 2일차 Part3 "코드로 되는 검사는 코드로 먼저" — 사람이 눈으로 하던 확인을 규칙 검사로.
    with_addr = [i for i in items if i.get("addr1")]
    if not with_addr:
        return False, "주소가 있는 장소가 한 건도 없습니다"
    matched = sum(keyword in i["addr1"] for i in with_addr)
    ratio = matched / len(with_addr)
    if ratio < config.REGION_ADDR_MATCH_MIN:
        return False, f"주소에 '{keyword}' 가 있는 비율 {ratio:.0%} (기준 {config.REGION_ADDR_MATCH_MIN:.0%})"
    return True, f"주소 일치 {matched}/{len(with_addr)}"


def collect_list(region: str, today: str | None = None) -> dict:
    """성공: {"ok": True, "region", "count", "calls", "path", "skipped"} / 실패: {"ok": False, "reason"}"""
    # 왜: 설정에 없는 지역을 조용히 넘기면 빈 파일이 생긴다. 어디: 함수 맨 앞의 입력 검사.
    # 교안: 4일차 PRD F1 "지원하지 않는 지역이면 지어내지 않고 안내" 와 같은 태도.
    if region not in config.REGIONS:
        return {"ok": False, "reason": f"config.REGIONS 에 '{region}' 이 없습니다"}
    spec = config.REGIONS[region]
    path = RAW_DIR / f"list_{region}.jsonl"

    # 왜: 하루 한도가 있어 같은 것을 두 번 받지 않는다. 어디: 호출 전에 파일 존재 확인.
    # 교안: 4일차 PRD 위험 대응 "무료 API 호출 제한 → 결과 캐시".
    if path.exists():
        count = sum(1 for _ in path.open(encoding="utf-8"))
        return {"ok": True, "region": region, "count": count, "calls": 0, "path": str(path), "skipped": True}

    # 왜: 첫 페이지를 받아야 전체 건수를 알고 남은 페이지 수를 계산할 수 있다. 어디: 수집의 시작.
    # 교안: 직접 대응 없음 (페이지 넘기기). 숫자 계산을 코드가 한다는 점은 "숫자는 코드가" 원칙.
    size = config.LIST_PAGE_SIZE
    first = call("areaBasedList2", {**spec["codes"], "numOfRows": size, "pageNo": 1}, today=today)
    if not first["ok"]:
        return {"ok": False, "reason": f"1쪽 실패: {first['reason']}"}
    total = int(first["total"])
    if total == 0:
        return {"ok": False, "reason": "전체 0건. 지역 코드를 다시 확인하세요"}

    ok, msg = _check_region(first["items"], spec["addr_keyword"])
    if not ok:
        return {"ok": False, "reason": f"지역 코드 확인 필요: {msg}"}

    # 왜: 한 쪽이라도 실패하면 반쪽 파일을 남기지 않으려고 메모리에 모았다가 마지막에 쓴다. 어디: 2쪽 이후.
    # 교안: 3일차 Part2 "에러도 결과로" — 중간 실패를 예외가 아니라 사유가 담긴 결과로 돌려준다.
    items = list(first["items"])
    pages = math.ceil(total / size)
    for page in range(2, pages + 1):
        r = call("areaBasedList2", {**spec["codes"], "numOfRows": size, "pageNo": page}, today=today)
        if not r["ok"]:
            return {"ok": False, "reason": f"{page}/{pages}쪽 실패: {r['reason']} (파일을 만들지 않았습니다)"}
        items.extend(r["items"])

    # 왜: 쪽을 넘기는 사이 순서가 흔들리면 누락 · 중복이 생기므로 저장 전에 센다. 어디: 저장 직전 검증.
    # 교안: 2일차 Part4 "출력 검증" 과 같은 생각 — 받은 것을 쓰기 전에 코드로 확인한다.
    ids = [i.get("contentid") for i in items]
    if len(items) != total or len(set(ids)) != len(ids):
        return {
            "ok": False,
            "reason": f"건수 불일치: 받은 {len(items)}건, 중복 없는 ID {len(set(ids))}건, 서버 전체 {total}건 (파일을 만들지 않았습니다)",
        }

    # 왜: 검색 필터는 바뀔 수 있는 법정동 코드 대신 우리가 정한 지역 이름을 쓴다. 어디: 저장하는 줄마다.
    # 교안: RAG 실습1 Q1 — corpus 를 한 줄에 문서 한 건인 jsonl 로 저장하던 방식.
    collected = today or date.today().isoformat()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps({**item, "region": region, "collected_at": collected}, ensure_ascii=False) + "\n")

    return {"ok": True, "region": region, "count": len(items), "calls": pages, "path": str(path), "skipped": False, "check": msg}


if __name__ == "__main__":
    # 왜: 지역을 하나씩 받아 결과를 보고 다음으로 넘어가기 위해서다. 어디: 터미널 실행.
    # 교안: 4일차 "한 단계씩 실행하고 결과를 확인" 하는 진행 방식.
    for name in sys.argv[1:]:
        print(name, collect_list(name))
