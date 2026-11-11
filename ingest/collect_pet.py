"""반려동물 동반 여행 정보를 전국분 그대로 받아 data/raw/pet.jsonl 로 저장한다. (A-2)

우리 장소와 합치는 일(A-4), 검색 본문에 넣는 일(A-5)은 여기 없다.
실행:  python -m ingest.collect_pet
"""
import json
import math
from datetime import date
from pathlib import Path

import config
from ingest.tourapi import call

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "pet.jsonl"

# 왜: 응답의 항목 이름이 약어라 뜻을 알 수 없어, 저장할 때 읽을 수 있는 이름으로 바꾼다. 어디: 저장하는 한 줄.
# 교안: 1-6a 의 FIELD_MAP 과 같은 방식 — 규칙을 if 문이 아니라 표로 둔다. 뜻은 2026-11-11 실제 값을 보고 붙였다.
FIELDS = {
    "acmpyTypeCd": "scope",          # 전구역 동반가능 / 일부구역 동반가능
    "acmpyPsblCpam": "allowed",      # 동반 가능한 동물 (예: 전 견종 동반 가능)
    "acmpyNeedMtr": "required",      # 필요 사항 (예: 목줄 착용)
    "etcAcmpyInfo": "notes",         # 기타 안내 (예: 맹견은 입마개 필수)
    "relaPosesFclty": "facilities",  # 관련 시설
    "relaFrnshPrdlst": "provided",   # 비치 품목
    "relaRntlPrdlst": "rental",      # 대여 품목
    "relaPurcPrdlst": "for_sale",    # 구매 품목
    "relaAcdntRiskMtr": "risk",      # 사고 예방 관련 사항
}


def collect_pet(today: str | None = None) -> dict:
    """성공: {"ok": True, "count", "calls", "path"} / 실패: {"ok": False, "reason"}"""
    today = today or date.today().isoformat()
    size = config.LIST_PAGE_SIZE

    # 왜: 이 오퍼레이션은 장소 ID 없이 부르면 전국분을 목록으로 준다. 장소마다 부르지 않아도 된다. 어디: 수집 전체.
    # 교안: 1-3 목록 수집과 같은 쪽 넘기기. 측정: 전국 9,635건, 10건 호출.
    first = call("detailPetTour2", {"numOfRows": size, "pageNo": 1}, today=today)
    if not first["ok"]:
        return {"ok": False, "reason": f"1쪽 실패: {first['reason']}"}
    total = int(first["total"])
    items = list(first["items"])
    pages = math.ceil(total / size)
    for page in range(2, pages + 1):
        r = call("detailPetTour2", {"numOfRows": size, "pageNo": page}, today=today)
        if not r["ok"]:
            return {"ok": False, "reason": f"{page}/{pages}쪽 실패: {r['reason']} (파일을 만들지 않았습니다)"}
        items.extend(r["items"])

    # 왜: 쪽을 넘기는 사이 순서가 흔들리면 누락 · 중복이 생기므로 저장 전에 센다. 어디: 저장 직전.
    # 교안: 2일차 Part4 "출력 검증" 과 같은 생각. 1-3 에서 쓴 검사와 같다.
    ids = [i.get("contentid") for i in items]
    if len(items) != total or len(set(ids)) != len(ids):
        return {"ok": False, "reason": f"건수 불일치: 받은 {len(items)}, 중복 없는 ID {len(set(ids))}, 서버 전체 {total} (파일을 만들지 않았습니다)"}

    # 왜: 10건이면 다시 받을 수 있어 "바뀐 것만 받기" 를 하지 않고 매번 통째로 새로 쓴다. 어디: 저장.
    # 교안: 직접 대응 없음. 우리 장소에 해당하는 것만 고르지 않고 전국분을 두는 것은 2차 확장(전통시장) 때 다시 받지 않기 위해서다.
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for item in items:
            row = {"contentid": item["contentid"], "collected_at": today}
            row.update({name: str(item.get(src) or "").strip() for src, name in FIELDS.items()})
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {"ok": True, "count": len(items), "calls": pages, "path": str(OUT_PATH)}


if __name__ == "__main__":
    print(collect_pet())
