"""validate_course 노드의 알맹이. 코드가 코스의 규칙 위반을 찾는다. LLM 은 쓰지 않는다. (14번 6단계)

검사: 칸 구성 · 후보에 없는 장소 · 칸과 유형 · 중복 · 연속 구간 거리(지역별) · 휴무 · 철수(withdrawn).
최종 코스에 들어간 장소만 관광공사에서 다시 받아 그 값으로 휴무를 판정하고, 한 장소는 한 번만 받는다(재작성해도 다시 받지 않는다).
축제는 코스 칸에 넣지 않으므로(5-5) 기간 검사는 해당 없다.
"""
import itertools
import time
from datetime import date

import config
from graph.context import _label, trip_dates
from graph.state import hits_exclusion, normalize_course_ids, retries_of, slots_for
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


def find_violations(course: dict, cands: dict, dates: list, rechecked: dict, region: str | None, slots: list | None = None,
                    exclusions: list | None = None) -> list:
    """순수 함수: 코스 · 후보 · 다시 받은 값으로 위반 목록을 만든다."""
    out, seen, museums = [], set(), 0
    limit = config.MAX_LEG_KM_BY_REGION.get(region, config.MAX_LEG_KM)
    days = course.get("days", [])
    want_slots = slots or config.COURSE_SLOTS   # 커피 · 디저트 취향이면 카페 칸이 하나 더 있다(graph/state.py slots_for)
    # 왜: 취향 음식(닭강정 · 빵 등)이 점심 · 저녁을 모두 채우지 않게 한다. 검색이 단 theme 표시를 쓰므로 어떤 취향이든 된다. 취향 밖 식당 후보가 칸 수만큼 없으면 지킬 수 없어 규칙을 끈다(재작성만 낭비한다). 어디: 식사 칸 검사.
    # 교안: 직접 대응 없음(2026-11-17 결정). 한계: 검색이 취향 질의로만 찾은 식당을 취향 음식으로 본다.
    others = sum(1 for c in cands.values() if c.get("kind") == "food" and not c.get("is_cafe") and not c.get("theme"))
    theme_on = any(c.get("theme") for c in cands.values()) and others >= len(days) * max(sum(1 for n in want_slots if n in ("점심", "저녁")) - config.MAX_THEME_MEALS, 1)
    if dates and [d["date"] for d in days] != dates:
        out.append(_v("dates", f"여행일은 {', '.join(dates)} 입니다. 코스의 날짜가 다릅니다."))
    for d in days:
        slots = d["slots"]
        if [s["slot"] for s in slots] != want_slots:
            out.append(_v("slots", f"{_label(d['date'])}은 {'·'.join(want_slots)} 칸을 순서대로 모두 채워야 합니다.", date=d["date"]))
        prev, theme_meals = None, 0
        for s in slots:
            cid, c = s["content_id"], cands.get(s["content_id"])
            if c is None:
                out.append(_v("unknown_place", f"{cid} 은(는) 후보 목록에 없는 장소입니다. 후보에 있는 id 만 쓰세요.", cid, d["date"], s["slot"]))
                prev = None
                continue
            if s["slot"] == config.CAFE_SLOT:   # 카페 칸에는 카페(원본 분류 FD05)만. 유형은 음식점이라 아래 유형 검사 대신 여기서 본다
                if not c.get("is_cafe"):
                    out.append(_v("cafe_slot", f"카페 칸에는 <카페 후보> 의 카페만 넣을 수 있습니다. {c.get('title')} 은(는) 카페가 아닙니다.", cid, d["date"], s["slot"]))
            want = config.FOOD_TYPES if s["slot"] in ("점심", "저녁", config.CAFE_SLOT) else config.SIGHT_TYPES
            if c.get("type") not in want:
                out.append(_v("slot_type", f"{s['slot']} 칸에는 {'/'.join(want)} 유형만 넣을 수 있습니다. {c.get('title')}({c.get('type')}) 은(는) 맞지 않습니다.", cid, d["date"], s["slot"]))
            if s["slot"] in ("점심", "저녁") and c.get("is_cafe"):   # 카페는 식사 자리가 아니라 "근처 카페 추천"으로 따로 둔다
                out.append(_v("cafe_meal", f"{s['slot']} 칸에는 식당을 넣어야 합니다. {c.get('title')} 은(는) 카페입니다.", cid, d["date"], s["slot"]))
            if theme_on and s["slot"] in ("점심", "저녁") and c.get("theme"):
                theme_meals += 1
                if theme_meals > config.MAX_THEME_MEALS:
                    out.append(_v("theme_repeat", f"{_label(d['date'])}은 [취향 음식] 식당을 {config.MAX_THEME_MEALS}곳까지만 넣을 수 있습니다. {c.get('title')} 은(는) 다른 종류의 식당으로 바꾸세요.", cid, d["date"], s["slot"]))
            if c.get("category") == config.MUSEUM_CLASS:   # 박물관류는 날씨와 상관없이 코스 전체에서 MUSEUM_MAX 곳까지
                museums += 1
                if museums > config.MUSEUM_MAX:
                    out.append(_v("museum_limit", f"박물관 · 미술관 · 전시관은 코스에 {config.MUSEUM_MAX}곳만 넣을 수 있습니다. {c.get('title')} 은(는) 다른 종류로 바꾸세요.", cid, d["date"], s["slot"]))
            hit = hits_exclusion(c, exclusions)   # 제외 조건 낱말이 이름 · 소개에 그대로 있는 장소(9단계 i6: 판정이 통과시켜도 여기서 막는다)
            if hit:
                out.append(_v("excluded", f"{c.get('title')} 은(는) 제외 조건({hit})에 해당합니다. 다른 곳으로 바꾸세요.", cid, d["date"], s["slot"]))
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
        # 하루 직선거리 합 상한(config.MAX_DAY_KM_BY_REGION). 칸이 아니라 하루 전체의 문제라 slot 은 비워 둔다(칸을 빼거나 바꾸지 않고 다시 쓰게만 한다)
        day_limit, legs = config.MAX_DAY_KM_BY_REGION.get(region), _legs(d["slots"], cands)
        if day_limit and legs and legs[0] > day_limit:
            out.append(_v("day_distance", f"{_label(d['date'])}의 이동 거리가 직선 합 {legs[0]:.0f}km 로 하루 상한 {day_limit}km 를 넘습니다. 가까운 장소끼리 묶어 다시 고르세요.", date=d["date"]))
    return out


