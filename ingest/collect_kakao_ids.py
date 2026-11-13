"""음식점의 카카오 장소 ID 를 찾아 저장한다. 멈췄다가 이어받을 수 있다. (지도 링크 개선 3단계)

저장하는 것은 콘텐츠 ID · 장소 ID · 조회일뿐이다. 이름 · 주소 · 좌표 · 거리는 저장하지 않는다
(카카오 이용정책: 응답 원본과 가공 데이터는 저장하지 않고, 장소 ID 와 URL 만 저장한다는 답변을 따른다).
화면 연결(4단계)은 여기 없다.
실행:  python -m ingest.collect_kakao_ids 20     ← 20곳만 (시험)
       python -m ingest.collect_kakao_ids        ← 아직 안 찾은 음식점 전부
"""
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import config
from ingest.match_kakao_place import find_kakao_place

ROOT = Path(__file__).resolve().parent.parent
PLACES_PATH = ROOT / "data" / "processed" / "places.jsonl"
IDS_PATH = ROOT / "data" / "raw" / "kakao_place_ids.jsonl"
USAGE_PATH = ROOT / "data" / "raw" / "kakao_usage.json"


def _load_done(path: Path) -> set:
    # 왜: 이미 처리한 곳은 다시 부르지 않는다 (못 찾은 곳도 포함). 어디: 이어받기.
    # 교안: 3일차 04 일정비서가 data/calendar.json 을 읽던 방식 — 파일이 없으면 빈 값으로 시작한다.
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return {json.loads(line)["contentid"] for line in f if line.strip()}


def _targets(path: Path) -> list:
    with path.open(encoding="utf-8") as f:
        return [p for p in map(json.loads, f) if p["type"] == "음식점"]


def _count_call(usage_path: Path, today: str) -> None:
    # 왜: 하루에 몇 번 불렀는지 파일에 적어 한도를 직접 볼 수 있게 한다. 어디: 호출할 때마다.
    # 교안: ingest/tourapi.py 의 _load_usage · _save_usage 와 같은 방식.
    usage = {"date": today, "count": 0}
    if usage_path.exists():
        saved = json.loads(usage_path.read_text(encoding="utf-8"))
        if saved.get("date") == today:
            usage = saved
    usage["count"] += 1
    usage_path.write_text(json.dumps(usage, ensure_ascii=False), encoding="utf-8")


def _is_no_match(reason: str) -> bool:
    # 못 찾은 것(후보 없음 · 판정 불가)과 호출 자체의 실패(키 · 서버 · 한도)를 가른다. 앞은 기록하고 뒤는 기록하지 않는다.
    return reason.startswith(("후보 없음", "판정 불가"))


def collect(limit: int | None = None, *, key: str | None = None, find=find_kakao_place, today: str | None = None,
            sleep=time.sleep, places_path: Path = PLACES_PATH, ids_path: Path = IDS_PATH,
            usage_path: Path = USAGE_PATH) -> dict:
    """성공: {"ok": True, "called", "found", "no_match", "skipped", "stopped"} / 실패: {"ok": False, "reason"}"""
    # 왜: 키 · 찾는 함수 · 날짜 · 쉬는 함수를 인자로 받아 테스트에서 가짜로 바꾼다. 어디: 함수 전체.
    # 교안: 4일차 PRD "가짜 날씨 데이터를 주입" — 외부 의존을 인자로 받는 원칙.
    if not places_path.exists():
        return {"ok": False, "reason": f"정제 파일이 없습니다: {places_path.name}. 먼저 ingest.clean 을 실행하세요"}
    today = today or date.today().isoformat()
    done = _load_done(ids_path)
    todo = [p for p in _targets(places_path) if p["id"] not in done]
    skipped = len(_targets(places_path)) - len(todo)
    if limit is not None:
        todo = todo[:limit]
    ids_path.parent.mkdir(parents=True, exist_ok=True)

    called = found = no_match = streak = 0
    stopped = "끝까지 처리"
    with ids_path.open("a", encoding="utf-8") as out:
        for p in todo:
            res = find(p["title"], p["lat"], p["lon"], key=key)
            called += 1
            _count_call(usage_path, today)
            if res["ok"]:
                streak, found = 0, found + 1
                row = {"contentid": p["id"], "place_id": res["place_id"], "date": today}
            elif _is_no_match(res["reason"]):
                streak, no_match = 0, no_match + 1
                row = {"contentid": p["id"], "place_id": None, "reason": res["reason"], "date": today}
            else:
                streak += 1
                if streak >= config.KAKAO_MAX_CONSECUTIVE_FAILURES:
                    stopped = f"연속 {streak}번 실패로 중단: {res['reason']}"
                    break
                sleep(config.KAKAO_SLEEP_SEC)
                continue
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()  # 중간에 멈춰도 받은 곳은 남는다
            sleep(config.KAKAO_SLEEP_SEC)
    if limit is not None and stopped == "끝까지 처리":
        stopped = f"요청한 {limit}곳까지 처리"
    return {"ok": True, "called": called, "found": found, "no_match": no_match, "skipped": skipped, "stopped": stopped}


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    result = collect(limit, key=os.getenv("KAKAO_REST_KEY"))
    print(result)
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
