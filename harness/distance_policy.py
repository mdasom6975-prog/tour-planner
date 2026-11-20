"""현재 코스·기존 검증은 그대로 두고 제안한 하루 거리 정책만 비교한다."""
import hashlib
import json
import math
from pathlib import Path

import config
from graph.state import normalize_course_ids
from graph.validate import _legs
from harness.regression import offline_only, run_suite

MODES = ("transit", "car", "walk")


def assess_day(region, mode, km):
    if mode not in MODES or region not in config.PROPOSED_DAY_KM:
        return {"status": "unknown", "recommended_km": None, "max_km": None}
    recommended, maximum = config.PROPOSED_WALK_DAY_KM if mode == "walk" else config.PROPOSED_DAY_KM[region][mode]
    if km is None or not math.isfinite(km) or km < 0:
        status = "unknown"
    else:
        status = "recommended" if km <= recommended else "long_day" if km <= maximum else "exceeds_max"
    return {"status": status, "recommended_km": recommended, "max_km": maximum}


def compare(suite: Path, output: Path):
    with offline_only():
        baseline = run_suite(suite, output / "legacy")
        manifest = json.loads((suite / "manifest.json").read_text())
        entries = {e["id"]: e for e in manifest["cases"]}
        rows = []
        for result in baseline["cases"]:
            if result["status"] == "FAIL":
                continue
            entry = entries[result["id"]]
            path = (suite / entry["file"]).resolve()
            if not path.is_relative_to(suite.resolve()):
                raise ValueError("fixture_outside_suite")
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                raise ValueError("fixture_changed_during_comparison")
            state = json.loads(raw)["state"]
            region = state["request"].get("region")
            course, _ = normalize_course_ids(state["course"], state["candidates"])
            candidates = {c["id"]: c for c in state["candidates"]}
            draft = [{"date": d["date"], "km": got[0] if (got := _legs(d["slots"], candidates)) else None} for d in course["days"]]
            for stage, days in (("saved_draft", draft), ("legacy_corrected", result["day_km"])):
                for day in days:
                    km = day["km"]
                    old = config.MAX_DAY_KM_BY_REGION.get(region)
                    rows.append({"case": result["id"], "region": region, "stage": stage, "date": day["date"], "km": km,
                                 "legacy_max_km": old, "legacy": "unknown" if km is None or old is None else "within_limit" if km <= old else "exceeds_max",
                                 "scenarios": {mode: assess_day(region, mode, km) for mode in MODES}})
    counts = {}
    for stage in ("saved_draft", "legacy_corrected"):
        counts[stage] = {mode: {status: sum(r["stage"] == stage and r["scenarios"][mode]["status"] == status for r in rows)
                                for status in ("recommended", "long_day", "exceeds_max", "unknown")} for mode in MODES}
    report = {"version": 1, "scope": "distance_scenarios_only", "runtime_policy_changed": False, "model_calls": 0,
              "network": "blocked", "counts": counts, "baseline": baseline["counts"], "rows": rows,
              "limits": config.PROPOSED_DAY_KM, "walk_limits": config.PROPOSED_WALK_DAY_KM,
              "notes": ["Saved transport mode was not inferred or persisted.", "No new itinerary optimization under proposed limits.",
                        "Drafts may violate non-distance rules.", "Straight-line legs only; excludes lodging, airport and onsite walking.",
                        "Existing per-leg distance rules remain unchanged; this compares only the daily distance rule.",
                        "Four snapshots cover Busan and Gangneung only; Seoul and Jeju have boundary tests, not real samples."]}
    output.mkdir(parents=True, exist_ok=True)
    (output / "distance-comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    labels = {"recommended": "추천 범위", "long_day": "이동 많음", "exceeds_max": "최대 초과", "unknown": "판정 불가", "within_limit": "기준 이내"}
    lines = ["# 지역·이동 수단별 하루 거리 기준 비교", "", "기존 엔진 기준 유지. 이동 수단은 가정한 시나리오이며 실제 사용자 선택이 아님. 모델·외부 API 호출 없음.", "",
             "직선거리 합만 비교하며 교통시간·보행거리 추정이나 전체 코스 합격 판정이 아님. 숙소·공항·관광지 내부 이동 제외.", "",
             "| 사례 | 입력 단계 | 날짜 | km | 기존 | 대중교통 | 자동차 | 도보 |", "| --- | --- | --- | ---: | --- | --- | --- | --- |"]
    for r in rows:
        scenario = " | ".join(labels[r["scenarios"][m]["status"]] for m in MODES)
        lines.append(f"| {r['case']} | {r['stage']} | {r['date']} | {r['km']} | {labels[r['legacy']]} | {scenario} |")
    lines += ["", "saved_draft는 검증 전 초안으로 유형 등 다른 위반을 포함할 수 있음. legacy_corrected는 기존 기준으로 보정한 코스를 그대로 재판정한 결과.",
              "", "부산·강릉 저장 기록 4건뿐이며 같은 여행의 생성/수정 기록을 포함함. 서울·제주는 실제 사례를 검증한 것이 아님.",
              "", "새 기준으로 장소 재배치·재작성은 하지 않음. 구간별 기존 상한은 그대로 유지하며 이번 표는 하루 합에 대한 판정만 표시함.", ""]
    (output / "distance-comparison.md").write_text("\n".join(lines))
    return report
