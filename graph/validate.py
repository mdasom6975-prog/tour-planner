"""validate_course 노드의 알맹이. 코드가 코스의 규칙 위반을 찾는다. LLM 은 쓰지 않는다. (14번 6단계)

검사: 칸 구성 · 후보에 없는 장소 · 칸과 유형 · 중복 · 연속 구간 거리(지역별) · 휴무 · 철수(withdrawn).
최종 코스에 들어간 장소만 관광공사에서 다시 받아 그 값으로 휴무를 판정하고, 한 장소는 한 번만 받는다(재작성해도 다시 받지 않는다).
축제는 코스 칸에 넣지 않으므로(5-5) 기간 검사는 해당 없다.
"""
import time
from datetime import date

import config
from graph.context import _label, trip_dates
from graph.state import retries_of
from tools.geo import distance_km
from tools.rest import rest_on

REST_KEYS = ("rest_status", "rest_weekdays", "rest_nth", "rest_note")


def _v(rule: str, reason: str, id=None, date=None, slot=None) -> dict:
    return {"rule": rule, "id": id, "date": date, "slot": slot, "reason": reason}


def _recheck(ids: list, stored: dict, detail) -> dict:
    """{id: {"source", "as_of", "withdrawn", "place": 휴무 칸, "note"}}. detail(id) 는 get_place_detail 과 같은 모양의 dict."""
    def one(cid):
        got = detail(cid) if detail else None
        if got is None or not got.get("ok"):   # 다시 받지 못하면 저장분으로 대신한다(어디서 온 값인지 표시)
            place = stored.get(cid, {})
            return cid, {"source": "stored", "as_of": place.get("fetched", ""), "withdrawn": False, "note": (got or {}).get("reason", ""),
                         "place": {k: place.get(k) for k in REST_KEYS}}
        return cid, {"source": got["source"], "as_of": got["as_of"], "withdrawn": bool(got["withdrawn"]), "note": got.get("note", ""),
                     "place": {k: got["place"].get(k) for k in REST_KEYS}}
    # 왜: 호출 한도 기록 파일(data/raw/_usage.json)을 읽고 쓰는 call()은 동시에 부르면 파일이 깨진다(2026-11-13 실행에서 확인). 장소당 약 315ms라 8곳이 순서대로 약 2.5초다. 어디: 다시 받기.
    # 교안: 직접 대응 없음. 병렬로 하려면 호출 쪽에 잠금을 먼저 넣어야 한다.
    return dict(one(cid) for cid in ids)


def find_violations(course: dict, cands: dict, dates: list, rechecked: dict, region: str | None) -> list:
    """순수 함수: 코스 · 후보 · 다시 받은 값으로 위반 목록을 만든다."""
    out, seen, museums = [], set(), 0
    limit = config.MAX_LEG_KM_BY_REGION.get(region, config.MAX_LEG_KM)
    days = course.get("days", [])
    if dates and [d["date"] for d in days] != dates:
        out.append(_v("dates", f"여행일은 {', '.join(dates)} 입니다. 코스의 날짜가 다릅니다."))
    for d in days:
        slots = d["slots"]
        if [s["slot"] for s in slots] != config.COURSE_SLOTS:
            out.append(_v("slots", f"{_label(d['date'])}은 {'·'.join(config.COURSE_SLOTS)} 네 칸을 순서대로 채워야 합니다.", date=d["date"]))
        prev = None
        for s in slots:
            cid, c = s["content_id"], cands.get(s["content_id"])
            if c is None:
                out.append(_v("unknown_place", f"{cid} 은(는) 후보 목록에 없는 장소입니다. 후보에 있는 id 만 쓰세요.", cid, d["date"], s["slot"]))
                prev = None
                continue
            want = config.FOOD_TYPES if s["slot"] in ("점심", "저녁") else config.SIGHT_TYPES
            if c.get("type") not in want:
                out.append(_v("slot_type", f"{s['slot']} 칸에는 {'/'.join(want)} 유형만 넣을 수 있습니다. {c.get('title')}({c.get('type')}) 은(는) 맞지 않습니다.", cid, d["date"], s["slot"]))
            if s["slot"] in ("점심", "저녁") and c.get("is_cafe"):   # 카페는 식사 자리가 아니라 "근처 카페 추천"으로 따로 둔다
                out.append(_v("cafe_meal", f"{s['slot']} 칸에는 식당을 넣어야 합니다. {c.get('title')} 은(는) 카페입니다.", cid, d["date"], s["slot"]))
            if c.get("category") == config.MUSEUM_CLASS:   # 박물관류는 날씨와 상관없이 코스 전체에서 MUSEUM_MAX 곳까지
                museums += 1
                if museums > config.MUSEUM_MAX:
                    out.append(_v("museum_limit", f"박물관 · 미술관 · 전시관은 코스에 {config.MUSEUM_MAX}곳만 넣을 수 있습니다. {c.get('title')} 은(는) 다른 종류로 바꾸세요.", cid, d["date"], s["slot"]))
            if cid in seen:
                out.append(_v("duplicate", f"{c.get('title')} 이(가) 코스에 두 번 들어 있습니다.", cid, d["date"], s["slot"]))
            seen.add(cid)
            if prev is not None:
                got = distance_km(prev, c)
                if got["ok"] and got["km"] > limit:
                    out.append(_v("distance", f"{prev.get('title')} → {c.get('title')} 직선 {got['km']:.1f}km 로 {limit}km 를 넘습니다. 더 가까운 장소로 바꾸세요.", cid, d["date"], s["slot"]))
            prev = c
            r = rechecked.get(cid)
            if r is not None:
                if r["withdrawn"]:
                    out.append(_v("withdrawn", f"{c.get('title')} 은(는) 관광공사 목록에서 내려간 장소입니다.", cid, d["date"], s["slot"]))
                elif rest_on(r["place"], date.fromisoformat(d["date"])) == "closed":
                    out.append(_v("closed", f"{c.get('title')} 은(는) {_label(d['date'])} 휴무입니다. 다른 장소로 바꾸세요.", cid, d["date"], s["slot"]))
    return out