def _fits(c: dict, slot: str) -> bool:
    """후보가 그 칸에 들어갈 수 있는 종류인가(가볼 곳 칸 · 식사 칸 · 카페 칸)."""
    if slot == config.CAFE_SLOT:
        return bool(c.get("is_cafe"))
    if slot in ("점심", "저녁"):
        return c.get("type") in config.FOOD_TYPES and not c.get("is_cafe")
    return c.get("type") in config.SIGHT_TYPES


def repair_slots(course: dict, cands: dict, dates: list, rechecked: dict, region: str | None, slots: list | None,
                 exclusions: list | None, rest_table: dict | None = None) -> tuple:
    """칸 하나의 위반(거리 · 중복 · 휴무 · 내려간 장소 · 제외 · 박물관 수)을 그 날의 규칙을 새로 어기지 않는 가장 가까운 미사용 후보로 바꾼다. (새 코스, [바꾼 칸 {date, slot, old_id, id, rule}])."""
    # 왜: 재작성을 다 쓰고도 위반이 남으면 칸을 비운 코스가 나갔다(제주 3일 6회 중 2회). 서울 3일에서는 중복 1건뿐인 초안이 다시 쓰다가 나빠졌다(2026-11-19). 칸을 비우거나 다시 쓰기 전에 코드가 규칙에 맞는 후보를 찾아 넣는다. 어디: validate_course.
    # 교안: 설계 원칙 "판정은 코드가". 2026-11-17 거리, 2026-11-19 나머지 칸 위반으로 넓힘. 바꿀 후보가 없으면 예전처럼 그 칸을 뺀다.
    rest_table, replaced = rest_table or {}, []
    course = {**course, "days": [{**d, "slots": [dict(s) for s in d["slots"]]} for d in course.get("days", [])]}
    check = lambda c: find_violations(c, cands, dates, rechecked, region, slots, exclusions)
    key = lambda v: (v["rule"], v["id"], v["date"], v["slot"])
    for _ in range(sum(len(d["slots"]) for d in course["days"])):   # 한 번에 한 칸씩, 더 고칠 것이 없을 때까지
        done = {(r["date"], r["slot"]) for r in replaced}
        before_list = check(course)
        bad = next((v for v in before_list if v["rule"] in config.REPAIR_RULES and v["slot"] and (v["date"], v["slot"]) not in done), None)
        if bad is None:
            break
        before = {key(v) for v in before_list}
        day = next(d for d in course["days"] if d["date"] == bad["date"])
        at = next(n for n, s in enumerate(day["slots"]) if s["slot"] == bad["slot"])
        used = {s["content_id"] for d in course["days"] for s in d["slots"]}
        best = None
        for n in ((at, at - 1) if bad["rule"] == "distance" else (at,)):   # 거리 위반은 "앞 장소 → 이 장소" 구간이다. 이 칸을 먼저 바꿔 보고, 안 되면 앞 칸을 바꿔 본다
            if n < 0 or (day["date"], day["slots"][n]["slot"]) in done:
                continue
            for cid, c in cands.items():
                if cid in used or not _fits(c, day["slots"][n]["slot"]) or rest_table.get(cid, {}).get(day["date"]) == "closed":
                    continue
                trial_day = {**day, "slots": [{**s, "content_id": cid, "reason": config.REPLACED_REASON} if i == n else s for i, s in enumerate(day["slots"])]}
                trial = {**course, "days": [trial_day if d["date"] == day["date"] else d for d in course["days"]]}
                if any(key(v) not in before and v["rule"] != "day_distance" for v in check(trial)):   # 새 위반을 만들면 안 된다. 하루 합 초과는 막지 않는다
                    continue
                legs = _legs(trial_day["slots"], cands)
                if legs and (best is None or legs[0] < best[0]):
                    best = (legs[0], n, cid, trial)
            if best:
                break
        if best is None:
            break   # 바꿀 후보가 없다. 남은 위반은 호출한 쪽이 다시 쓰게 하거나 예전처럼 뺀다
        _, n, cid, trial = best
        replaced.append({"date": day["date"], "slot": day["slots"][n]["slot"], "old_id": day["slots"][n]["content_id"], "id": cid, "rule": bad["rule"]})
        course = trial
    return course, replaced


