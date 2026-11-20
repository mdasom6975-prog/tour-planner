"""무장애 · 반려동물 조건 정보를 읽는 순수 함수 모음. LLM · 네트워크를 쓰지 않는다. (코스 품질 T3)

요청에 그런 낱말이 있는지(request_wants) · 저장된 값이 긍정인지(access_positive · pet_positive) · 후보 줄에 옮길 문구(access_brief · pet_label · menu_label) ·
검색 순위 가중(boost_results)을 한 곳에 둔다. 후보 줄 · 검색 · 평가 지표가 같은 판정을 쓰게 하려는 것이다. 거르기(제외)는 하지 않는다(PRD 4번).
"""
import re

import config
from tools.hours import describe, parse_hours


def _flat(value) -> list:
    if value is None:
        return []
    return [str(x) for x in value] if isinstance(value, (list, tuple)) else [str(value)]


def request_texts_of(message, req: dict | None) -> list:
    """요청 반영을 볼 때 읽는 문장 한 턴분: 사용자가 보낸 말과 파싱된 동행 · 취향 · 제외. 지표(eval/quality.py)와 검색 가중이 같은 문장을 읽는다."""
    out = [str(message or "")]
    for key in ("companions", "preferences", "exclusions"):
        out += _flat((req or {}).get(key))
    return out


def request_wants(texts) -> dict:
    """요청 문장들에 무장애 · 반려동물 낱말이 있는지. {"access": bool, "pet": bool}"""
    # 왜: "장애물"에 "장애"가, "카펫"에 "펫"이 걸려 조건을 안 말했는데 말한 것으로 셌다(T1 크리틱). 알려 둔 오탐 낱말을 먼저 지우고 찾는다. 어디: 요청 반영 지표와 검색 가중이 같은 함수를 쓴다.
    # 교안: 직접 대응 없음. 낱말 · 오탐 목록은 config.ACCESS_REQUEST_WORDS · PET_REQUEST_WORDS · REQUEST_FALSE_HITS.
    text = " ".join(str(t) for t in texts if t)
    for bad in config.REQUEST_FALSE_HITS:
        text = text.replace(bad, " ")
    return {"access": any(w in text for w in config.ACCESS_REQUEST_WORDS), "pet": any(w in text for w in config.PET_REQUEST_WORDS)}


def _items(access: dict) -> dict:
    """무장애 정보를 {항목 이름: 원문} 으로 편다. 값이 빈 항목은 뺀다. 이름이 겹치면 먼저 나온 것을 쓴다."""
    out = {}
    for part in (access or {}).values():
        if isinstance(part, dict):
            for key, value in part.items():
                text = " ".join(str(value or "").split())
                if text:
                    out.setdefault(key, text)
    return out


def wheelchair_ok(access: dict) -> bool:
    """원문에 '휠체어 접근 가능' 문장이 있고 '접근 어려움 · 불가'가 없을 때만 True. 정보가 없거나 다른 항목뿐이거나 좋고 나쁜 말이 섞이면 False(가능이라 단정하지 않는다)."""
    flat = " ".join(str(v) for part in (access or {}).values() for v in (part.values() if isinstance(part, dict) else [part]))
    return bool(re.search(config.ACCESS_POSITIVE_PATTERN, flat)) and not re.search(config.ACCESS_NEGATIVE_PATTERN, flat)


def access_positive(place: dict) -> bool:
    return wheelchair_ok((place or {}).get("access"))


def pet_status(pet: dict | None, flag: str | None = None) -> str | None:
    """반려동물 동반 상태: yes(전구역·가능) | partial(일부구역) | no(불가·없음) | info(값은 있으나 뜻을 모름) | None(정보 없음). 반려동물 정보(pet)가 있으면 그것이, 없으면 flag(extra.pet 원문)가 기준."""
    scope = str((pet or {}).get("범위") or "")
    if scope:
        return "no" if "불가" in scope else "yes" if "전구역" in scope else "partial" if "일부" in scope else "info"
    flag = str(flag or "").strip()
    if not flag:
        return None
    return "yes" if flag == "가능" else "no" if flag in ("불가", "없음") else "info"


def pet_positive(place: dict) -> bool:
    """반려동물 '가능'으로 읽히는 장소(전구역 · 일부구역 · 가능). 정보 없음 · 불가는 False."""
    p = place or {}
    return pet_status(p.get("pet"), p.get("pet_flag") or (p.get("extra") or {}).get("pet")) in ("yes", "partial")


def pet_label(place: dict) -> str:
    """후보 줄에 옮길 반려동물 문구. 정보가 없으면 빈 문자열(없는 것을 '가능'이나 '불가'로 쓰지 않는다)."""
    # 왜: 후보 줄이 범위만 옮겨 "불가"와 "정보 없음"이 같은 모습(아무 말 없음)이었다. 저장된 원문(범위 · 관광공사 chkpet)을 그대로 옮기고, 불가 표기는 불가라고 쓴다. 어디: 코스 작성 후보 줄.
    # 교안: PRD 8번 "LLM 은 받은 장소 정보를 옮겨 적기만". 한계: chkpet 의 '없음'은 불가 쪽으로 읽는다(저장 3,691곳 중 10곳).
    pet, flag = place.get("pet") or {}, str(place.get("pet_flag") or "").strip()
    scope = str(pet.get("범위") or "")
    if scope:
        return scope
    status = pet_status(None, flag)
    if status == "yes":
        return "동반 가능"
    if status == "no":
        return "동반 불가" if flag == "불가" else f"동반 불가(원문 '{flag}')"
    return f"{flag}(원문)" if status == "info" else ""


