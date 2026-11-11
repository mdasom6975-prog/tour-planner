"""대기열 순서대로 장소 상세를 받아 저장한다. 멈췄다가 다음 날 이어받을 수 있다. (PRD 14번 1단계 중 1-5b)

두 응답 합치기 · 항목 이름 맞추기 · 휴무일 해석은 여기 없다 (1-6 정제).
실행:  python -m ingest.collect_detail detailCommon2 5     ← 5곳만 (시험)
       python -m ingest.collect_detail detailIntro2       ← 그날 한도까지
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

import config
from ingest.tourapi import call

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
QUEUE_PATH = RAW_DIR / "detail_queue.jsonl"

# 왜: 한도가 오퍼레이션별이라 진도가 서로 달라질 수 있어 파일을 따로 둔다. 어디: 저장 위치 결정.
# 교안: 3일차 Part2 도구 설계 "한 가지 일만" — 소개글 수집과 휴무일 수집을 서로 묶지 않는다.
OUTPUT = {
    "detailCommon2": "detail_common.jsonl",
    "detailIntro2": "detail_intro.jsonl",
}


def _done_ids(path: Path) -> set:
    # 왜: "어디까지 받았나" 를 따로 적지 않고 저장 파일 자체를 기록으로 쓴다. 어디: 이어받기의 근거.
    # 교안: 3일차 05 LangGraph checkpointer 와 같은 생각 — 저장된 상태를 읽어 이어서 한다.
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return {json.loads(line)["contentid"] for line in f if line.strip()}


def collect_detail(operation: str, max_places: int | None = None, today: str | None = None) -> dict:
    """결과: {"ok", "fetched", "skipped", "empty", "failed", "stopped", "avg_sec", "remaining"}"""
    # 왜: 모르는 오퍼레이션으로 한도를 쓰지 않게 먼저 거른다. 어디: 함수 맨 앞의 입력 검사.
    # 교안: 3일차 Part2 "에러도 결과로" — 잘못된 입력도 예외 대신 사유를 돌려준다.
    if operation not in OUTPUT:
        return {"ok": False, "reason": f"지원하지 않는 오퍼레이션: {operation}. 가능: {list(OUTPUT)}"}
    if not QUEUE_PATH.exists():
        return {"ok": False, "reason": "대기열이 없습니다. 먼저 ingest.plan_detail 을 실행하세요"}

    out_path = RAW_DIR / OUTPUT[operation]
    done = _done_ids(out_path)
    with QUEUE_PATH.open(encoding="utf-8") as f:
        queue = [json.loads(line) for line in f if line.strip()]

    collected = today or date.today().isoformat()
    fetched = skipped = empty = failed = consecutive = 0
    elapsed = 0.0
    stopped = "대기열 끝"

    # 왜: 받는 즉시 한 줄씩 덧붙여야 중간에 꺼져도 그때까지 받은 것이 남는다. 어디: 수집 전체.
    # 교안: 직접 대응 없음. 목록(1-3)은 "전부 성공해야 저장" 이었지만 950건은 다시 받기 비싸 반대로 한다.
    with out_path.open("a", encoding="utf-8") as out:
        for place in queue:
            if place["contentid"] in done:
                skipped += 1
                continue

            # 왜: 시험할 때 몇 곳만 받고 멈추기 위해서다. 어디: 호출 전 상한 검사.
            # 교안: 3일차 day3_tools.run_agent 의 max_rounds — 반복에는 코드로 정한 상한을 둔다.
            if max_places is not None and fetched + empty >= max_places:
                stopped = f"요청한 {max_places}곳 완료"
                break

            # 왜: 휴무일 조회는 유형을 함께 보내야 그 유형의 항목이 온다 (1-4b 에서 그렇게 불러 확인). 어디: 조회 조건.
            # 교안: 3일차 Part2 "도구 입력은 필요한 것만 명확하게".
            params = {"contentId": place["contentid"]}
            if operation == "detailIntro2":
                params["contentTypeId"] = place["contenttypeid"]

            started = time.perf_counter()
            r = call(operation, params, today=today)
            elapsed += time.perf_counter() - started

            # 왜: 한도 도달은 실패가 아니라 "오늘 분량 끝" 이므로 따로 다룬다. 어디: 호출 결과 분기.
            # 교안: 3일차 Part4 "안전장치는 코드에" — 한도를 넘기지 않는 판단을 코드가 한다.
            if r.get("limit"):
                stopped = "오늘 한도 도달. 내일 같은 명령으로 이어받습니다"
                break

            # 왜: 서버 장애 때 실패만 반복하며 한도를 태우지 않게 연속 실패를 센다. 어디: 실패 처리.
            # 교안: RAG 실습2 Q6 — 재시도 횟수가 상한에 닿으면 포기(abstain)로 빠지던 조건부 edge.
            if not r["ok"]:
                failed += 1
                consecutive += 1
                if consecutive >= config.DETAIL_MAX_CONSECUTIVE_FAILURES:
                    stopped = f"연속 {consecutive}번 실패로 중단. 마지막 사유: {r['reason']}"
                    break
                continue
            consecutive = 0

            # 왜: 내용이 0건인 곳도 기록해야 내일 또 불러 한도를 낭비하지 않는다. 어디: 저장하는 줄.
            # 교안: 3일차 03 가이드북 "없으면 '찾을 수 없음'" — 없다는 사실도 결과로 남긴다.
            item = r["items"][0] if r["items"] else None
            out.write(json.dumps({
                "contentid": place["contentid"],
                "contenttypeid": place["contenttypeid"],
                "region": place["region"],
                "collected_at": collected,
                "empty": item is None,
                "data": item,
            }, ensure_ascii=False) + "\n")
            out.flush()
            if item is None:
                empty += 1
            else:
                fetched += 1

            if (fetched + empty) % 100 == 0:
                print(f"  {operation}: {fetched + empty}곳 받음", flush=True)
            time.sleep(config.TOURAPI_SLEEP_SEC)

    calls = fetched + empty + failed
    return {
        "ok": True,
        "operation": operation,
        "fetched": fetched,
        "skipped": skipped,
        "empty": empty,
        "failed": failed,
        "stopped": stopped,
        "avg_sec": round(elapsed / calls, 3) if calls else None,
        # 이미 받았지만 대기열에서 빠진 곳(끝난 축제)이 있어, 대기열에 있는 것만 센다.
        "remaining": sum(1 for p in queue if p["contentid"] not in done) - fetched - empty,
    }


if __name__ == "__main__":
    op = sys.argv[1] if len(sys.argv) > 1 else ""
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    print(collect_detail(op, limit))