def repair_day_distance(course: dict, cands: dict, dates: list, rechecked: dict, region: str | None,
                        slots: list, exclusions: list | None, rest_table: dict | None = None) -> tuple:
    """거리 초과일만 완성된 적합 동선으로 바꾼다. 제한 탐색 실패 시 기존 코스를 유지한다."""
    limit = config.MAX_DAY_KM_BY_REGION.get(region)
    if not limit:
        return course, []
    check = lambda value: find_violations(value, cands, dates, rechecked, region, slots, exclusions)
    changes = []
    for day_index, day in enumerate(course.get("days", [])):
        if not any(v["rule"] == "day_distance" and v["date"] == day["date"] for v in check(course)):
            continue
        if [s["slot"] for s in day["slots"]] != slots:
            continue
        ordered, moved = reorder_day(day["slots"], cands, config.MAX_LEG_KM_BY_REGION.get(region, config.MAX_LEG_KM))
        if moved:
            trial = {**course, "days": [{**d, "slots": ordered} if n == day_index else d for n, d in enumerate(course["days"])]}
            if not any(v["date"] == day["date"] for v in check(trial)):
                course = {**trial, "reordered": list(dict.fromkeys([*course.get("reordered", []), day["date"]]))}
                continue
        reserved = {s["content_id"] for n, d in enumerate(course["days"]) if n != day_index for s in d["slots"]}
        reserved.update(s["content_id"] for key in ("backup", "cafes") for s in course.get(key, []))
        baseline = {(v["rule"], v["id"], v["date"], v["slot"]) for v in check(course) if v["date"] != day["date"]}
        beam = [(0, 0.0, [])]
        for original in day["slots"]:
            groups = {}
            for count, _, path in beam:
                used = reserved | {s["content_id"] for s in path}
                for cid, candidate in cands.items():
                    if cid in used or not _fits(candidate, original["slot"]) or (rest_table or {}).get(cid, {}).get(day["date"]) == "closed":
                        continue
                    same = cid == original["content_id"]
                    route = [*path, {**original, "content_id": cid, "reason": original["reason"] if same else config.REPLACED_REASON}]
                    legs = _legs(route, cands)
                    if legs is None or legs[0] > limit:
                        continue
                    trial = {**course, "days": [{**d, "slots": route} if n == day_index else d for n, d in enumerate(course["days"])]}
                    violations = check(trial)
                    if any(v["rule"] != "slots" and (v["rule"], v["id"], v["date"], v["slot"]) not in baseline for v in violations):
                        continue
                    groups.setdefault(count + (not same), []).append((count + (not same), legs[0], route))
            # 왜: 같은 변경 수 안에서 짧은 경로만 남겨 탐색량을 제한한다. 어디: 최종 하루 거리 보정.
            # 교안: 직접 대응 없음. 전역 최적해 보장은 없고 완성된 규칙 통과 동선만 적용한다.
            beam = [item for group in groups.values() for item in sorted(group, key=lambda x: (x[1], tuple(s["content_id"] for s in x[2])))[:config.DAY_REPAIR_BEAM_WIDTH]]
            if not beam:
                break
        if not beam:
            continue
        _, _, route = min(beam, key=lambda x: (x[0], x[1], tuple(s["content_id"] for s in x[2])))
        trial = {**course, "days": [{**d, "slots": route} if n == day_index else d for n, d in enumerate(course["days"])]}
        if any((v["rule"], v["id"], v["date"], v["slot"]) not in baseline for v in check(trial)):
            continue
        changes.extend({"date": day["date"], "slot": old["slot"], "old_id": old["content_id"], "id": new["content_id"], "rule": "day_distance"}
                       for old, new in zip(day["slots"], route) if old["content_id"] != new["content_id"])
        course = trial
    return course, changes


