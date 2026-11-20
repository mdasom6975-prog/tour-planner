"""저장된 후보·초안·휴무 응답만으로 검증 노드를 재생한다. 모델 품질 평가는 별도다."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time
from unittest.mock import patch

from graph.context import trip_dates
from graph.menu import place_menu_keywords
from graph.state import normalize_course_ids, preserve_unchanged_reasons, slots_for
from graph.validate import _legs, find_violations, hours_of, validate_update
from harness.trace import Trace


@contextmanager
def offline_only():
    """누락된 녹화값이 있어도 네트워크나 자식 프로세스로 보충하지 않는다."""
    attempts = []
    def blocked(*args, **kwargs):
        attempts.append(True)
        raise RuntimeError("offline_regression_external_access_blocked")
    with patch.object(socket.socket, "connect", blocked), patch.object(socket.socket, "connect_ex", blocked), \
         patch.object(socket, "create_connection", blocked), patch.object(socket, "getaddrinfo", blocked), \
         patch.object(subprocess, "Popen", blocked):
        yield attempts


def signature(v):
    return {key: v.get(key) for key in ("rule", "date", "slot", "id")}


def replay_case(fixture):
    if fixture.get("version") != 1:
        raise ValueError("unsupported_fixture_version")
    state = deepcopy(fixture["state"])
    expected = fixture["expected"]
    calls = []

    def detail(cid):
        calls.append(cid)
        return deepcopy(fixture.get("details", {}).get(cid, {"ok": False, "reason": "not_recorded"}))

    started = time.perf_counter()
    with offline_only() as attempts:
        if fixture.get("previous_course") is not None:
            state["course"] = preserve_unchanged_reasons(fixture["previous_course"], state["course"], state.get("rewrite_reasons", False))
        update = validate_update(fixture.get("stored", {}), detail, Trace(save=False))(state)
    final = update.get("course", state["course"])
    candidates = {c["id"]: c for c in state["candidates"]}
    req = state["request"]
    dates = trip_dates(req["start_date"], req["days"])
    # 왜: 노드가 반환한 위반만 보면 삭제 후 빈 칸을 놓칠 수 있다. 어디: 최종 결과의 독립 재검사.
    # 교안: 설계 원칙 "숫자와 사실 판정은 코드가".
    edit = state.get("mode") == "edit"
    stored = fixture.get("stored", {})
    menus = None if edit else {cid: kw for cid in candidates if (kw := place_menu_keywords(stored.get(cid)))}
    hours = None if edit else hours_of(candidates, stored, update["rechecked"])
    actual = find_violations(final, candidates, dates, update["rechecked"], req.get("region"),
                             slots_for(req, list(candidates.values())), req.get("exclusions"), menus, hours)
    errors = ["external_access_attempt"] if attempts else []
    slots = [s for d in final["days"] for s in d["slots"]]
    if len(slots) != expected["slots"]:
        errors.append("slot_count")
    if update.get("removed"):
        errors.append("removed_places")
    selected = {s["content_id"] for s in slots}
    for key in ("backup", "cafes"):
        for item in final.get(key, []):
            cid = item["content_id"]
            if cid not in candidates or cid in selected:
                errors.append(f"{key}_membership_or_duplicate")
            selected.add(cid)
    previous = fixture.get("previous_course")
    if previous is not None:
        allowed = {tuple(x) for x in expected.get("editable_slots", [])}
        previous, _ = normalize_course_ids(previous, state["candidates"])
        before = {(d["date"], s["slot"]): s for d in previous["days"] for s in d["slots"]}
        after = {(d["date"], s["slot"]): s for d in final["days"] for s in d["slots"]}
        for key, value in before.items():
            if key in allowed:
                continue
            current = after.get(key)
            if current is None or current.get("content_id") != value.get("content_id"):
                actual.append({"rule": "unrequested_place_change", "date": key[0], "slot": key[1], "id": value.get("content_id")})
            elif not state.get("rewrite_reasons", False) and current.get("reason") != value.get("reason"):
                actual.append({"rule": "unrequested_reason_change", "date": key[0], "slot": key[1], "id": value.get("content_id")})
    known = expected.get("known_issues", [])
    unexpected = [signature(v) for v in actual if signature(v) not in known]
    status = "FAIL" if errors or unexpected else "KNOWN_ISSUE" if actual else "PASS"
    return {"id": fixture["id"], "status": status, "slots": len(slots), "removed": len(update.get("removed", [])),
            "errors": sorted(set(errors)), "violations": [signature(v) for v in actual], "unexpected": unexpected,
            "day_km": [{"date": d["date"], "km": round(got[0], 2) if (got := _legs(d["slots"], candidates)) else None}
                       for d in final["days"]], "replacements": len(update.get("replaced", [])),
            "recorded_detail_reads": len(calls), "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}


def run_suite(suite: Path, output: Path):
    manifest = json.loads((suite / "manifest.json").read_text())
    if manifest.get("version") != 1 or not manifest.get("cases"):
        raise ValueError("empty_or_unsupported_suite")
    results = []
    for entry in manifest["cases"]:
        try:
            path = (suite / entry["file"]).resolve()
            if not path.is_relative_to(suite.resolve()):
                raise ValueError("fixture_outside_suite")
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                raise ValueError("fixture_checksum_mismatch")
            fixture = json.loads(raw)
            if fixture["id"] != entry["id"]:
                raise ValueError("fixture_id_mismatch")
            results.append(replay_case(fixture))
        except Exception as exc:
            results.append({"id": entry["id"], "status": "FAIL", "errors": [type(exc).__name__],
                            "slots": None, "removed": None, "violations": [], "day_km": []})
    root = Path(__file__).resolve().parent.parent
    source_hash = hashlib.sha256(b"".join((root / p).read_bytes() for p in ("config.py", "graph/validate.py", "graph/state.py"))).hexdigest()
    report = {"version": 1, "scope": "saved_validation_only", "network": "blocked", "model_calls": 0,
              "validator_sha256": source_hash,
              "counts": {s: sum(r["status"] == s for r in results) for s in ("PASS", "KNOWN_ISSUE", "FAIL")}, "cases": results}
    output.mkdir(parents=True, exist_ok=True)
    (output / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    lines = ["# 오프라인 회귀 검증", "", "모델·외부 API 호출 없음. 저장된 초안과 휴무 정보 기준이며 최신 추천 품질·UI 검증은 포함하지 않음.", "",
             "| 사례 | 상태 | 칸 | 삭제 | 날짜별 직선 합 km | 남은 문제 |", "| --- | --- | ---: | ---: | --- | --- |"]
    for r in results:
        distances = ", ".join(f"{d['date']}: {d['km']}" for d in r["day_km"])
        issues = ", ".join(f"{v['rule']} ({v['date']} {v.get('slot') or ''})" for v in r["violations"])
        issues = ", ".join(filter(None, [issues, *r["errors"]]))
        lines.append(f"| {r['id']} | {r['status']} | {r['slots']} | {r['removed']} | {distances} | {issues} |")
        print(f"{r['status']:11} {r['id']}: slots={r['slots']} removed={r['removed']} violations={len(r['violations'])}")
    lines += ["", "KNOWN_ISSUE는 기록된 기존 문제를 표시하며 합격으로 취급하지 않음. FAIL은 새 실패·검증 실행 실패.", ""]
    (output / "latest.md").write_text("\n".join(lines))
    return report
