"""오프라인 재생의 경계·독립 검사·실패 분류를 검증한다."""
from copy import deepcopy
import hashlib
import json
import socket
import sqlite3
import subprocess

import pytest
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from harness.regression import offline_only, replay_case, run_suite
from scripts.capture_regression import capture
from tests.test_validate import CANDS, D1, good, live
from tests.test_day_repair import case


def fixture():
    return {'version': 1, 'id': 'valid', 'state': {
        'course': good(), 'candidates': deepcopy(CANDS), 'request': {'region': '강릉', 'start_date': D1, 'days': 2},
        'rechecked': {c['id']: live() for c in CANDS}, 'retries': {'draft': 3}}, 'expected': {'slots': 10}}


def test_network_and_child_process_are_blocked_even_if_caller_catches():
    with offline_only() as attempts:
        for action in [lambda: socket.create_connection(('example.com', 443)),
                       lambda: socket.getaddrinfo('example.com', 443),
                       lambda: subprocess.Popen(['echo', 'not-run'])]:
            with pytest.raises(RuntimeError, match='external_access_blocked'):
                action()
        assert len(attempts) == 3


def test_healthy_and_known_issue_are_distinct_and_new_issue_fails():
    assert replay_case(fixture())['status'] == 'PASS'
    f = fixture()
    course, candidates = case()
    candidates.pop('near')
    f['state'].update(course=course, candidates=list(candidates.values()),
                      request={'region': '부산', 'start_date': D1, 'days': 1},
                      rechecked={cid: live() for cid in candidates})
    f['expected'] = {'slots': 5, 'known_issues': [{'rule': 'day_distance', 'date': D1, 'slot': None, 'id': None}]}
    assert replay_case(f)['status'] == 'KNOWN_ISSUE'
    f['expected']['known_issues'][0]['date'] = '2026-11-22'
    assert replay_case(f)['status'] == 'FAIL'


def test_independent_check_catches_empty_course_even_if_node_claims_no_violations(monkeypatch):
    def fake_update(*args, **kwargs):
        return lambda state: {'course': {'days': []}, 'violations': [], 'rechecked': {}}
    monkeypatch.setattr('harness.regression.validate_update', fake_update)
    result = replay_case(fixture())
    assert result['status'] == 'FAIL' and 'slot_count' in result['errors']
    assert result['unexpected']


def test_edit_reason_drift_can_be_known_without_allowing_place_drift(monkeypatch):
    monkeypatch.setattr("harness.regression.preserve_unchanged_reasons", lambda previous, edited, rewrite: edited)
    f = fixture()
    f['state']['mode'] = 'edit'
    f['previous_course'] = deepcopy(f['state']['course'])
    slot = f['state']['course']['days'][0]['slots'][0]
    slot['reason'] = 'changed wording'
    issue = {'rule': 'unrequested_reason_change', 'date': D1, 'slot': '오전', 'id': 's0'}
    f['expected']['known_issues'] = [issue]
    assert replay_case(f)['status'] == 'KNOWN_ISSUE'
    slot['content_id'] = 'x0'
    assert replay_case(f)['status'] == 'FAIL'


def test_allowed_edit_is_not_reported_as_unrequested_change():
    f = fixture()
    f['state']['mode'] = 'edit'
    f['previous_course'] = deepcopy(f['state']['course'])
    f['state']['course']['days'][0]['slots'][0]['content_id'] = 'x0'
    f['expected']['editable_slots'] = [[D1, '오전']]
    assert replay_case(f)['status'] == 'PASS'


def test_missing_and_tampered_fixtures_fail_and_do_not_stop_remaining_cases(tmp_path):
    raw = json.dumps(fixture()).encode()
    (tmp_path/'ok.json').write_bytes(raw)
    entries = [{'id': 'missing', 'file': 'missing.json', 'sha256': ''},
               {'id': 'tampered', 'file': 'ok.json', 'sha256': 'bad'},
               {'id': 'valid', 'file': 'ok.json', 'sha256': hashlib.sha256(raw).hexdigest()}]
    (tmp_path/'manifest.json').write_text(json.dumps({'version': 1, 'cases': entries}))
    result = run_suite(tmp_path, tmp_path/'out')
    assert result['counts'] == {'PASS': 1, 'KNOWN_ISSUE': 0, 'FAIL': 2}
    assert (tmp_path/'out/latest.md').exists()


def test_capture_selects_prevalidation_checkpoint_and_does_not_overwrite(tmp_path):
    state = fixture()['state']
    state['trace'] = [{'node': 'draft_course'}]
    final = {**state, 'course': {'days': []}, 'trace': [{'node': 'respond'}]}
    db = tmp_path/'chat.sqlite'
    with sqlite3.connect(db) as con:
        con.execute('create table checkpoints(thread_id text, checkpoint_id text, type text, checkpoint blob)')
        for index, s in enumerate((state, final)):
            typ, blob = JsonPlusSerializer().dumps_typed({'channel_values': s})
            con.execute('insert into checkpoints values (?,?,?,?)', ('thread', str(index), typ, blob))
    stored = tmp_path/'stored.jsonl'
    stored.write_text('\n'.join(json.dumps(c) for c in CANDS))
    suite = tmp_path/'suite'
    captured = capture(db, 'thread', suite, 'captured', stored)
    assert captured['state']['course']['days']
    assert 'trace' not in captured['state']
    assert replay_case(captured)['status'] == 'PASS'
    with pytest.raises(ValueError, match='immutable'):
        capture(db, 'thread', suite, 'captured', stored)
    assert run_suite(suite, tmp_path/'out')['counts']['PASS'] == 1


def test_cli_strict_mode_fails_for_known_issues_without_hiding_them(monkeypatch, tmp_path):
    from scripts import replay_regressions
    def report(*args):
        return {'counts': {'PASS': 0, 'KNOWN_ISSUE': 1, 'FAIL': 0}}
    monkeypatch.setattr(replay_regressions, 'run_suite', report)
    monkeypatch.setattr('sys.argv', ['replay_regressions', '--suite', str(tmp_path)])
    assert replay_regressions.main() == 0
    monkeypatch.setattr('sys.argv', ['replay_regressions', '--suite', str(tmp_path), '--strict-known'])
    assert replay_regressions.main() == 1


def test_empty_suite_is_an_error(tmp_path):
    (tmp_path/'manifest.json').write_text(json.dumps({'version': 1, 'cases': []}))
    with pytest.raises(ValueError, match='empty_or_unsupported'):
        run_suite(tmp_path, tmp_path/'out')


def test_swallowed_network_attempt_still_fails_case(monkeypatch):
    from harness import regression
    real = regression.validate_update
    def faulty(*args, **kwargs):
        update = real(*args, **kwargs)
        def wrapped(state):
            try:
                socket.create_connection(('example.com', 443))
            except RuntimeError:
                pass
            return update(state)
        return wrapped
    monkeypatch.setattr(regression, 'validate_update', faulty)
    result = replay_case(fixture())
    assert result['status'] == 'FAIL' and 'external_access_attempt' in result['errors']