def _legs(slots: list, cands: dict):
    """연속한 칸 사이 직선거리의 (합, 가장 긴 구간). 좌표를 못 구하면 None."""
    total, longest, prev = 0.0, 0.0, None
    for s in slots:
        c = cands.get(s["content_id"])
        if c is None:
            return None
        if prev is not None:
            got = distance_km(prev, c)
            if not got["ok"]:
                return None
            total, longest = total + got["km"], max(longest, got["km"])
        prev = c
    return total, longest


def reorder_day(slots: list, cands: dict, limit: float):
    """같은 종류 칸(가볼 곳끼리, 점심↔저녁)을 서로 바꿔 하루 이동 거리가 가장 짧은 배치를 고른다. (칸 목록, 바꿨는지)."""
    # 왜: LLM 은 칸 순서를 지리로 고르지 못해 지그재그 동선이 잦았다(평가 코스 36일 중 14~18일이 맞바꿈만으로 10% 이상 단축, 2026-11-17 측정). 거리는 코드가 판정한다. 가볼 곳이 3칸이 되어(2026-11-17) 쌍 맞바꿈이 아니라 가볼 곳 칸 안의 모든 순서를 본다. 어디: validate_course 끝.
    # 교안: 직접 대응 없음. 장소와 이유 문장은 함께 옮기고, 이유에 시간 낱말이 있는 칸은 옮기지 않는다. 구간 상한은 넘기지 않는다.
    names = [s["slot"] for s in slots]
    movable = lambda group: [n for n in group if n in names and not any(w in slots[names.index(n)]["reason"] for w in config.REORDER_TIME_WORDS)]
    groups = [g for g in (movable(config.SIGHT_SLOTS), movable(("점심", "저녁"))) if len(g) >= 2]
    base = _legs(slots, cands)
    if not groups or base is None:
        return slots, False
    best, best_slots = base, slots
    for perms in itertools.product(*[itertools.permutations(g) for g in groups]):
        trial = [dict(s) for s in slots]
        for group, perm in zip(groups, perms):
            for key in ("content_id", "reason"):
                values = [slots[names.index(p)][key] for p in perm]
                for slot_name, value in zip(group, values):
                    trial[names.index(slot_name)][key] = value
        got = _legs(trial, cands)
        if got and got[0] < best[0] - config.REORDER_MIN_GAIN_KM and got[1] <= max(limit, base[1]):
            best, best_slots = got, trial
    return best_slots, best_slots is not slots