def access_brief(access: dict) -> str:
    """후보 줄에 옮길 무장애 요약. '휠체어 접근 가능' 판정(원문에 문장이 있을 때만) + 동행에 쓸 항목(접근로 · 엘리베이터 · 유아차 · 수유실 …) 원문 앞부분. 정보가 없으면 빈 문자열."""
    # 왜: 후보 줄에 무장애가 없어 "휠체어", 부모님, 아이 동반 요청이 장소 고르기에 반영되지 않았다. 원문 항목을 짧게 잘라 옮겨 LLM 이 보고 고르게 한다(새 값은 만들지 않는다). 어디: 코스 작성 후보 줄.
    # 교안: PRD 8번 "LLM 은 받은 장소 정보를 옮겨 적기만". 길이는 config.CAND_ACCESS_*. 후보가 100곳 안팎이라 줄이 길어지지 않게 자른다.
    items = _items(access)
    if not items:
        return ""
    keys = [k for k in config.CAND_ACCESS_KEYS if k in items][:config.CAND_ACCESS_MAX_ITEMS] or list(items)[:2]
    n = config.CAND_ACCESS_ITEM_CHARS
    parts = ["휠체어 접근 가능"] if wheelchair_ok(access) else []
    parts += [f"{k}: {items[k][:n]}{'…' if len(items[k]) > n else ''}" for k in keys]
    text = " / ".join(parts)
    return text if len(text) <= config.CAND_ACCESS_CHARS else text[:config.CAND_ACCESS_CHARS] + "…"


def menu_label(place: dict) -> str:
    """후보 줄에 옮길 대표메뉴(원문 menu_main) 앞부분. 없으면 빈 문자열."""
    text = " ".join(str(place.get("menu") or "").split())
    n = config.CAND_MENU_CHARS
    return text if len(text) <= n else text[:n] + "…"


def hours_label(place: dict) -> str:
    """후보 줄에 옮길 이용시간 문구. 코드가 읽은 값이면 '이용시간: 11:00~20:00', 읽지 못한 원문이면 '이용시간(원문): 앞부분'. 정보가 없으면 빈 문자열."""
    # 왜: 칸의 대표 시각에 문을 연 곳을 LLM 이 처음부터 고르게 하려면 후보 줄에 이용시간이 있어야 한다. 읽은 값(tools/hours.py)은 검증기와 같은 값이고, 못 읽은 문장은 원문 앞부분만 "(원문)" 표시로 옮긴다. 어디: 코스 작성 · 수정 후보 줄.
    # 교안: PRD 8번 "LLM 은 받은 장소 정보를 옮겨 적기만". 한계: 길이는 config.CAND_HOURS_CHARS 로 자른다.
    raw = " ".join(str(place.get("hours") or "").split())
    if not raw:
        return ""
    n = config.CAND_HOURS_CHARS
    parsed = parse_hours(raw)
    if parsed["status"] in ("open_close", "all_day"):
        text = describe(parsed)
        return "이용시간: " + (text if len(text) <= n else text[:n] + "…")
    return "이용시간(원문): " + (raw if len(raw) <= n else raw[:n] + "…")


def extra_fields(p: dict) -> dict:
    """저장된 장소에서 후보에 실을 값만(있을 때만): 대표메뉴(menu) · 관광공사 반려동물 표기(pet_flag) · 이용시간 원문(hours)."""
    extra = p.get("extra") or {}
    out = {}
    if str(p.get("hours_text") or "").strip():
        out["hours"] = p["hours_text"]
    if extra.get("menu_main"):
        out["menu"] = extra["menu_main"]
    if extra.get("pet"):
        out["pet_flag"] = extra["pet"]
    return out


def boost_results(results: list, places: dict, wants: dict, ranks: int | None = None) -> list:
    """요청한 조건이 긍정으로 저장된 장소를 ranks 칸 앞으로 올린다. 순서만 바꾸고 하나도 빼지 않는다. wants 가 모두 False 이면 입력 그대로."""
    # 왜: 점수는 재정렬 모델 점수(0~1)일 때도 RRF 점수(0.01대)일 때도 있어 점수를 더하면 단위가 어긋난다. 순위를 몇 칸 올리는 방식이 어느 쪽에서도 같다. 어디: search_places 의 k 자르기 직전.
    # 교안: 직접 대응 없음. 거르기가 아니라 순위만 바꾼다(PRD 4번). 요청에 낱말이 없으면 이 함수를 부르지도 않는다.
    ranks = config.REQUEST_BOOST_RANKS if ranks is None else ranks
    if not (wants.get("access") or wants.get("pet")):
        return list(results)

    def good(r):
        p = places.get(r["id"]) or {}
        return (wants.get("access") and access_positive(p)) or (wants.get("pet") and pet_positive(p))
    keyed = [(n - ranks if good(r) else n, n, r) for n, r in enumerate(results)]
    return [r for _, _, r in sorted(keyed, key=lambda t: (t[0], t[1]))]

