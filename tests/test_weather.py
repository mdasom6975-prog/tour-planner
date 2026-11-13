"""tools/weather.py 의 get_weather 를 가짜 응답으로 확인한다. 네트워크를 쓰지 않는다."""
import pytest

import requests

import config
from tools.weather import fetch_open_meteo, get_weather

TODAY = "2026-11-13"
BUSAN = (35.18, 129.08)


class FakeFetch:
    """조회 함수 흉내. 받은 인자를 기억하고, 물어본 기간의 날짜마다 정해 둔 값을 돌려준다."""
    def __init__(self, rows=None, error=None, raw=None):
        self.rows, self.error, self.raw, self.calls = rows or {}, error, raw, []

    def __call__(self, lat, lon, start, end):
        self.calls.append((lat, lon, start, end))
        if self.error:
            raise self.error
        if self.raw is not None:
            return self.raw
        days = [d for d in sorted(self.rows) if start <= d <= end]
        col = lambda n: [self.rows[d][n] for d in days]
        return {"daily": {"time": days, "temperature_2m_max": col(0), "temperature_2m_min": col(1),
                          "precipitation_probability_max": col(2), "snowfall_sum": col(3)}}


ROWS = {"2026-11-14": (15.2, 7.1, 20, 0.0), "2026-11-15": (9.0, -1.5, 80, 2.4), "2026-11-16": (11.0, 3.0, 0, 0.0)}


def test_날짜별_값을_그대로_옮긴다():
    fake = FakeFetch(ROWS)
    r = get_weather(*BUSAN, ["2026-11-14", "2026-11-15"], fetch=fake, today=TODAY)
    assert r["ok"] and r["unavailable"] == [] and r["source"] == "Open-Meteo"
    assert r["days"][0] == {"date": "2026-11-14", "available": True, "temp_max": 15.2, "temp_min": 7.1, "rain_prob": 20, "snow_cm": 0.0, "note": ""}
    assert (r["days"][1]["rain_prob"], r["days"][1]["snow_cm"]) == (80, 2.4)
    assert fake.calls == [(35.18, 129.08, "2026-11-14", "2026-11-15")]   # 한 번만, 필요한 기간만


def test_비_오는_날인지는_판정하지_않는다():
    r = get_weather(*BUSAN, ["2026-11-15"], fetch=FakeFetch(ROWS), today=TODAY)
    assert set(r["days"][0]) == {"date", "available", "temp_max", "temp_min", "rain_prob", "snow_cm", "note"}


def test_예보_범위_밖과_지난_날짜는_없다고_표시한다():
    fake = FakeFetch(ROWS)
    r = get_weather(*BUSAN, ["2026-11-12", "2026-11-14", "2026-11-29"], fetch=fake, today=TODAY)
    assert r["ok"] and r["unavailable"] == ["2026-11-12", "2026-11-29"]
    assert [d["available"] for d in r["days"]] == [False, True, False]
    assert r["days"][0]["note"] == "지난 날짜" and "예보 범위 밖" in r["days"][2]["note"]
    assert r["days"][2]["rain_prob"] is None                       # 지어내지 않는다
    assert fake.calls == [(35.18, 129.08, "2026-11-14", "2026-11-14")]   # 범위 밖 날짜는 묻지 않는다


def test_경계_오늘과_16일째는_범위_안():
    rows = {"2026-11-13": (1, 0, 0, 0.0), "2026-11-28": (2, 0, 0, 0.0)}
    r = get_weather(*BUSAN, ["2026-11-13", "2026-11-28", "2026-11-29"], fetch=FakeFetch(rows), today=TODAY)
    assert [d["available"] for d in r["days"]] == [True, True, False]


def test_전부_범위_밖이면_호출하지_않는다():
    fake = FakeFetch(ROWS)
    r = get_weather(*BUSAN, ["2026-12-24", "2026-12-25"], fetch=fake, today=TODAY)
    assert r["ok"] and r["unavailable"] == ["2026-12-24", "2026-12-25"] and fake.calls == []