def validate_update(stored: dict | None, detail, trace):
    stored = stored or {}

    def update(state) -> dict:
        t0 = time.perf_counter()
        course, cands = state.get("course") or {}, {c["id"]: c for c in state.get("candidates", [])}
        course, resolved = normalize_course_ids(course, list(cands.values()))
        if resolved:
            course["resolved_ids"] = [*course.get("resolved_ids", []), *resolved]
        req = state.get("request", {})
        dates = trip_dates(req["start_date"], req["days"]) if req.get("start_date") and req.get("days") else []
        # 왜: 휴무 판정은 최종 코스의 장소만 관광공사에서 다시 받은 값으로 한다. 이미 받은 장소는 다시 받지 않는다(재작성 반복에서 한도를 아낀다). 어디: 검사 직전.
        # 교안: PRD F3 "검증과 표시에는 실시간으로 다시 받은 값을 쓴다". 다시 받기에 실패하면 저장분으로 대신하고 기준일을 남긴다.
        rechecked = dict(state.get("rechecked") or {})
        need = [s["content_id"] for d in course.get("days", []) for s in d["slots"] if s["content_id"] in cands and s["content_id"] not in rechecked]
        need = list(dict.fromkeys(need))
        if need:
            rechecked.update(_recheck(need, stored, detail))
        violations = find_violations(course, cands, dates, rechecked, req.get("region"), slots_for(req, list(cands.values())), req.get("exclusions"))

        # 왜: 휴무 표(5-4)는 저장분 기준이었다. 다시 받은 값으로 코스 장소의 칸을 덮어 써서 다시 쓸 때와 화면 표시가 같은 값을 보게 한다. 어디: rest_table.
        table = {k: dict(v) for k, v in (state.get("rest_table") or {}).items()}
        for cid in need:
            row = {day: r for day in dates if (r := rest_on(rechecked[cid]["place"], date.fromisoformat(day))) != "open"}
            table[cid] = row
        out = {"rechecked": rechecked, "rest_table": table, "violations": violations}
        if resolved:
            out["course"] = course

        # 왜: 두 번 고쳐도 남은 위반은 그 장소를 빼고 "확인 필요"로 알린다(없는 장소 · 규칙 위반 장소를 코스에 남기지 않는다). 어디: 재작성 횟수를 다 쓴 뒤.
        # 교안: PRD 10번 "위반 & 재작성 = 2 → 위반 장소 제거 + '확인 필요' 표시".
        exhausted = retries_of(state)["draft"] > config.MAX_REDRAFTS
        fixable = [v for v in violations if v["rule"] in config.REPAIR_RULES and v["slot"]]
        # 수정 턴(mode=edit)은 사용자가 요청한 칸을 코드가 몰래 바꾸지 않도록 재작성을 다 쓴 뒤에만 바꾼다
        early = not exhausted and state.get("mode") != "edit" and 0 < len(fixable) <= config.REPAIR_MAX_SLOTS
        out["replaced"] = []   # 지난 턴 · 지난 초안의 교체 기록이 남지 않게 비운다
        if fixable and (exhausted or early):
            fixed, replaced = repair_slots(course, cands, dates, rechecked, req.get("region"), slots_for(req, list(cands.values())), req.get("exclusions"), table)
            if replaced:
                # 바꿔 넣은 장소도 휴무를 다시 받아 검사한다. 걸리면 아래에서 예전처럼 그 칸을 뺀다
                rechecked.update(_recheck([r["id"] for r in replaced if r["id"] not in rechecked], stored, detail))
                course, out["rechecked"] = fixed, rechecked
                violations = find_violations(course, cands, dates, rechecked, req.get("region"), slots_for(req, list(cands.values())), req.get("exclusions"))
                out["violations"] = violations
                if not violations or exhausted:   # 다시 쓰게 되면 이 코스는 버려지므로 교체 기록도 남기지 않는다
                    out["course"], out["replaced"] = fixed, replaced
        if exhausted and state.get("mode") != "edit" and any(v["rule"] == "day_distance" for v in violations):
            fixed, changed = repair_day_distance(course, cands, dates, rechecked, req.get("region"), slots_for(req, list(cands.values())), req.get("exclusions"), table)
            if fixed is not course:
                new_ids = list(dict.fromkeys(r["id"] for r in changed if r["id"] not in rechecked))
                rechecked.update(_recheck(new_ids, stored, detail))
                for cid in new_ids:
                    table[cid] = {day: r for day in dates if (r := rest_on(rechecked[cid]["place"], date.fromisoformat(day))) != "open"}
                checked = find_violations(fixed, cands, dates, rechecked, req.get("region"), slots_for(req, list(cands.values())), req.get("exclusions"))
                before = {(v["rule"], v["id"], v["date"], v["slot"]) for v in violations}
                if not any((v["rule"], v["id"], v["date"], v["slot"]) not in before for v in checked):
                    course, violations = fixed, checked
                    out["course"], out["violations"] = fixed, checked
                    out["replaced"].extend(changed)
                out["rechecked"] = rechecked
        if violations and exhausted:
            # 취향 음식 반복(theme_repeat)은 규칙 위반이 아니라 쏠림이라, 재작성을 다 써도 칸을 비우지 않는다
            bad = {(v["date"], v["slot"]) for v in violations if v["slot"] and v["rule"] != "theme_repeat"}
            out["course"] = {**course, "days": [{**d, "slots": [s for s in d["slots"] if (d["date"], s["slot"]) not in bad]} for d in course["days"]]}
            out["removed"] = [v for v in violations if v["slot"] and v["rule"] != "theme_repeat"]
        # 왜: 최종 코스(위반이 없거나 재작성을 다 쓴 뒤)만 칸 순서를 맞바꿔 이동 거리를 줄인다. State 의 코스를 바꿔야 후속 수정이 화면과 같은 순서를 본다. 어디: 위반 처리 직후.
        # 교안: 직접 대응 없음(2026-11-17 결정).
        # 수정 턴(mode=edit)에서는 맞바꾸지 않는다: "점심만 바꿔 줘"에 오전 · 오후 · 저녁 자리까지 움직였다(dev e05, 2026-11-17). 요청한 칸만 바뀌어야 한다
        if (not violations or exhausted) and state.get("mode") != "edit":
            final, limit, days_new = out.get("course", course), config.MAX_LEG_KM_BY_REGION.get(req.get("region"), config.MAX_LEG_KM), []
            moved = list(final.get("reordered", []))
            for d in final.get("days", []):
                slots_new, changed = reorder_day(d["slots"], cands, limit)
                days_new.append({**d, "slots": slots_new})
                if changed and d["date"] not in moved:
                    moved.append(d["date"])
            if final.get("days"):
                out["course"] = {**{k: v for k, v in final.items() if k != "reordered"}, "days": days_new, **({"reordered": moved} if moved else {})}
                # 왜: 맞바꿈 전 하루 거리 위반이 최종 화면에 남지 않도록 실제 최종 동선을 다시 검사한다. 어디: 칸을 제거하지 않은 최종 코스.
                # 교안: 설계 원칙 "판정은 코드가". 제거한 칸은 원래 위반 사유를 유지한다.
                if not out.get("removed"):
                    violations = find_violations(out["course"], cands, dates, rechecked, req.get("region"), slots_for(req, list(cands.values())), req.get("exclusions"))
                    out["violations"] = violations
        trace.record("validate_course.check", "tool", input={"rechecked_new": len(need), "draft": retries_of(state)["draft"]},
                     output={"violations": [v["rule"] for v in violations], "removed": len(out.get("removed", []))}, ok=not violations,
                     took_ms=round((time.perf_counter() - t0) * 1000, 2))
        return out
    return update
