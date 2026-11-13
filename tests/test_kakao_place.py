"""ingest/match_kakao_place.py 를 가짜 카카오 응답으로 검증한다. 실제 호출은 하지 않는다."""
import requests

import config
from ingest.match_kakao_place import find_kakao_place, normalize_name


class FakeResponse:
    def __init__(self, docs=None, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {"documents": docs or []}

    def json(self):
        return self._body


def fake_get(docs=None, status=200, body=None, calls=None):
    # 왜: 요청을 기록해 두면 반경 · 좌표를 제대로 보냈는지도 검사할 수 있다. 어디: 모든 테스트.
    def get(url, headers=None, params=None, timeout=None):
        if calls is not None:
            calls.append({"url": url, "headers": headers, "params": params})
        return FakeResponse(docs, status, body)

    return get


def doc(place_id, name, distance, code="FD6"):
    return {"id": place_id, "place_name": name, "distance": str(distance), "category_group_code": code,
            "place_url": f"http://place.map.kakao.com/{place_id}"}


def test_이름이_같으면_고르고_요청에_반경과_좌표를_담는다():
    calls = []
    r = find_kakao_place("툇마루", "35.23", "129.00", key="K", get=fake_get([doc("1", "툇마루", 0)], calls=calls))
    assert r["ok"] and r["place_id"] == "1" and r["method"] == "name"
    assert r["place_url"] == "http://place.map.kakao.com/1"
    p = calls[0]["params"]
    assert (p["x"], p["y"], p["radius"]) == ("129.00", "35.23", config.KAKAO_RADIUS_M)


def test_같은_이름_두_곳이면_가까운_곳을_고른다():
    docs = [doc("far", "한성식당", 80), doc("near", "한성식당", 20)]   # 순서가 거리순이 아니어도 가까운 곳
    r = find_kakao_place("한성식당", "35.28", "126.42", key="K", get=fake_get(docs))
    assert r["place_id"] == "near" and r["distance_m"] == 20


def test_주차장만_있으면_후보_없음():
    r = find_kakao_place("24프레임", "37.78", "128.90", key="K", get=fake_get([doc("9", "24프레임 주차장", 12, code="PK6")]))
    assert r == {"ok": False, "reason": "후보 없음"}


def test_이름이_달라도_가까운_후보가_하나뿐이면_채택():
    r = find_kakao_place("MCL", "35.96", "126.73", key="K", get=fake_get([doc("7", "엠씨엘", 0)]))
    assert r["ok"] and r["method"] == "sole_near"


def test_이름이_다르고_멀리_있는_단독_후보는_거부():
    far = config.KAKAO_SOLE_MAX_M + 10
    r = find_kakao_place("MCL", "35.96", "126.73", key="K", get=fake_get([doc("7", "엠씨엘", far)]))
    assert r["ok"] is False and "판정 불가" in r["reason"]


def test_실패는_예외가_아니라_결과로_돌려준다():
    assert find_kakao_place("가게", "1", "2", key=None)["reason"] == "카카오 키가 없습니다"
    forbidden = {"errorType": "NotAuthorizedError", "message": "disabled OPEN_MAP_AND_LOCAL service."}
    r = find_kakao_place("가게", "1", "2", key="K", get=fake_get(status=403, body=forbidden))
    assert r["ok"] is False and r["reason"].startswith("HTTP 403")

    def boom(*a, **k):
        raise requests.ConnectionError("끊김")

    assert find_kakao_place("가게", "1", "2", key="K", get=boom)["reason"] == "호출 실패: ConnectionError"


def test_이름_정규화는_공백_괄호_기호를_뗀다():
    assert normalize_name("삼교리 동치미막국수 (본점)") == "삼교리동치미막국수"
    assert normalize_name("A·B-C") == "abc"
