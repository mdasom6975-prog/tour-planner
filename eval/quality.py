"""코스 품질 지표: 동선 거리 · 하루 칸 구성 · 메뉴 겹침 · 요청 반영. 코드로만 재고 모델을 부르지 않는다. (코스 품질 T1)

합격선은 정하지 않는다. 고치기 전 현재 값을 기록하는 용도다(T6 에서 전 · 후를 비교).
입력은 eval/run.py 가 남긴 마지막 턴(turn)과 고정 사본의 장소({id: place}).
"""
import config
from graph.menu import menu_overlaps
from tools.conditions import access_positive, pet_positive, request_texts_of, request_wants
from tools.geo import distance_km
from tools.hours import describe, open_at, parse_hours

IS_FOOD = lambda p: p.get("type") in config.FOOD_TYPES and not p.get("is_cafe")   # 카페는 아메리카노처럼 겹치는 메뉴가 당연해 뺀다


def day_km(slots: list, places: dict) -> float | None:
    """하루 칸을 순서대로 이은 연속 직선거리의 합(km). 사본에 없는 장소나 좌표가 없으면 None."""
    # 왜: 동선이 효율적인지는 "하루 이동 거리 합"으로 잰다. 검증기(graph/validate.py _legs)와 같은 distance_km 를 써서 재배열 전 · 후 값과 비교할 수 있게 한다. 어디: 동선 총거리.
    # 교안: 직접 대응 없음. 직선거리라 실제 도로 거리와 다르다.
    total, prev = 0.0, None
    for s in slots:
        p = places.get(str(s["id"]))
        if p is None:
            return None
        if prev is not None:
            got = distance_km(prev, p)
            if not got["ok"]:
                return None
            total += got["km"]
        prev = p
    return round(total, 2)


def route_metrics(course: list, places: dict, leg_km: list | None = None) -> dict:
    """날별 직선거리 합(after)과, 실행 기록에 재배열 전 값(leg_km)이 있으면 before 도 함께. 합계는 모든 날이 계산될 때만 낸다."""
    before = {r["date"]: r.get("before") for r in leg_km or []}
    days = [{"date": d["date"], "after": day_km(d["slots"], places), "before": before.get(d["date"])} for d in course]
    after_total = round(sum(d["after"] for d in days), 2) if days and all(d["after"] is not None for d in days) else None
    before_total = round(sum(d["before"] for d in days), 2) if days and all(d["before"] is not None for d in days) else None
    return {"days": days, "after_km": after_total, "before_km": before_total,
            "gain_km": round(before_total - after_total, 2) if None not in (before_total, after_total) else None}


def day_shape(course: list, places: dict) -> dict:
    """하루에 칸이 몇 개이고 이용시간 문장(hours_text)이 있는 칸이 몇 개인지. 시간을 해석하지는 않는다(T4 의 일)."""
    # 왜: 시간 배분을 코드가 판정하려면 먼저 이용시간 정보가 칸의 몇 %에 있는지 알아야 한다. 칸 수는 하루 분량(너무 많거나 적은 날)을 본다. 어디: 하루 시간 배분 기준선.
    # 교안: 직접 대응 없음. 파싱 없이 hours_text 가 비어 있지 않은지만 센다.
    per_day = [len(d["slots"]) for d in course]
    slots = [places.get(str(s["id"])) for d in course for s in d["slots"]]
    known = sum(1 for p in slots if p and str(p.get("hours_text") or "").strip())
    return {"slots_per_day": per_day, "slots": len(slots), "with_hours": known,
            "hours_ratio": round(known / len(slots), 3) if slots else None,
            "min_slots": min(per_day, default=None), "max_slots": max(per_day, default=None)}


def hours_fit(course: list, places: dict) -> dict:
    """코스 칸 중 이용시간으로 시간대 판정이 가능한 칸 · 그중 칸 시각에 문을 닫은 칸 · 판정 불가 칸의 수."""
    # 왜: "하루 시간 배분이 어색하다"를 칸의 대표 시각(config.SLOT_MINUTES)과 장소의 이용시간 충돌로 잰다. 읽을 수 없는 문장은 충돌이 아니라 판정 불가로 따로 센다(합: judged + unknown = slots). 어디: 하루 시간 배분 기준선.
    # 교안: 직접 대응 없음(2026-11-19 T4). 검증기(graph/validate.py hours_violation)와 같은 파서(tools/hours.py)를 쓰되 호출은 독립이다. 합격선은 정하지 않았다.
    n = judged = closed = 0
    examples = []
    for d in course:
        for s in d["slots"]:
            n += 1
            p, minute = places.get(str(s["id"])), config.SLOT_MINUTES.get(s["slot"])
            parsed = parse_hours((p or {}).get("hours_text"))
            state = "check" if p is None or minute is None else open_at(parsed, minute)
            judged += state != "check"
            if state == "closed":
                closed += 1
                if len(examples) < 3:
                    examples.append(f'{d["date"]} {s["slot"]} {p.get("title")} ({describe(parsed)})')
    return {"slots": n, "judged": judged, "closed": closed, "unknown": n - judged, "examples": examples,
            "closed_ratio": round(closed / judged, 3) if judged else None}


