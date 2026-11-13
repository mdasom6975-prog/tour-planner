"""tools/geo.py 의 distance_km 을 손으로 계산되는 값과 대조한다."""
import math

import pytest

import config
from tools.geo import distance_km

SEOUL = (37.5665, 126.9780)


def test_같은_점은_0km():
    assert distance_km(SEOUL, SEOUL) == {"ok": True, "km": 0.0}


def test_위도_1도는_약_111km():
    # 반지름 × 1도(라디안) = 6371 × π / 180 = 111.19km
    expected = config.EARTH_RADIUS_KM * math.pi / 180
    assert distance_km((37.0, 127.0), (38.0, 127.0))["km"] == pytest.approx(expected, abs=0.01)
    assert distance_km((37.0, 127.0), (38.0, 127.0))["km"] == pytest.approx(111.19, abs=0.01)


def test_경도_1도는_위도가_높을수록_짧다():
    at_equator = distance_km((0.0, 127.0), (0.0, 128.0))["km"]
    at_37 = distance_km((37.0, 127.0), (37.0, 128.0))["km"]
    assert at_equator == pytest.approx(111.19, abs=0.01)
    assert at_37 == pytest.approx(111.19 * math.cos(math.radians(37)), abs=0.05)


def test_순서를_바꿔도_같다():
    busan = (35.1796, 129.0756)
    assert distance_km(SEOUL, busan) == distance_km(busan, SEOUL)


def test_장소_dict_도_받는다():
    a = {"id": "1", "lat": 37.0, "lon": 127.0}
    b = {"id": "2", "lat": "38.0", "lon": "127.0"}   # 원본 데이터는 좌표가 글자일 수 있다
    assert distance_km(a, b)["km"] == pytest.approx(111.19, abs=0.01)


@pytest.mark.parametrize("bad", [None, (), (37.0,), (None, 127.0), {"lat": 37.0}, ("가", "나"), (91.0, 127.0), (37.0, 181.0), (float("nan"), 127.0)])
def test_잘못된_좌표는_실패를_결과로(bad):
    for r in (distance_km(bad, SEOUL), distance_km(SEOUL, bad)):
        assert r["ok"] is False and r["reason"]


def test_지구_반대편은_반_바퀴():
    assert distance_km((0.0, 0.0), (0.0, 180.0))["km"] == pytest.approx(math.pi * config.EARTH_RADIUS_KM, abs=0.01)
