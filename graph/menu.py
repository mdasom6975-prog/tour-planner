"""식당 대표메뉴(places 의 extra.menu_main) 문장에서 비교용 키워드를 뽑는다. LLM 은 쓰지 않는다. (코스 품질 T1, T2 가 재사용)

판정 규칙(코스 검증에 넣기)은 여기 없다. 뽑은 키워드가 겹치는지는 menu_overlaps 가 센다.
"""
import itertools
import re

import config

_SPLIT = re.compile(r"[,/·\n\r\t()\[\]+&、;:~]|\s+")


def menu_keywords(text) -> set:
    """'마라도물회, 물밀면 / 소금빵 아이스크림' → {'마라도물회', '물밀면', '소금빵', '아이스크림'}. 비어 있으면 빈 집합."""
    # 왜: 대표메뉴는 자유 문장이라 구분자가 제각각이다. 단순 분리 + 소문자 + 짧은 말 · 흔한 말 제거만 한다(형태소 분석은 하지 않는다). 어디: 메뉴 중복 지표와 T2 검증.
    # 교안: 직접 대응 없음. 한계: "물회"와 "마라도물회"처럼 한쪽이 다른 쪽을 품은 말은 서로 다른 키워드로 본다.
    if not isinstance(text, str):
        return set()
    words = (w.strip(" .!'\"").lower() for w in _SPLIT.split(text))
    return {w for w in words if len(w) >= config.MENU_KEYWORD_MIN_LEN and w not in config.MENU_STOPWORDS}


def place_menu_keywords(place: dict) -> set:
    return menu_keywords(((place or {}).get("extra") or {}).get("menu_main"))


def menu_overlaps(places: list) -> dict:
    """장소 목록에서 대표메뉴 키워드가 겹치는 쌍과 장소. {'pairs': [(id, id, 겹친 키워드 목록)], 'places': 겹침에 든 장소 id 목록}."""
    keys = [(p.get("id"), place_menu_keywords(p)) for p in places]
    pairs = [(a, b, sorted(ka & kb)) for (a, ka), (b, kb) in itertools.combinations(keys, 2) if ka & kb]
    return {"pairs": pairs, "places": sorted({i for a, b, _ in pairs for i in (a, b)}, key=str)}