def menu_duplicates(course: list, places: dict) -> dict:
    """코스 안 식당 칸들의 대표메뉴 키워드가 겹치는 쌍 수와 장소 수."""
    meals = [p for d in course for s in d["slots"] if (p := places.get(str(s["id"]))) and IS_FOOD(p)]
    over = menu_overlaps(meals)
    return {"restaurants": len(meals), "pairs": len(over["pairs"]), "places": len(over["places"]),
            "examples": [f'{a}-{b}:{"/".join(k)}' for a, b, k in over["pairs"][:3]]}


def request_texts(turns: list) -> list:
    """요청 반영을 볼 때 읽는 문장: 사용자가 보낸 말 전부와 파싱된 동행 · 취향 · 제외. 검색 가중(graph/retrieval.py)과 같은 함수로 읽는다."""
    return [t for turn in turns for t in request_texts_of(turn.get("message"), turn.get("request"))]


def request_reflection(texts: list, course: list, places: dict) -> dict:
    """요청에 무장애 · 반려동물 낱말이 있으면, 코스 장소 중 access / pet 값이 있는 비율(정보 유무). 해당 요청이 아니면 None."""
    # 왜: "휠체어 위주"라고 했는데 코스에 무장애 정보가 있는 장소가 몇 %인지 코드로 센다. 정보가 없는 장소는 "모름"이지 "불가"가 아니다. 어디: 요청 반영 기준선.
    # 교안: 직접 대응 없음. 낱말은 config 의 목록 + 오탐 목록(tools/conditions.py request_wants). 주의: 이 값은 "정보 유무"라 반려동물 '불가 · 없음' 표기도 정보 있음으로 센다. 긍정(가능)만의 비율은 request_positive.
    wants = request_wants(texts)
    cs = [p for d in course for s in d["slots"] if (p := places.get(str(s["id"])))]
    has = {"access": lambda p: bool(p.get("access")),
           "pet": lambda p: bool(p.get("pet") or (p.get("extra") or {}).get("pet"))}
    out = {}
    for key in ("access", "pet"):
        if not wants[key]:
            out[key] = None
            continue
        n = sum(1 for p in cs if has[key](p))
        out[key] = {"places": len(cs), "with_info": n, "ratio": round(n / len(cs), 3) if cs else None}
    return out


def request_positive(texts: list, course: list, places: dict) -> dict:
    """요청에 무장애 · 반려동물 낱말이 있으면, 코스 장소 중 '긍정'으로 저장된 비율. 무장애는 "휠체어 접근 가능" 문장(접근 어려움 · 불가가 섞이면 제외), 반려동물은 전구역 · 일부구역 · 가능. 해당 요청이 아니면 None."""
    # 왜: 정보 유무(request_reflection)만으로는 "불가"로 적힌 장소도 반영된 것으로 센다. 요청대로 가도 되는 장소가 몇 곳인지는 긍정만 따로 센다. 어디: 요청 반영 기준선 · T3 전 후 비교.
    # 교안: 직접 대응 없음. 정보가 없는 장소는 긍정이 아니므로 분모에는 들고 분자에는 안 든다(모름 = 확인 못 함).
    wants = request_wants(texts)
    cs = [p for d in course for s in d["slots"] if (p := places.get(str(s["id"])))]
    good = {"access": access_positive, "pet": pet_positive}
    out = {}
    for key in ("access", "pet"):
        if not wants[key]:
            out[key] = None
            continue
        n = sum(1 for p in cs if good[key](p))
        out[key] = {"places": len(cs), "positive": n, "ratio": round(n / len(cs), 3) if cs else None}
    return out


def course_quality(turns: list, places: dict) -> dict | None:
    """문항의 마지막 턴이 코스일 때 네 가지 지표(요청 반영은 정보 유무 + 긍정)를 한 번에. 코스가 아니면 None."""
    last = turns[-1] if turns else {}
    course = last.get("course") or []
    if last.get("kind") != "course" or not course:
        return None
    return {"route": route_metrics(course, places, last.get("leg_km")), "shape": day_shape(course, places),
            "menu": menu_duplicates(course, places), "hours": hours_fit(course, places), "request": request_reflection(request_texts(turns), course, places),
            "positive": request_positive(request_texts(turns), course, places)}
