"""ingest/clean.py 의 detail_fields: 유형마다 다른 항목 이름을 같은 칸으로 읽는지 확인한다. (4-5a)"""
import pytest

from ingest.clean import DETAIL_REST_KEYS, DETAIL_TEXT_KEYS, detail_fields

COMMON = {"overview": "소개글<br>둘째 줄", "homepage": '<a href="http://x.kr">홈</a>'}


def test_모든_유형이_같은_칸_이름을_돌려준다():
    for type_id in ("12", "14", "15", "39"):
        assert set(detail_fields(type_id, COMMON, {})) == set(DETAIL_TEXT_KEYS) | set(DETAIL_REST_KEYS)


@pytest.mark.parametrize("type_id, intro, hours", [
    ("12", {"restdate": "매주 월요일", "usetime": "09:00~18:00"}, "09:00~18:00"),
    ("14", {"restdateculture": "매주 월요일", "usetimeculture": "10:00~17:00"}, "10:00~17:00"),
    ("39", {"restdatefood": "매주 월요일", "opentimefood": "11:00~21:00"}, "11:00~21:00"),
])
def test_유형마다_다른_이름의_휴무일_이용시간을_읽는다(type_id, intro, hours):
    d = detail_fields(type_id, COMMON, intro)
    assert (d["rest_text"], d["hours_text"]) == ("매주 월요일", hours)
    assert (d["rest_status"], d["rest_weekdays"], d["rest_note"]) == ("weekly", ["월"], False)


def test_다른_유형의_항목_이름은_읽지_않는다():
    d = detail_fields("39", COMMON, {"restdate": "매주 월요일"})   # 음식점인데 관광지 이름으로 온 값
    assert d["rest_text"] == "" and d["rest_status"] == "unknown"


def test_축제는_휴무일_대신_행사_기간():
    d = detail_fields("15", COMMON, {"eventstartdate": "20261114", "eventenddate": "20261116", "eventplace": "광장", "playtime": "10:00~20:00"})
    assert d["rest_text"] == "" and d["rest_status"] == "not_applicable" and d["rest_weekdays"] == []
    assert d["hours_text"] == "10:00~20:00"
    assert d["extra"] == {"event_start": "20261114", "event_end": "20261116", "event_place": "광장"}


def test_소개글과_홈페이지는_정리해서():
    d = detail_fields("12", COMMON, {})
    assert d["overview"] == "소개글\n둘째 줄" and d["homepage"] == "http://x.kr"


def test_빈_응답도_받는다():
    for common, intro in ((None, None), ({}, {})):
        d = detail_fields("12", common, intro)
        assert d["overview"] == "" and d["rest_text"] == "" and d["extra"] == {} and d["rest_status"] == "unknown"


def test_빈_값인_덧붙는_항목은_넣지_않는다():
    d = detail_fields("39", COMMON, {"firstmenu": "낙곱새", "treatmenu": "", "packing": None})
    assert d["extra"] == {"menu_main": "낙곱새"}
