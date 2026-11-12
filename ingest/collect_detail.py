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
# 무장애 정보(detailWithTour2)는 서비스 · 대기열 · 저장 파일이 다르지만 "순서대로 받아 덧붙이고 이어받는" 동작은 같다.
# 같은 동작을 두 벌 두면 한쪽만 고쳐지므로, 다른 점만 표로 두고 함수는 하나로 쓴다. (A-3)
OPERATIONS = {
    "detailCommon2":   {"file": "detail_common.jsonl", "queue": "detail_queue.jsonl", "service": None, "send_type": False, "plan": "ingest.plan_detail"},
    "detailIntro2":    {"file": "detail_intro.jsonl",  "queue": "detail_queue.jsonl", "service": None, "send_type": True,  "plan": "ingest.plan_detail"},
    "detailWithTour2": {"file": "access.jsonl",        "queue": "access_queue.jsonl", "service": "KorWithService2", "send_type": False, "plan": "ingest.plan_access"},
}


def _done(path: Path) -> dict:
    """받은 곳마다 "그때 기준이 된 수정 시각" 을 돌려준다. {contentid: "YYYYMMDDhhmmss"}"""
    # 왜: "어디까지 받았나" 를 따로 적지 않고 저장 파일 자체를 기록으로 쓴다. 같은 곳이 여러 줄이면 마지막 줄이 최신이다. 어디: 이어받기의 근거.
    # 교안: 3일차 05 LangGraph checkpointer 와 같은 생각 — 저장된 상태를 읽어 이어서 한다.
    done = {}
    if not path.exists():
        return done
    with path.open(encoding="utf-8") as f:
        for row in (json.loads(line) for line in f if line.strip()):
            # 1-7c-2 전에 받은 줄에는 수정 시각이 없어 받은 날의 0시로 본다. 같은 날 수정된 곳은 낡은 것으로 보고 다시 받는다(안전한 쪽).
            done[row["contentid"]] = row.get("source_modified") or row["collected_at"].replace("-", "") + "000000"
    return done


def _modified_now() -> dict:
    # 왜: 대기열의 수정 시각은 만든 날 것이라 낡았을 수 있다(무장애 대기열은 매일 다시 만들지 않는다). 매일 갱신되는 목록에서 직접 읽는다. 어디: 낡음 판정.
    # 교안: 직접 대응 없음. "숫자와 사실 판정은 코드가" — 다시 받을지를 날짜 비교로 정한다.
    modified = {}
    for region in config.REGIONS:
        path = RAW_DIR / f"list_{region}.jsonl"
        if path.exists():
            with path.open(encoding="utf-8") as f:
                modified.update({r["contentid"]: r.get("modifiedtime", "") for r in map(json.loads, f)})
    return modified


