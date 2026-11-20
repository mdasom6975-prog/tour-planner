"""평가 실행 기록을 채점한다: 기대 동작 · 코스 규칙 · 속도 · 토큰. 모델을 부르지 않는다. (PRD 12-2, 14번 8-3)

validate_course 가 "통과"라고 한 코스를 믿지 않고, 실행 기록의 장소 id 와 고정 사본만으로 다시 검사한다.
실행:  python -m eval.score                 (가장 최근 실행)
       python -m eval.score runs/eval/20261116-112918
"""
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import config
from eval.quality import course_quality
from tools.rest import rest_on

ROOT = Path(__file__).resolve().parent.parent
RULES = ("unknown_place", "distance", "closed", "festival_period")   # PRD 12-2 "절대 하면 안 되는 것" 네 가지
FESTIVAL = config.DETAIL_TYPES["15"]


def _km(a: dict, b: dict) -> float | None:
    # 왜: 검증기(tools/geo.py)와 같은 함수를 쓰면 그 함수의 버그를 채점기도 그대로 지나친다. 거리는 여기서 따로 계산한다. 어디: 거리 규칙.
    # 교안: 2일차 Part3 "채점자는 채점 대상과 따로" — 직접 대응 없음(코드 채점기에 적용).
    try:
        la1, lo1, la2, lo2 = (math.radians(float(x)) for x in (a["lat"], a["lon"], b["lat"], b["lon"]))
    except (KeyError, TypeError, ValueError):
        return None
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def _ymd(text) -> date | None:
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8])) if text and len(text) == 8 else None
    except (TypeError, ValueError):
        return None


def rule_violations(turn: dict, places: dict) -> list:
    """코스 한 건의 규칙 위반 목록. places 는 {id: 고정 사본의 장소}."""
    out = []
    region = (turn.get("request") or {}).get("region")
    limit = config.MAX_LEG_KM_BY_REGION.get(region, config.MAX_LEG_KM)
    days = turn.get("course", [])
    trip = [date.fromisoformat(d["date"]) for d in days]
    for d in days:
        day, prev = date.fromisoformat(d["date"]), None
        for s in d["slots"]:
            p = places.get(str(s["id"]))
            where = f'{d["date"]} {s["slot"]} {s.get("title")}'
            # 왜: 사본에 없는 id, 다른 지역의 장소, 비표출 장소는 모두 "보여 주면 안 되는 장소"다. 어디: 없는 장소 규칙.
            # 교안: PRD 8번 "장소는 검색 결과에 있던 content_id 만".
            if p is None or p.get("region") != region or p.get("showflag") == "0":
                out.append({"rule": "unknown_place", "where": where})
                prev = None
                continue
            if prev is not None:
                km = _km(prev, p)
                if km is not None and km > limit:
                    out.append({"rule": "distance", "where": where, "km": round(km, 1), "limit": limit})
            prev = p
            if rest_on(p, day) == "closed":
                out.append({"rule": "closed", "where": where})
            if p.get("type") == FESTIVAL:   # 축제를 칸에 넣었다면 그날이 행사 기간 안이어야 한다
                start, end = _ymd((p.get("extra") or {}).get("event_start")), _ymd((p.get("extra") or {}).get("event_end"))
                if start is None or end is None or not start <= day <= end:
                    out.append({"rule": "festival_period", "where": where})
    for f in turn.get("festivals", []):   # "이 기간 축제"로 안내한 행사는 여행 날짜와 하루라도 겹쳐야 한다
        try:
            start, end = date.fromisoformat(f["event_start"]), date.fromisoformat(f["event_end"])
        except (KeyError, TypeError, ValueError):
            start = end = None
        if not trip or start is None or start > trip[-1] or end < trip[0]:
            out.append({"rule": "festival_period", "where": f'안내 {f.get("title")}'})
    return out


