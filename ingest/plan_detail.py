"""상세를 받을 순서를 정해 data/raw/detail_queue.jsonl 로 저장한다. API 를 호출하지 않는다. (PRD 14번 1단계 중 1-5a)

실제 상세 호출 · 이어받기는 여기 없다.
실행:  python -m ingest.plan_detail
"""
import json
from pathlib import Path

import pandas as pd

import config

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
QUEUE_PATH = RAW_DIR / "detail_queue.jsonl"


def build_queue() -> dict:
    """성공: {"ok": True, "count", "path"} / 실패: {"ok": False, "reason"}"""
    # 왜: 대기열은 이미 받은 목록에서만 만든다. 목록이 없으면 만들 수 없다. 어디: 함수 맨 앞.
    # 교안: 3일차 Part2 "에러도 결과로" — 입력이 없을 때 예외 대신 사유를 돌려준다.
    paths = [RAW_DIR / f"list_{region}.jsonl" for region in config.REGIONS]
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        return {"ok": False, "reason": f"목록 파일이 없습니다: {missing}. 먼저 ingest.collect_list 를 실행하세요"}
    df = pd.concat([pd.read_json(p, lines=True, dtype=str) for p in paths], ignore_index=True).fillna("")

    # 왜: 1차 범위(관광지 · 문화시설 · 축제 · 음식점)만 받기로 정했다. 어디: 대기열에 넣을 장소 고르기.
    # 교안: 4일차 PRD "하지 않을 것" — 범위는 코드가 아니라 설정(config)에서 정한다.
    df = df[df["contenttypeid"].isin(config.DETAIL_TYPES)].copy()

    # 왜: 묶음 안에서는 화면에 사진이 보이는 장소, 최근에 고쳐진 장소부터 받는다. 어디: 묶음 내 순서.
    # 교안: RAG 실습1 Q1 — corpus 를 만들 때 정렬 기준을 고정해 매번 같은 결과가 나오게 하던 것.
    df["has_image"] = df["firstimage"] != ""
    df = df.sort_values(
        ["region", "contenttypeid", "has_image", "modifiedtime", "contentid"],
        ascending=[True, True, False, False, True],
    )

    # 왜: 12개 묶음(지역 × 유형)에서 한 곳씩 돌아가며 뽑아야 어느 날 끊어도 고르게 섞인다. 어디: 전체 순서.
    # 교안: 2일차 Part3 "평가셋을 유형별로 고르게" 와 같은 생각. 직접 대응하는 코드는 없음.
    df["turn"] = df.groupby(["region", "contenttypeid"]).cumcount()
    df["region_order"] = df["region"].map({name: i for i, name in enumerate(config.REGIONS)})
    df["type_order"] = df["contenttypeid"].map({t: i for i, t in enumerate(config.DETAIL_TYPES)})
    df = df.sort_values(["turn", "region_order", "type_order"]).reset_index(drop=True)

    # 왜: 한 줄에 장소 한 곳이면 "어디까지 받았는지" 를 줄 번호로 이어 갈 수 있다. 어디: 1-5b 가 읽는 파일.
    # 교안: RAG 실습1 Q1 — 한 줄에 한 건인 jsonl 저장.
    with QUEUE_PATH.open("w", encoding="utf-8") as f:
        for order, row in enumerate(df.itertuples(index=False), start=1):
            f.write(json.dumps({
                "order": order,
                "contentid": row.contentid,
                "contenttypeid": row.contenttypeid,
                "region": row.region,
                "title": row.title,
                "has_image": bool(row.has_image),
                "modifiedtime": row.modifiedtime,
            }, ensure_ascii=False) + "\n")

    return {"ok": True, "count": len(df), "path": str(QUEUE_PATH)}


if __name__ == "__main__":
    print(build_queue())