def collect_detail(operation: str, max_places: int | None = None, today: str | None = None) -> dict:
    """결과: {"ok", "fetched", "refreshed", "stale", "skipped", "empty", "failed", "stopped", "avg_sec", "remaining"}"""
    # 왜: 모르는 오퍼레이션으로 한도를 쓰지 않게 먼저 거른다. 어디: 함수 맨 앞의 입력 검사.
    # 교안: 3일차 Part2 "에러도 결과로" — 잘못된 입력도 예외 대신 사유를 돌려준다.
    if operation not in OPERATIONS:
        return {"ok": False, "reason": f"지원하지 않는 오퍼레이션: {operation}. 가능: {list(OPERATIONS)}"}
    spec = OPERATIONS[operation]
    queue_path = RAW_DIR / spec["queue"]
    if not queue_path.exists():
        return {"ok": False, "reason": f"대기열({spec['queue']})이 없습니다. 먼저 {spec['plan']} 을 실행하세요"}

    out_path = RAW_DIR / spec["file"]
    done = _done(out_path)
    with queue_path.open(encoding="utf-8") as f:
        queue = [json.loads(line) for line in f if line.strip()]

    # 왜: 받은 뒤에 관광공사가 고친 곳은 저장본이 낡았다. 관광공사 요구(매일 동기화)에 따라 새 장소보다 먼저 다시 받는다. 어디: 받을 순서.
    # 교안: 4일차 PRD "결과 캐시" 의 짝 — 캐시는 원본이 바뀌면 버려야 한다. 순서(낡은 것 먼저)는 2026-11-12 에 정했다.
    modified = _modified_now()
    stale_ids = {p["contentid"] for p in queue if p["contentid"] in done and modified.get(p["contentid"], "") > done[p["contentid"]]}
    queue = [p for p in queue if p["contentid"] in stale_ids] + [p for p in queue if p["contentid"] not in stale_ids]
    waiting = sum(1 for p in queue if p["contentid"] not in done)

    collected = today or date.today().isoformat()
    fetched = refreshed = skipped = empty = failed = consecutive = 0
    elapsed = 0.0
    stopped = "대기열 끝"

    # 왜: 받는 즉시 한 줄씩 덧붙여야 중간에 꺼져도 그때까지 받은 것이 남는다. 어디: 수집 전체.
    # 교안: 직접 대응 없음. 목록(1-3)은 "전부 성공해야 저장" 이었지만 950건은 다시 받기 비싸 반대로 한다.
    with out_path.open("a", encoding="utf-8") as out:
        for place in queue:
            is_stale = place["contentid"] in stale_ids
            if place["contentid"] in done and not is_stale:
                skipped += 1
                continue

            # 왜: 시험할 때 몇 곳만 받고 멈추기 위해서다. 어디: 호출 전 상한 검사.
            # 교안: 3일차 day3_tools.run_agent 의 max_rounds — 반복에는 코드로 정한 상한을 둔다.
            if max_places is not None and fetched + refreshed + empty >= max_places:
                stopped = f"요청한 {max_places}곳 완료"
                break

            # 왜: 휴무일 조회는 유형을 함께 보내야 그 유형의 항목이 온다 (1-4b 에서 그렇게 불러 확인). 어디: 조회 조건.
            # 교안: 3일차 Part2 "도구 입력은 필요한 것만 명확하게".
            params = {"contentId": place["contentid"]}
            if spec["send_type"]:
                params["contentTypeId"] = place["contenttypeid"]

            started = time.perf_counter()
            r = call(operation, params, today=today, service=spec["service"])
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
                "source_modified": modified.get(place["contentid"], ""),   # 이 시각까지의 수정분이 반영된 응답이다
                "empty": item is None,
                "data": item,
            }, ensure_ascii=False) + "\n")
            out.flush()
            # 다시 받은 곳은 새로 받은 곳과 따로 센다 (남은 곳 계산에 들어가면 안 된다).
            if is_stale:
                refreshed += 1
            elif item is None:
                empty += 1
            else:
                fetched += 1

            if (fetched + refreshed + empty) % 100 == 0:
                print(f"  {operation}: {fetched + refreshed + empty}곳 받음", flush=True)
            time.sleep(config.TOURAPI_SLEEP_SEC)

    calls = fetched + refreshed + empty + failed
    return {
        "ok": True,
        "operation": operation,
        "fetched": fetched,
        "refreshed": refreshed,          # 낡아서 다시 받은 곳
        "stale": len(stale_ids),         # 시작할 때 낡아 있던 곳
        "skipped": skipped,
        "empty": empty,
        "failed": failed,
        "stopped": stopped,
        "avg_sec": round(elapsed / calls, 3) if calls else None,
        # 이미 받았지만 대기열에서 빠진 곳(끝난 축제)이 있어, 대기열에 있는 것만 센다.
        "remaining": waiting - fetched - empty,
    }


if __name__ == "__main__":
    op = sys.argv[1] if len(sys.argv) > 1 else ""
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    print(collect_detail(op, limit))