def expect_failures(row: dict, places: dict) -> list:
    """기대값과 다른 점을 글로 돌려준다. 빈 목록이면 통과."""
    exp, turns = row["expect"], row["turns"]
    if "alt" in exp:   # 모델이 읽는 방식에 따라 맞는 답이 둘인 문항(b05): 어느 한쪽 기대에 맞으면 통과
        first = expect_failures({**row, "expect": {k: v for k, v in exp.items() if k != "alt"}}, places)
        return first if not first or expect_failures({**row, "expect": exp["alt"]}, places) else []
    if row.get("error") or not turns:
        return [f'실행 오류: {row.get("error") or "턴 없음"}']
    last, req, bad = turns[-1], turns[-1].get("request") or {}, []
    if last["kind"] != exp["kind"]:
        return [f'답 종류 {last["kind"]} (기대 {exp["kind"]})']
    for key in ("region", "place", "days", "start_date"):
        if key in exp and req.get(key) != exp[key]:
            bad.append(f"{key} {req.get(key)} (기대 {exp[key]})")
    lacking = [m for m in exp.get("missing", []) if m not in last.get("missing", [])]
    if lacking:
        bad.append(f"되묻기 사유에 없음: {lacking}")
    titles = [s.get("title") or "" for d in last.get("course", []) for s in d["slots"]]
    ids = [str(s["id"]) for d in last.get("course", []) for s in d["slots"]]
    text, notices = last.get("text", ""), " ".join(last.get("notices", []))
    if "museum_max" in exp:
        museums = sum(1 for i in ids + [str(b["id"]) for b in last.get("backup", [])] if (places.get(i) or {}).get("category") == config.MUSEUM_CLASS)
        if museums > exp["museum_max"]:
            bad.append(f'박물관류 {museums}곳 (최대 {exp["museum_max"]})')
    if "notice_has" in exp and exp["notice_has"] not in notices:
        bad.append(f'안내에 없음: {exp["notice_has"]}')
    if "text_has" in exp and exp["text_has"] not in text:
        bad.append(f'답에 없음: {exp["text_has"]}')
    bad += [f"답에 있으면 안 됨: {w}" for w in exp.get("text_not", []) if w in text or w in notices]
    bad += [f"코스에 없음: {w}" for w in exp.get("title_has", []) if not any(w in t for t in titles)]
    # 왜: "요청하신 ○○식당은 후보에 없어 대신 골랐습니다"처럼 없는 장소를 사실대로 말하는 것은 잘한 것이다. 장소 이름 칸만 본다(2026-11-16 a02 실행에서 확인). 어디: 없는 장소 강요 문항.
    # 교안: 직접 대응 없음.
    bad += [f"코스에 있으면 안 됨: {w}" for w in exp.get("title_not", []) if any(w in t for t in titles)]
    used = {s["slot"] for d in last.get("course", []) for s in d["slots"]}
    bad += [f"코스에 없는 칸: {w}" for w in exp.get("slots_has", []) if w not in used]
    if "mode" in exp and last.get("mode") != exp["mode"]:
        bad.append(f'경로 {last.get("mode")} (기대 {exp["mode"]})')
    if exp.get("changed") and len(turns) >= 2:
        # 왜: "첫째 날 점심만 바꿔 줘"는 그 칸이 바뀌고 나머지는 그대로여야 한다. 첫 턴과 마지막 턴의 칸을 비교한다. 어디: 후속 수정 문항.
        # 교안: 직접 대응 없음.
        def slots(turn):
            return {(d["date"], s["slot"]): str(s["id"]) for d in turn.get("course", []) for s in d["slots"]}
        before, after = slots(turns[0]), slots(last)
        want = {tuple(c) for c in exp["changed"]}
        for key in sorted(set(before) | set(after)):
            moved = before.get(key) != after.get(key)
            if key in want and not moved:
                bad.append(f"바뀌지 않음: {key[0]} {key[1]}")
            if key not in want and moved:
                bad.append(f"요청하지 않은 칸이 바뀜: {key[0]} {key[1]}")
    return bad


