"""매일 한 번 실행하는 수집 명령 일곱 개를 순서대로 돌리고 결과를 한 화면에 모아 보여 준다.

새 기능은 없다. 이미 있는 함수를 순서대로 부를 뿐이다.
실행:  python scripts/daily_collect.py
"""
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from ingest.clean import build_places
from ingest.collect_detail import collect_detail
from ingest.collect_festivals import collect_active_festivals
from ingest.collect_sync import RAW_DIR, collect_sync
from ingest.plan_access import OUT_PATH as ACCESS_QUEUE, build_access_queue
from ingest.plan_detail import build_queue
from ingest.tourapi import USAGE_PATH


def sync_all() -> dict:
    """여섯 지역의 동기화 목록을 받고, 비표출 수와 "목록을 받은 뒤 수정된 곳" 수를 센다."""
    # 왜: 표출 여부는 날마다 바뀌므로 대기열 · 정제보다 먼저 받아야 그날 값이 쓰인다. 한 지역이 실패하면 그 지역은 어제 파일을 그대로 쓴다. 어디: 묶음의 맨 앞.
    # 교안: 직접 대응 없음 (관광공사 요구 "매일 동기화 · 비표출 제외"). 실패를 모아 돌려주는 것은 3일차 Part2 "에러도 결과로".
    hidden, changed, calls, errors = {}, {}, 0, []
    for region in config.REGIONS:
        r = collect_sync(region)
        if not r["ok"]:
            errors.append(f"{region}: {r['reason']}")
            continue
        hidden[region], calls = r["hidden"], calls + r["calls"]
        # 우리 목록의 수정일보다 동기화 목록의 수정일이 뒤인 곳 = 다시 받아야 할 곳 (1-7c 가 쓸 수).
        with (RAW_DIR / f"sync_{region}.jsonl").open(encoding="utf-8") as f:
            newest = {x["contentid"]: x["modifiedtime"] for x in map(json.loads, f)}
        with (RAW_DIR / f"list_{region}.jsonl").open(encoding="utf-8") as f:
            changed[region] = sum(newest.get(x["contentid"], "") > x.get("modifiedtime", "") for x in map(json.loads, f))
    if errors:
        return {"ok": False, "reason": " / ".join(errors), "hidden": hidden, "changed": changed, "calls": calls}
    return {"ok": True, "hidden": hidden, "changed": changed, "calls": calls}


def main():
    started = time.perf_counter()
    failed = []

    def step(name, fn):
        # 왜: 한 단계가 실패해도 나머지는 돌려야 한다 (축제 목록이 실패해도 어제 목록으로 수집은 할 수 있다). 어디: 모든 단계.
        # 교안: 3일차 Part2 "에러도 결과로" — 실패를 모아 두었다가 마지막에 보여 준다.
        t = time.perf_counter()
        result = fn()
        took = time.perf_counter() - t
        if not result.get("ok"):
            failed.append(name)
            print(f"[실패] {name}: {result.get('reason')}")
        else:
            print(f"[완료] {name} ({took:.0f}초)")
        return result

    # 순서에 뜻이 있다: 표출 여부 · 축제 목록 → 그것을 반영한 대기열 → 대기열대로 상세 수집 → 받은 것을 정제.
    sync = step("0. 동기화 목록 (표출 여부 · 수정일)", sync_all)
    fest = step("1. 진행 중 · 예정 축제 목록", collect_active_festivals)
    queue = step("2. 받을 순서 다시 만들기", build_queue)

    # 왜: 무장애 대기열은 기존 대기열에서 만든 것이라 매일 다시 만들 필요가 없다 (목록 조회 7건을 아낀다). 어디: 파일이 없을 때만.
    # 교안: 4일차 PRD "결과 캐시" — 바뀌지 않는 것은 다시 받지 않는다.
    if not ACCESS_QUEUE.exists():
        step("   (무장애 대기열이 없어 새로 만듦)", build_access_queue)

    detail = {}
    for label, op in (("3. 소개글", "detailCommon2"), ("4. 휴무일 · 이용시간", "detailIntro2"), ("5. 무장애 정보", "detailWithTour2")):
        detail[op] = step(f"{label} ({op})", lambda op=op: collect_detail(op))
    places = step("6. 정제", build_places)

    # 왜: 일곱 단계의 결과를 따로 읽지 않고 "오늘 얼마나 받았고 며칠 남았는지" 를 한눈에 본다. 어디: 마지막 요약.
    # 교안: 2일차 Part3 비교표 — 숫자를 한 표에 모아야 판단할 수 있다.
    usage = json.loads(USAGE_PATH.read_text(encoding="utf-8")) if USAGE_PATH.exists() else {}
    remaining = usage.get("server_remaining", {})
    per_day = config.TOURAPI_DAILY_LIMIT - config.TOURAPI_SAFETY_MARGIN
    print("\n" + "=" * 62)
    print(f"수집 요약 ({usage.get('date', '?')}, {time.perf_counter() - started:.0f}초)")
    if fest.get("ok"):
        print(f"  쓸 수 있는 축제   {fest['count']}곳  {fest['by_region']}")
    if sync.get("hidden"):
        print(f"  비표출            {sum(sync['hidden'].values()):,}곳  {sync['hidden']}  (호출 {sync['calls']}회)")
        print(f"  받은 뒤 수정됨    {sum(sync['changed'].values())}곳  {sync['changed']}")
    if queue.get("ok"):
        print(f"  대기열            {queue['count']}곳  (비표출 {queue.get('excluded_hidden', '?')}곳 제외)")
    print(f"  {'':<18}{'오늘 받음':>8}{'실패':>6}{'남은 곳':>9}{'남은 일수':>9}{'서버 남은 한도':>12}")
    keys = {"detailCommon2": "detailCommon2", "detailIntro2": "detailIntro2", "detailWithTour2": "KorWithService2/detailWithTour2"}
    for label, op in (("소개글", "detailCommon2"), ("휴무일", "detailIntro2"), ("무장애", "detailWithTour2")):
        d = detail[op]
        if not d.get("ok"):
            print(f"  {label:<18}{'실패':>8}")
            continue
        got, left = d["fetched"] + d["empty"], d["remaining"]
        print(f"  {label:<18}{got:>10}{d['failed']:>8}{left:>11}{math.ceil(left / per_day):>11}{str(remaining.get(keys[op], '?')):>14}")
        if "실패로 중단" in d["stopped"]:
            print(f"    ↳ {d['stopped']}")
    if places.get("ok"):
        print(f"  정제된 장소       {places['count']}곳  {places['by_type']}")
        print(f"    ↳ 그중 비표출 {places['hidden']}곳은 검색에서 빠짐 · 표출 여부 모름 {places['showflag_unknown']}곳")
    print(f"  수집 마감         2026-11-20 (PRD 4번)")
    if failed:
        print(f"\n실패한 단계: {failed}")
    print("=" * 62)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
