"""동기화 목록의 내용으로 list_지역.jsonl 을 고친다. API 를 호출하지 않는다. (PRD 9번 갱신 표, 1-7c-1)

수정된 곳은 줄을 바꾸고 새 장소는 줄을 더한다. 낡은 상세를 다시 받는 일(1-7c-2)은 여기 없다.
실행:  python -m ingest.apply_sync 강릉
"""
import json
import shutil
import sys
from pathlib import Path

import config

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def _rows(path: Path) -> list:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def apply_sync(region: str) -> dict:
    """성공: {"ok": True, "region", "before", "updated", "added", "after"} / 실패: {"ok": False, "reason"}"""
    list_path, sync_path = RAW_DIR / f"list_{region}.jsonl", RAW_DIR / f"sync_{region}.jsonl"
    missing = [p.name for p in (list_path, sync_path) if not p.exists()]
    if region not in config.REGIONS or missing:
        return {"ok": False, "reason": f"지역이 설정에 없거나 파일이 없습니다: {region} {missing}"}

    rows = _rows(list_path)
    sync = {r["contentid"]: r for r in _rows(sync_path)}
    if "addr1" not in next(iter(sync.values())):
        return {"ok": False, "reason": f"{sync_path.name} 에 주소 등 전체 항목이 없습니다. ingest.collect_sync 를 다시 실행하세요"}

    def as_list_row(s: dict) -> dict:
        # 표출 여부는 날마다 바뀌는 값이라 목록에 복사하지 않는다. 정제 단계가 동기화 파일에서 직접 읽는다.
        return {k: v for k, v in s.items() if k != "showflag"}

    # 왜: 수정일이 더 뒤인 곳만 바꾸면 몇 번 실행해도 결과가 같고, 바뀐 수를 셀 수 있다. 어디: 목록의 줄마다.
    # 교안: 4일차 PRD "결과 캐시" 를 "바뀐 것만 갱신" 으로 넓힌 것. 관광공사 요구 "전일 수정분 매일 동기화".
    updated, out, have = 0, [], set()
    for row in rows:
        cid = row["contentid"]
        have.add(cid)
        s = sync.get(cid)
        if s and s.get("modifiedtime", "") > row.get("modifiedtime", ""):
            out.append(as_list_row(s))
            updated += 1
        else:
            out.append(row)

    # 왜: 새로 생긴 장소도 목록에 있어야 대기열에 들어간다. 비표출인 새 장소는 보여 줄 수 없으므로 넣지 않는다. 어디: 목록 끝에 추가.
    # 교안: 직접 대응 없음. 기존 줄을 지우지 않는 것은 받아 둔 상세와의 연결을 끊지 않기 위해서다.
    new = [as_list_row(s) for cid, s in sync.items() if cid not in have and s.get("showflag") == "1"]
    out.extend(new)

    ids = [r["contentid"] for r in out]
    if len(out) != len(rows) + len(new) or len(set(ids)) != len(ids):
        return {"ok": False, "reason": f"건수 불일치: 기존 {len(rows)} + 새 {len(new)} ≠ {len(out)} 또는 중복 ID (파일을 바꾸지 않았습니다)"}

    # 바뀐 것이 있을 때만 쓴다. 쓰기 전에 한 벌(.bak)을 남겨 잘못됐을 때 되돌릴 수 있게 한다.
    if updated or new:
        shutil.copy2(list_path, list_path.with_name(list_path.name + ".bak"))
        with list_path.open("w", encoding="utf-8") as f:
            for r in out:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"ok": True, "region": region, "before": len(rows), "updated": updated, "added": len(new), "after": len(out)}


if __name__ == "__main__":
    for name in sys.argv[1:]:
        print(name, apply_sync(name))