def test_응답에_없거나_빈_값인_날은_없다고_표시한다():
    rows = {"2026-11-14": (15.2, 7.1, None, 0.0)}   # 강수확률이 빈 날, 15일은 응답에 없음
    r = get_weather(*BUSAN, ["2026-11-14", "2026-11-15"], fetch=FakeFetch(rows), today=TODAY)
    assert r["ok"] and r["unavailable"] == ["2026-11-14", "2026-11-15"]
    assert all(d["note"] == "응답에 값이 없음" and d["temp_max"] is None for d in r["days"])


def test_항목이_날짜_수보다_짧으면_없다고_표시한다():
    raw = {"daily": {"time": ["2026-11-14", "2026-11-15"], "temperature_2m_max": [10], "temperature_2m_min": [1, 2], "precipitation_probability_max": [30, 40]}}
    r = get_weather(*BUSAN, ["2026-11-14", "2026-11-15"], fetch=FakeFetch(raw=raw), today=TODAY)
    assert r["ok"] and [d["available"] for d in r["days"]] == [True, False]


def test_눈_항목이_없는_응답도_받는다():
    raw = {"daily": {"time": ["2026-11-14"], "temperature_2m_max": [10], "temperature_2m_min": [1], "precipitation_probability_max": [30]}}
    r = get_weather(*BUSAN, ["2026-11-14"], fetch=FakeFetch(raw=raw), today=TODAY)
    assert r["days"][0]["available"] and r["days"][0]["snow_cm"] is None


@pytest.mark.parametrize("fake", [FakeFetch(error=TimeoutError("느림")), FakeFetch(error=RuntimeError("500")),
                                  FakeFetch(raw={"error": True, "reason": "bad"}), FakeFetch(raw={"daily": "깨짐"})])
def test_서버_오류와_깨진_응답은_실패를_결과로(fake):
    r = get_weather(*BUSAN, ["2026-11-14"], fetch=fake, today=TODAY)
    assert r["ok"] is False and r["reason"].startswith("날씨를 가져오지 못했습니다")


@pytest.mark.parametrize("lat, lon, dates", [(None, 129.0, ["2026-11-14"]), (91, 129.0, ["2026-11-14"]), (35.1, 129.0, []),
                                             (35.1, 129.0, ["11/14"]), (35.1, 129.0, None)])
def test_잘못된_입력은_호출_전에_거른다(lat, lon, dates):
    fake = FakeFetch(ROWS)
    r = get_weather(lat, lon, dates, fetch=fake, today=TODAY)
    assert r["ok"] is False and r["reason"] and fake.calls == []


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code, self.body = status, body or {"daily": {"time": []}}

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeGet:
    """requests.get 흉내. 정해 둔 순서대로 예외를 던지거나 응답을 돌려준다."""
    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), 0

    def __call__(self, url, params, timeout):
        self.calls += 1
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


@pytest.mark.parametrize("first", [requests.Timeout("느림"), requests.ConnectionError("끊김"), FakeResponse(503)])
def test_잠깐_끊기면_한_번_더_불러_받는다(first):
    get = FakeGet(first, FakeResponse(200, {"daily": {"time": ["2026-11-14"]}}))
    assert fetch_open_meteo(35.1, 129.0, "2026-11-14", "2026-11-14", get=get) == {"daily": {"time": ["2026-11-14"]}}
    assert get.calls == 2


def test_계속_죽어_있으면_정해진_횟수만_부르고_실패한다():
    get = FakeGet(*[requests.Timeout("느림")] * 5)
    r = get_weather(*BUSAN, ["2026-11-14"], today=TODAY, fetch=lambda *a: fetch_open_meteo(*a, get=get))
    assert r == {"ok": False, "reason": "날씨를 가져오지 못했습니다: Timeout"}
    assert get.calls == config.WEATHER_RETRIES + 1


def test_잘못된_요청은_다시_부르지_않는다():
    get = FakeGet(FakeResponse(400), FakeResponse(200))
    with pytest.raises(requests.HTTPError):
        fetch_open_meteo(35.1, 129.0, "2026-11-14", "2026-11-14", get=get)
    assert get.calls == 1
