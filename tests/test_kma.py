"""tools/kma.py 와 get_weather 의 층별 전환을 가짜 응답으로 확인한다. 네트워크를 쓰지 않는다. 응답 모양은 2026-11-13 에 받은 실제 응답을 따랐다."""
from datetime import datetime

import pytest

from tools import kma
from tools.weather import get_weather

TODAY = "2026-11-13"
SEOUL = (37.5665, 126.9780)


def _item(cat, day, time, value):
    return {"category": cat, "fcstDate": day, "fcstTime": time, "fcstValue": value}


def short_items(day="20261114", pop="60", sno="적설없음", pty="0", hours=24, with_tm=True):
    items = [_item("TMP", day, f"{h:02d}00", "10") for h in range(hours)]
    items += [_item("POP", day, "0900", pop), _item("SNO", day, "0900", sno), _item("PTY", day, "0900", pty)]
    if with_tm:
        items += [_item("TMN", day, "0600", "10.0"), _item("TMX", day, "1500", "14.0")]
    return items


LAND = {"rnSt4Am": 30, "rnSt4Pm": 60, "wf4Am": "흐림", "wf4Pm": "흐리고 비", "rnSt8": 10, "wf8": "맑음", "rnSt5Am": 10, "rnSt5Pm": 20, "wf5Am": "맑음", "wf5Pm": "비/눈"}
TA = {"taMin4": 9, "taMax4": 15, "taMin5": 2, "taMax5": 8, "taMin8": 3, "taMax8": 10}
MID = {"tmFc": "202611130600", "land": LAND, "ta": TA}


def test_격자_변환은_서울과_강릉이_맞는다():
    assert kma.to_grid(*SEOUL) == (60, 127) and kma.to_grid(37.75, 128.88) == (92, 131)


def test_발표_시각은_10분_뒤부터_받고_새벽에는_전날_23시():
    assert kma.short_base(datetime(2026, 11, 13, 14, 5, tzinfo=kma.KST)) == ("20261113", "1100")
    assert kma.short_base(datetime(2026, 11, 13, 14, 10, tzinfo=kma.KST)) == ("20261113", "1400")
    assert kma.short_base(datetime(2026, 11, 13, 1, 30, tzinfo=kma.KST)) == ("20261112", "2300")


def test_단기_문자열_값을_숫자로_읽는다():
    r = kma.parse_short(short_items(pop="60", sno="0.5cm 미만"))["2026-11-14"]
    assert (r["temp_max"], r["temp_min"], r["rain_prob"], r["snow_cm"], r["snow"]) == (14.0, 10.0, 60.0, 0.5, True)


def test_단기_강수형태가_눈이면_적설이_없어도_눈():
    assert kma.parse_short(short_items(pty="3"))["2026-11-14"]["snow"] is True
    assert kma.parse_short(short_items())["2026-11-14"]["snow"] is False


def test_최저최고가_없고_시간별_기온도_모자라면_그_날은_비운다():
    assert kma.parse_short(short_items(hours=9, with_tm=False)) == {}
    assert kma.parse_short(short_items(hours=24, with_tm=False))["2026-11-14"]["temp_max"] == 10.0


def test_중기는_발표일_더하기_N일을_날짜로_쓴다():
    r = kma.parse_mid("202611130600", LAND, TA)
    assert set(r) == {"2026-11-17", "2026-11-18", "2026-11-21"}   # 6 · 7일차는 응답에 없어 비운다
    assert r["2026-11-17"] == {"temp_max": 15.0, "temp_min": 9.0, "rain_prob": 60.0, "snow_cm": None, "snow": False}
    assert r["2026-11-18"]["snow"] is True                       # '비/눈' 문구


def test_중기_구역은_가까운_도시로_잡는다():
    assert kma.mid_region(37.75, 128.9) == ("11D20000", "11D20501")   # 강릉
    assert kma.mid_region(33.4, 126.5) == ("11G00000", "11G00201")    # 제주


def test_날짜마다_단기_중기_순서로_받고_출처를_남긴다():
    r = get_weather(*SEOUL, ["2026-11-14", "2026-11-17"], today=TODAY, short=lambda la, lo: short_items(), mid=lambda la, lo: MID)
    assert r["ok"] and r["unavailable"] == []
    assert [d["source"] for d in r["days"]] == ["기상청 단기예보", "기상청 중기예보"]
    assert r["source"] == "기상청 단기예보 + 기상청 중기예보"


def test_기상청이_실패하면_Open_Meteo로_넘어간다():
    def boom(la, lo):
        raise TimeoutError("느림")
    raw = {"daily": {"time": ["2026-11-14"], "temperature_2m_max": [9], "temperature_2m_min": [1], "precipitation_probability_max": [10], "snowfall_sum": [0.0]}}
    r = get_weather(*SEOUL, ["2026-11-14"], today=TODAY, short=boom, mid=boom, fetch=lambda *a: raw)
    assert r["ok"] and r["days"][0]["available"] and r["source"] == "Open-Meteo" and "source" not in r["days"][0]


def test_모든_층이_실패하면_실패를_결과로():
    def boom(*a):
        raise TimeoutError("느림")
    r = get_weather(*SEOUL, ["2026-11-14"], today=TODAY, short=boom, mid=boom, fetch=boom)
    assert r == {"ok": False, "reason": "날씨를 가져오지 못했습니다: TimeoutError"}


def test_오늘은_단기에_하루치가_없어_Open_Meteo가_받는다():
    items = short_items(day="20261113", hours=9, with_tm=False)
    r = get_weather(*SEOUL, ["2026-11-13"], today=TODAY, short=lambda la, lo: items, mid=lambda la, lo: MID)
    assert r["ok"] and r["unavailable"] == ["2026-11-13"]


def test_코드에_키가_없으면_호출하지_않는다(monkeypatch):
    monkeypatch.delenv("TOURAPI_KEY", raising=False)
    with pytest.raises(RuntimeError):
        kma.fetch_short(37.5, 127.0, get=lambda *a, **k: (_ for _ in ()).throw(AssertionError("호출하면 안 된다")))