def _avg(values: list):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def quality_summary(qs: list) -> dict:
    """코스별 품질 지표의 합계 · 평균. 합격선은 없다(기준선 기록)."""
    asked = {k: [q["request"][k]["ratio"] for q in qs if q["request"].get(k) and q["request"][k]["ratio"] is not None] for k in ("access", "pet")}
    pos = {k: [q["positive"][k]["ratio"] for q in qs if (q.get("positive") or {}).get(k) and q["positive"][k]["ratio"] is not None] for k in ("access", "pet")}
    paired = [q for q in qs if q["route"]["gain_km"] is not None]
    return {"courses": len(qs),
            "km_after_total": round(sum(q["route"]["after_km"] for q in qs if q["route"]["after_km"] is not None), 2),
            # 왜: 전 · 후 합계를 서로 다른 코스 집합으로 비교하면 줄어든 양이 틀려 보인다. 전 · 후가 모두 있는 코스(gain_km 가 있는 코스)에서만 합친다. 어디: 동선 요약.
            # 교안: 직접 대응 없음.
            "km_paired": len(paired), "km_paired_before": round(sum(q["route"]["before_km"] for q in paired), 2),
            "km_paired_after": round(sum(q["route"]["after_km"] for q in paired), 2), "km_paired_gain": round(sum(q["route"]["gain_km"] for q in paired), 2),
            "km_after_avg": _avg([q["route"]["after_km"] for q in qs]),
            "slots_per_day_avg": _avg([n for q in qs for n in q["shape"]["slots_per_day"]]),
            "hours_slots": sum(q["shape"]["slots"] for q in qs), "hours_known": sum(q["shape"]["with_hours"] for q in qs),
            # 왜: 칸 시간대와 이용시간이 충돌하는 칸 수(T4). 예전 기록의 quality 에는 hours 칸이 없을 수 있어 .get 으로 읽는다. 어디: 하루 시간 배분 요약.
            # 교안: 직접 대응 없음. 합격선 없음.
            "hours_judged": sum(q["hours"]["judged"] for q in qs if q.get("hours")), "hours_closed": sum(q["hours"]["closed"] for q in qs if q.get("hours")),
            "hours_unknown": sum(q["hours"]["unknown"] for q in qs if q.get("hours")), "hours_courses_with_closed": sum(1 for q in qs if (q.get("hours") or {}).get("closed")),
            "menu_pairs": sum(q["menu"]["pairs"] for q in qs), "menu_places": sum(q["menu"]["places"] for q in qs),
            "menu_courses_with_dup": sum(1 for q in qs if q["menu"]["pairs"]),
            "access_asked": len(asked["access"]), "access_ratio_avg": _avg(asked["access"]),
            "pet_asked": len(asked["pet"]), "pet_ratio_avg": _avg(asked["pet"]),
            # 왜: 위 두 비율은 "정보 유무"라 반려동물 '불가' 표기도 센다. 긍정(휠체어 접근 가능 · 반려 가능)만의 비율을 따로 낸다(2026-11-19 T3). 어디: 요청 반영 요약.
            # 교안: 직접 대응 없음. 예전 기록에는 positive 칸이 없어 .get 으로 읽는다(결과표는 모델 호출 없이 다시 만들 수 있다).
            "access_positive_avg": _avg(pos["access"]), "pet_positive_avg": _avg(pos["pet"])}


def score_rows(rows: list, places: dict) -> dict:
    """문항별 채점과 합계. 코스 규칙 위반의 합격선은 0건, 속도는 config.EVAL_MAX_SEC 초 이내."""
    items, by_rule, steps = [], {r: 0 for r in RULES}, {}
    for row in rows:
        last = row["turns"][-1] if row["turns"] else {}
        violations = rule_violations(last, places) if last.get("kind") == "course" else []
        for v in violations:
            by_rule[v["rule"]] += 1
        for t in row["turns"]:
            for s in t["steps"]:
                if s["kind"] == "node" and s["took_ms"] is not None:
                    steps.setdefault(s["step"], []).append(s["took_ms"])
        failures = expect_failures(row, places)
        items.append({"id": row["id"], "case": row["case"], "kind": last.get("kind"), "expect_ok": not failures, "failures": failures,
                      "violations": violations, "left_by_validator": last.get("violations", []), "removed": last.get("removed", 0),
                      "took_sec": row["took_sec"], "slow": row["took_sec"] > config.EVAL_MAX_SEC,
                      "quality": course_quality(row["turns"], places),   # 코스가 아니면 None. 합격선 없는 기준선 지표(eval/quality.py)
                      "llm_calls": sum(t["llm_calls"] for t in row["turns"]),
                      "tokens": sum(t["input_tokens"] + t["output_tokens"] for t in row["turns"])})
    courses = [i for i in items if i["kind"] == "course"]
    cases = {}
    for i in items:
        c = cases.setdefault(i["case"], {"items": 0, "expect_ok": 0})
        c["items"] += 1
        c["expect_ok"] += i["expect_ok"]
    return {"items": items, "count": len(items), "expect_ok": sum(i["expect_ok"] for i in items), "by_case": cases,
            "courses": len(courses), "rule_violations": by_rule, "rule_total": sum(by_rule.values()),
            "left_by_validator": sum(len(i["left_by_validator"]) for i in items), "removed": sum(i["removed"] for i in items),
            "slow": sum(i["slow"] for i in items),
            "course_sec_avg": round(sum(i["took_sec"] for i in courses) / len(courses), 1) if courses else None,
            "course_sec_max": max((i["took_sec"] for i in courses), default=None),
            "tokens": sum(i["tokens"] for i in items),
            "quality": quality_summary([i["quality"] for i in courses if i.get("quality")]),
            "step_ms_avg": {k: round(sum(v) / len(v)) for k, v in sorted(steps.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))}}


