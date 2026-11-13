"""카카오 로컬 API 로 가게 한 곳의 장소 ID 를 찾는 함수 하나만 있는 파일. (지도 링크 개선 2단계)

결과 저장(3단계) · 화면 연결(4단계)은 여기 없다. 키를 읽는 일도 여기 없다 (호출하는 쪽이 넘긴다).
"""
import re

import requests

import config


def normalize_name(name: str) -> str:
    # 왜: "가게(본점)" · 공백 · 기호 차이로 같은 가게를 다르게 보지 않게 한다. 어디: 이름 비교.
    # 교안: 직접 대응 없음. 괄호 안 글자는 지점 설명인 경우가 많아 뗀다.
    name = re.sub(r"\(.*?\)", "", name or "")
    return re.sub(r"[\s·\-_.,&]+", "", name).lower()


def _fail(reason: str) -> dict:
    return {"ok": False, "reason": reason}


def _found(doc: dict, method: str) -> dict:
    place_id = doc["id"]
    return {
        "ok": True,
        "place_id": place_id,
        "place_url": doc.get("place_url") or f"https://place.map.kakao.com/{place_id}",
        "place_name": doc["place_name"],
        "distance_m": int(float(doc.get("distance") or 0)),
        "method": method,  # name = 이름으로 고름 · sole_near = 이름은 달라도 가까운 후보가 하나뿐
    }


def find_kakao_place(name: str, lat, lon, *, key: str | None, get=requests.get) -> dict:
    """성공: {"ok": True, "place_id", "place_url", "place_name", "distance_m", "method"} / 실패: {"ok": False, "reason"}"""
    # 왜: 키와 HTTP 호출을 인자로 받으면 테스트에서 가짜로 바꿀 수 있고, 실패도 예외가 아니라 결과로 돌려준다. 어디: 함수 전체.
    # 교안: 4일차 PRD "가짜 날씨 데이터를 주입" · 3일차 Part2 "에러도 결과로".
    if not key:
        return _fail("카카오 키가 없습니다")
    try:
        r = get(
            config.KAKAO_LOCAL_URL,
            headers={"Authorization": f"KakaoAK {key}"},  # 키는 헤더로만 보내고 로그나 결과에 넣지 않는다
            params={"query": name, "x": lon, "y": lat, "radius": config.KAKAO_RADIUS_M, "sort": "distance", "size": 15},
            timeout=config.KAKAO_TIMEOUT_SEC,
        )
    except requests.RequestException as e:
        return _fail(f"호출 실패: {type(e).__name__}")
    if r.status_code != 200:
        try:
            message = r.json().get("message", "")
        except ValueError:
            message = ""
        return _fail(f"HTTP {r.status_code} {message}".strip())

    # 왜: 업종이 음식점 · 카페가 아닌 후보(주차장 등)를 먼저 뺀다. 어디: 후보 고르기 1단계.
    # 교안: 직접 대응 없음. 호출은 한 번만 하고 거르는 일은 코드가 한다.
    docs = [d for d in r.json().get("documents", []) if d.get("category_group_code") in config.KAKAO_CATEGORY_CODES]
    if not docs:
        return _fail("후보 없음")

    def dist(d: dict) -> float:
        return float(d.get("distance") or 1e9)

    # 왜: 이름이 같거나 한쪽이 다른 쪽을 품으면 같은 가게로 보고, 여럿이면 가장 가까운 곳을 고른다. 어디: 후보 고르기 2단계.
    # 교안: 직접 대응 없음. 두 글자 미만은 아무 이름에나 들어가므로 포함 비교를 하지 않는다.
    want = normalize_name(name)
    same = []
    for d in docs:
        got = normalize_name(d["place_name"])
        short = min(len(want), len(got))
        if want == got or (short >= 2 and (want in got or got in want)):
            same.append(d)
    if same:
        return _found(min(same, key=dist), "name")

    # 왜: 영문↔한글(MCL↔엠씨엘)처럼 이름이 달라도, 업종이 맞는 후보가 하나뿐이고 아주 가까우면 같은 가게다. 어디: 후보 고르기 3단계.
    # 교안: 직접 대응 없음. 50m 는 20곳 표본에서 잡은 임시값이라 3단계에서 다시 점검한다.
    if len(docs) == 1 and dist(docs[0]) <= config.KAKAO_SOLE_MAX_M:
        return _found(docs[0], "sole_near")
    return _fail(f"판정 불가: 후보 {len(docs)}곳, 이름 불일치")
