"""ingest/collect_kakao_ids.py 를 가짜 찾기 함수로 검증한다. 실제 호출은 하지 않는다."""
import json

import config
from ingest.collect_kakao_ids import collect


def make_places(tmp_path, n_food=3):
    rows = [{"id": f"F{i}", "type": "음식점", "title": f"가게{i}", "lat": "35.0", "lon": "129.0"} for i in range(n_food)]
    rows.append({"id": "T1", "type": "관광지", "title": "공원", "lat": "35.0", "lon": "129.0"})
    path = tmp_path / "places.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return path


def run(tmp_path, find, limit=None, places=None, today="2026-11-13"):
    return collect(limit, key="K", find=find, today=today, sleep=lambda s: None,
                   places_path=places or make_places(tmp_path), ids_path=tmp_path / "ids.jsonl",
                   usage_path=tmp_path / "usage.json")


def ok_find(name, lat, lon, *, key):
    # 이름 · 거리 같은 응답 내용을 담아 돌려줘도 저장되면 안 된다.
    return {"ok": True, "place_id": f"id-{name}", "place_name": name, "distance_m": 3, "method": "name"}


def lines(tmp_path):
    return [json.loads(l) for l in (tmp_path / "ids.jsonl").read_text(encoding="utf-8").splitlines()]


def test_음식점만_찾고_저장에는_ID와_날짜만_남긴다(tmp_path):
    r = run(tmp_path, ok_find)
    assert (r["called"], r["found"]) == (3, 3)               # 관광지는 대상이 아니다
    for row in lines(tmp_path):
        assert set(row) == {"contentid", "place_id", "date"}  # 이름 · 좌표 · 거리 · 방식은 저장하지 않는다
    assert lines(tmp_path)[0] == {"contentid": "F0", "place_id": "id-가게0", "date": "2026-11-13"}


def test_다시_실행하면_이미_처리한_곳은_부르지_않는다(tmp_path):
    places = make_places(tmp_path)
    run(tmp_path, ok_find, places=places)
    again = run(tmp_path, ok_find, places=places)
    assert again["called"] == 0 and again["skipped"] == 3
    assert len(lines(tmp_path)) == 3


def test_못_찾은_곳은_null로_기록하고_다시_부르지_않는다(tmp_path):
    places = make_places(tmp_path, n_food=1)
    nothing = lambda name, lat, lon, *, key: {"ok": False, "reason": "후보 없음"}  # noqa: E731
    r = run(tmp_path, nothing, places=places)
    assert r["no_match"] == 1
    assert lines(tmp_path) == [{"contentid": "F0", "place_id": None, "reason": "후보 없음", "date": "2026-11-13"}]
    assert run(tmp_path, nothing, places=places)["called"] == 0


def test_연속_실패하면_멈추고_그_곳은_기록하지_않는다(tmp_path):
    places = make_places(tmp_path, n_food=config.KAKAO_MAX_CONSECUTIVE_FAILURES + 2)
    down = lambda name, lat, lon, *, key: {"ok": False, "reason": "HTTP 429"}  # noqa: E731
    r = run(tmp_path, down, places=places)
    assert r["called"] == config.KAKAO_MAX_CONSECUTIVE_FAILURES and "중단" in r["stopped"]
    assert not (tmp_path / "ids.jsonl").read_text(encoding="utf-8")   # 실패한 곳은 다음에 다시 시도한다


def test_호출_횟수를_날짜별로_적는다(tmp_path):
    places = make_places(tmp_path)
    run(tmp_path, ok_find, limit=2, places=places)
    assert json.loads((tmp_path / "usage.json").read_text(encoding="utf-8")) == {"date": "2026-11-13", "count": 2}
    run(tmp_path, ok_find, places=places, today="2026-11-14")      # 날짜가 바뀌면 새로 센다
    assert json.loads((tmp_path / "usage.json").read_text(encoding="utf-8")) == {"date": "2026-11-14", "count": 1}


def test_곳_수를_정하면_그만큼만_처리한다(tmp_path):
    r = run(tmp_path, ok_find, limit=2)
    assert r["called"] == 2 and len(lines(tmp_path)) == 2