def to_markdown(run: str, provider: str, model: str, meta: dict, s: dict) -> str:
    """사람이 읽는 결과표. 관광공사 문장은 넣지 않고 장소 이름과 숫자만 적는다."""
    lines = [f"# 코스 평가 {run} · {provider} ({model})", "",
             f"- 코드 {meta.get('git', '?')} · 데이터 {meta.get('places', '?')} ({meta.get('place_count', '?')}곳) · 날씨 {meta.get('weather')} · 실시간 조회 {meta.get('detail')}", "",
             "| 지표 | 값 | 합격선 |", "| --- | --- | --- |",
             f"| 기대 동작 일치 | {s['expect_ok']}/{s['count']} | — |",
             f"| 코스 규칙 위반 (없는 장소 · 거리 · 휴무 · 기간 밖 축제) | {s['rule_total']}건 {s['rule_violations']} (코스 {s['courses']}건) | 0건 |",
             f"| 검증기가 남긴 위반 · 뺀 장소 | {s['left_by_validator']}건 · {s['removed']}곳 | — |",
             f"| {config.EVAL_MAX_SEC}초를 넘긴 문항 | {s['slow']}/{s['count']} (코스 평균 {s['course_sec_avg']}초 · 최대 {s['course_sec_max']}초) | 0건 |",
             f"| 토큰 합계 | {s['tokens']:,} | — |", "",
             "유형별 기대 동작 일치: " + " · ".join(f"{c} {v['expect_ok']}/{v['items']}" for c, v in s["by_case"].items()), "",
             "단계별 평균 시간(ms): " + " · ".join(f"{k} {v:,}" for k, v in s["step_ms_avg"].items()), "",
             "| 문항 | 유형 | 답 | 기대 | 규칙 위반 | 시간(초) | LLM 호출 | 토큰 | 다른 점 |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for i in s["items"]:
        rules = ", ".join(f'{v["rule"]}({v["where"]})' for v in i["violations"]) or "—"
        lines.append(f"| {i['id']} | {i['case']} | {i['kind']} | {'통과' if i['expect_ok'] else '실패'} | {rules} | {i['took_sec']} | {i['llm_calls']} | {i['tokens']:,} | {'; '.join(i['failures']) or '—'} |")

    q = s.get("quality") or {}
    if q.get("courses"):
        lines += ["", "## 코스 품질 지표 (기준선 · 합격선 없음)", "",
                  f"- 동선 직선거리: 코스 {q['courses']}건 합계 {q['km_after_total']}km (평균 {q['km_after_avg']}km)",
                  f"- 재배열 전 · 후 (전 · 후가 모두 있는 코스 {q['km_paired']}건만): 전 {q['km_paired_before']}km → 후 {q['km_paired_after']}km, 줄어든 합 {q['km_paired_gain']}km",
                  f"- 하루 칸 수 평균 {q['slots_per_day_avg']} · 이용시간 정보가 있는 칸 {q['hours_known']}/{q['hours_slots']}",
                  f"- 칸 시간대 충돌(칸 대표 시각에 문을 닫는 칸): 시간 판정이 가능한 칸 {q.get('hours_judged')}곳 중 {q.get('hours_closed')}곳 · 판정 불가 {q.get('hours_unknown')}곳 (충돌이 있는 코스 {q.get('hours_courses_with_closed')}/{q['courses']}건)",
                  f"- 식당 메뉴 겹침: {q['menu_pairs']}쌍 · {q['menu_places']}곳 (겹친 코스 {q['menu_courses_with_dup']}/{q['courses']}건)",
                  f"- 요청 반영(정보 유무 — 반려동물 '불가 · 없음' 표기도 정보 있음으로 셈): 무장애 요청 {q['access_asked']}건 정보 있는 장소 비율 평균 {q['access_ratio_avg']} · 반려동물 요청 {q['pet_asked']}건 정보 있는 장소 비율 평균 {q['pet_ratio_avg']}",
                  f"- 요청 반영(긍정만 — 휠체어 접근 가능 · 반려동물 가능): 무장애 장소 비율 평균 {q.get('access_positive_avg')} · 반려동물 장소 비율 평균 {q.get('pet_positive_avg')}", "",
                  "| 문항 | 동선 전(km) | 동선 후(km) | 하루 칸 수 | 이용시간 있는 칸 | 시간 충돌 칸 / 판정 가능 / 판정 불가 | 메뉴 겹침 쌍 · 장소 | 무장애 정보 있음 | 반려동물 정보 있음 | 휠체어 접근 가능 | 반려동물 가능 |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        ratio = lambda r: "해당 없음" if r is None else f"{r['with_info']}/{r['places']}"
        hrs = lambda h: "—" if not h else f"{h['closed']} / {h['judged']} / {h['unknown']}"
        good = lambda r: "해당 없음" if r is None else f"{r['positive']}/{r['places']}"
        for i in s["items"]:
            if i.get("quality"):
                c = i["quality"]
                lines.append(f"| {i['id']} | {c['route']['before_km'] if c['route']['before_km'] is not None else '—'} | {c['route']['after_km'] if c['route']['after_km'] is not None else '—'} | "
                             f"{'·'.join(map(str, c['shape']['slots_per_day']))} | {c['shape']['with_hours']}/{c['shape']['slots']} | {hrs(c.get('hours'))} | {c['menu']['pairs']}쌍 · {c['menu']['places']}곳 | "
                             f"{ratio(c['request']['access'])} | {ratio(c['request']['pet'])} | {good((c.get('positive') or {}).get('access'))} | {good((c.get('positive') or {}).get('pet'))} |")
    return "\n".join(lines) + "\n"


def latest_run() -> Path | None:
    runs = sorted(p for p in (ROOT / config.EVAL_RUNS_DIR).glob("*") if p.is_dir())
    return runs[-1] if runs else None


def main():
    run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_run()
    if run_dir is None or not run_dir.exists():
        sys.exit("채점할 실행 기록이 없습니다. 먼저 python -m eval.run 을 실행하세요")
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    with (ROOT / meta["places"]).open(encoding="utf-8") as f:
        places = {p["id"]: p for p in map(json.loads, f)}
    out_dir = ROOT / config.EVAL_RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(run_dir.glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        s = score_rows(rows, places)
        (run_dir / f"{path.stem}.score.json").write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        table = out_dir / f"{run_dir.name}_{path.stem}.md"
        table.write_text(to_markdown(run_dir.name, path.stem, meta.get("models", {}).get(path.stem, "?"), meta, s), encoding="utf-8")
        print(f"{path.stem}: 기대 동작 {s['expect_ok']}/{s['count']} · 규칙 위반 {s['rule_total']}건 {s['rule_violations']} · "
              f"{config.EVAL_MAX_SEC}초 초과 {s['slow']}건 · 코스 평균 {s['course_sec_avg']}초 · 토큰 {s['tokens']:,} → {table.relative_to(ROOT)}")
        for i in s["items"]:
            if i["failures"] or i["violations"]:
                print(f"  {i['id']} {i['case']}: {'; '.join(i['failures'])} {[v['rule'] + ' ' + v['where'] for v in i['violations']]}")


if __name__ == "__main__":
    main()
