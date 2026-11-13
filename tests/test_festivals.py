"""tools/festivals.py 의 search_festivals 를 손으로 센 날짜와 대조한다."""
import pytest

from tools.festivals import search_festivals


def _f(pid, start, end, region="부산", type_="축제·행사", **more):
    base = {"id": pid, "title": f"행사{pid}", "type": type_, "region": region, "addr": "주소", "lat": 35.1, "lon": 129.0,
            "modified": "2026-11-01", "overview": "소개", "showflag": "1", "extra": {"event_start": start, "event_end": end, "event_place": "광장"}}
    base.update(more)
    return base


TRIP = ("2026-11-14", "2026-11-16")   # 2박 3일


def _ids(places, region="부산", trip=TRIP):
    r = search_festivals(region, *trip, places=places)
    assert r["ok"]
    return [x["id"] for x in r["results"]]


def test_경계_하루라도_겹치면_넣는다():
    places = [_f("끝-첫날", "20261110", "20261114"), _f("끝-전날", "20261110", "20261113"),
              _f("시작-막날", "20261116", "20261120"), _f("시작-다음날", "20261117", "20261120")]
    assert sorted(_ids(places)) == sorted(["끝-첫날", "시작-막날"])


def test_겹치는_날짜와_행사_일수():
    r = search_festivals("부산", *TRIP, places=[_f("a", "20261115", "20261130"), _f("b", "20260101", "20261231")])
    a, b = r["results"]
    assert a["id"] == "a" and a["days_in_trip"] == ["2026-11-15", "2026-11-16"] and a["duration_days"] == 16
    assert b["days_in_trip"] == ["2026-11-14", "2026-11-15", "2026-11-16"] and b["duration_days"] == 365
    assert (a["event_start"], a["event_end"], a["event_place"]) == ("2026-11-15", "2026-11-30", "광장")


def test_당일_여행과_하루짜리_행사():
    r = search_festivals("부산", "2026-11-14", "2026-11-14", places=[_f("a", "20261114", "20261114")])
    assert r["results"][0]["days_in_trip"] == ["2026-11-14"] and r["results"][0]["duration_days"] == 1


def test_짧은_행사부터():
    places = [_f("일년", "20260101", "20261231"), _f("사흘", "20261114", "20261116"), _f("한달", "20261101", "20261130")]
    assert _ids(places) == ["사흘", "한달", "일년"]


def test_다른_지역_다른_유형_비표출은_뺀다():
    places = [_f("부산", "20261114", "20261116"), _f("서울", "20261114", "20261116", region="서울"),
              _f("식당", "20261114", "20261116", type_="음식점"), _f("숨김", "20261114", "20261116", showflag="0")]
    assert _ids(places) == ["부산"]
    assert sorted(_ids(places, region=None)) == ["부산", "서울"]   # 지역을 비우면 전체


def test_기간을_모르는_행사는_넣지_않는다():
    places = [_f("빈값", "", ""), _f("이상", "2026", "20261116"), _f("없는날", "20261131", "20261231")]
    places.append({**_f("칸없음", "20261114", "20261116"), "extra": {}})
    assert _ids(places) == []


def test_0건은_실패가_아니다():
    assert search_festivals("부산", *TRIP, places=[]) == {"ok": True, "results": [], "count": 0}


@pytest.mark.parametrize("region, start, end", [
    ("부산", "2026/11/14", "2026-11-16"), ("부산", "2026-11-14", None), ("부산", "2026-11-31", "2026-12-01"),
    ("부산", "2026-11-16", "2026-11-14"), ("대구", "2026-11-14", "2026-11-16")])
def test_잘못된_입력은_실패를_결과로(region, start, end):
    r = search_festivals(region, start, end, places=[_f("a", "20261114", "20261116")])
    assert r["ok"] is False and r["reason"]


def test_실행하는_날과_상관없이_같은_결과():
    # 이미 지난 날짜의 여행을 넣어도(평가 재현) 그 기간의 행사가 나온다
    assert _ids([_f("옛", "20250101", "20250103")], trip=("2025-01-02", "2025-01-02")) == ["옛"]
