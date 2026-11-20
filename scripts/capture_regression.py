"""읽기 전용 체크포인트에서 검증 직전 초안을 독립된 오프라인 사례로 보존한다."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from graph.state import slots_for

STATE_KEYS = ("course", "candidates", "request", "rechecked", "rest_table", "retries", "mode", "rewrite_reasons")
REST_KEYS = ("rest_status", "rest_weekdays", "rest_nth", "rest_note", "fetched", "hours_text")


def capture(db, thread, suite, name, stored_path, known_issues=(), editable=(), mode=None):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name):
        raise ValueError("invalid_case_name")
    path = suite / f"{name}.json"
    if path.exists():
        raise ValueError("immutable_fixture_already_exists")
    serde = JsonPlusSerializer()
    states = []
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as con:
        for typ, blob in con.execute("select type, checkpoint from checkpoints where thread_id=? order by checkpoint_id desc", (thread,)):
            states.append(serde.loads_typed((typ, blob)).get("channel_values", {}))
    def last_node(state):
        last = (state.get("trace") or [{}])[-1]
        return last.get("node", last.get("step"))
    chosen = next((i for i, s in enumerate(states) if last_node(s) in ("draft_course", "edit_course")
                   and s.get("course", {}).get("days") and (mode is None or s.get("mode") == mode)), None)
    if chosen is None:
        raise ValueError("no_prevalidation_checkpoint")
    raw = states[chosen]
    state = {k: raw[k] for k in STATE_KEYS if k in raw}
    ids = {c["id"] for c in state["candidates"]}
    stored = {}
    with stored_path.open() as source:
        for line in source:
            row = json.loads(line)
            if row["id"] in ids:
                stored[row["id"]] = {key: row.get(key) for key in REST_KEYS}
                stored[row["id"]]["extra"] = {"menu_main": (row.get("extra") or {}).get("menu_main")}
    expected = {"slots": state["request"]["days"] * len(slots_for(state["request"], state["candidates"])),
                "known_issues": [{"rule": parts[0], "date": parts[1], "slot": parts[2] if len(parts) > 2 else None,
                                  "id": parts[3] if len(parts) > 3 else None} for parts in known_issues]}
    fixture = {"version": 1, "id": name, "state": state, "stored": stored, "expected": expected,
               "details": {cid: {"ok": True, **value} for cid, value in raw.get("rechecked", {}).items()}}
    if state.get("mode") == "edit":
        previous = next((s.get("course") for s in states[chosen + 1:] if s.get("mode") != "edit"
                         and last_node(s) == "respond" and s.get("course", {}).get("days")), None)
        if previous is None:
            raise ValueError("missing_previous_course_for_edit")
        fixture["previous_course"] = previous
        expected["editable_slots"] = list(editable)
    suite.mkdir(parents=True, exist_ok=True)
    manifest_path = suite / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"version": 1, "cases": []}
    if any(c["id"] == name for c in manifest["cases"]):
        raise ValueError("duplicate_case_id")
    raw_bytes = (json.dumps(fixture, ensure_ascii=False, indent=2) + "\n").encode()
    path.write_bytes(raw_bytes)
    manifest["cases"].append({"id": name, "file": path.name, "sha256": hashlib.sha256(raw_bytes).hexdigest()})
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return fixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--thread", required=True)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--mode", choices=("new", "edit"))
    parser.add_argument("--stored", type=Path, default=Path(__file__).resolve().parent.parent / "data/processed/places.jsonl")
    parser.add_argument("--known-issue", action="append", default=[], metavar="RULE@DATE[@SLOT@ID]")
    parser.add_argument("--editable-slot", action="append", default=[], metavar="DATE@SLOT")
    args = parser.parse_args()
    capture(args.db, args.thread, args.suite, args.name, args.stored,
            [x.split("@") for x in args.known_issue], [x.split("@", 1) for x in args.editable_slot], args.mode)
    print(f"저장 완료: {args.name} (모델·외부 API 호출 없음)")


if __name__ == "__main__":
    main()