def validate_update(stored: dict | None, detail, trace):
    stored = stored or {}

    def update(state) -> dict:
        t0 = time.perf_counter()
        course, cands = state.get("course") or {}, {c["id"]: c for c in state.get("candidates", [])}
        req = state.get("request", {})
        dates = trip_dates(req["start_date"], req["days"]) if req.get("start_date") and req.get("days") else []
        # 왜: 휴무 판정은 최종 코스의 장소만 관광공사에서 다시 받은 값으로 한다. 이미 받은 장소는 다시 받지 않는다(재작성 반복에서 한도를 아낀다). 어디: 검사 직전.
        # 교안: PRD F3 "검증과 표시에는 실시간으로 다시 받은 값을 쓴다". 다시 받기에 실패하면 저장분으로 대신하고 기준일을 남긴다.
        rechecked = dict(state.get("rechecked") or {})
        need = [s["content_id"] for d in course.get("days", []) for s in d["slots"] if s["content_id"] in cands and s["content_id"] not in rechecked]
        need = list(dict.fromkeys(need))
        if need:
            rechecked.update(_recheck(need, stored, detail))
        violations = find_violations(course, cands, dates, rechecked, req.get("region"))

        # 왜: 휴무 표(5-4)는 저장분 기준이었다. 다시 받은 값으로 코스 장소의 칸을 덮어 써서 다시 쓸 때와 화면 표시가 같은 값을 보게 한다. 어디: rest_table.
        table = {k: dict(v) for k, v in (state.get("rest_table") or {}).items()}
        for cid in need:
            row = {day: r for day in dates if (r := rest_on(rechecked[cid]["place"], date.fromisoformat(day))) != "open"}
            table[cid] = row
        out = {"rechecked": rechecked, "rest_table": table, "violations": violations}

        # 왜: 두 번 고쳐도 남은 위반은 그 장소를 빼고 "확인 필요"로 알린다(없는 장소 · 규칙 위반 장소를 코스에 남기지 않는다). 어디: 재작성 횟수를 다 쓴 뒤.
        # 교안: PRD 10번 "위반 & 재작성 = 2 → 위반 장소 제거 + '확인 필요' 표시".
        exhausted = retries_of(state)["draft"] > config.MAX_REDRAFTS
        if violations and exhausted:
            bad = {(v["date"], v["slot"]) for v in violations if v["slot"]}
            out["course"] = {**course, "days": [{**d, "slots": [s for s in d["slots"] if (d["date"], s["slot"]) not in bad]} for d in course["days"]]}
            out["removed"] = [v for v in violations if v["slot"]]
        trace.record("validate_course.check", "tool", input={"rechecked_new": len(need), "draft": retries_of(state)["draft"]},
                     output={"violations": [v["rule"] for v in violations], "removed": len(out.get("removed", []))}, ok=not violations,
                     took_ms=round((time.perf_counter() - t0) * 1000, 2))
        return out
    return update
