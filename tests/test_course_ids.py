"""모델이 ID 대신 후보 이름을 반환해도 후보 경계와 후속 검증을 유지한다."""
from copy import deepcopy

from graph.course import pack_course
from graph.schemas import Course
from graph.state import normalize_course_ids
from graph.validate import validate_update
from harness.trace import Trace
from tests.test_validate import CANDS, good, live


def test_exact_unique_titles_only_and_no_input_mutation():
    candidates = [{'id': '1', 'title': '사찰'}, {'id': '2', 'title': '동명이소'},
                  {'id': '3', 'title': '동명이소'}, {'id': '4', 'title': '1'}]
    course = {'days': [{'slots': [{'content_id': x} for x in [' 사찰 ', '동명이소', '없는곳', '1']]}]}
    original = deepcopy(course)
    out, changes = normalize_course_ids(course, candidates)
    assert [s['content_id'] for s in out['days'][0]['slots']] == ['1', '동명이소', '없는곳', '1']
    assert changes == [{'from': ' 사찰 ', 'id': '1'}]
    assert course == original


def test_pack_resolves_before_overlap_and_pool_filters():
    candidates = [{'id': '1', 'title': '관광지'}, {'id': '2', 'title': '카페'}, {'id': '3', 'title': '실내'}]
    got = Course.model_validate({'days': [{'date': '2026-11-21', 'slots': [
        {'slot': '오전', 'content_id': '관광지', 'reason': 'r'}]}],
        'cafes': [{'content_id': x, 'reason': 'r'} for x in ['카페', '2']],
        'backup': [{'content_id': x, 'reason': 'r'} for x in ['실내', '카페', '관광지']]})
    out = pack_course(got, [candidates[2]], [candidates[1]], candidates=candidates)
    assert out['days'][0]['slots'][0]['content_id'] == '1'
    assert [c['content_id'] for c in out['cafes']] == ['2']
    assert [c['content_id'] for c in out['backup']] == ['3']
    assert got.days[0].slots[0].content_id == '관광지'


def test_validator_resolves_saved_course_and_still_rejects_unknown():
    course = good()
    titles = {c['id']: c['title'] for c in CANDS}
    for day in course['days']:
        for slot in day['slots']:
            slot['content_id'] = titles[slot['content_id']]
    state = {'course': course, 'candidates': CANDS, 'rechecked': {c['id']: live() for c in CANDS},
             'request': {'region': '강릉', 'start_date': '2026-11-21', 'days': 2}, 'retries': {'draft': 3}}
    update = validate_update({}, None, Trace(save=False))
    out = update(state)
    assert out['violations'] == []
    assert len(out['course']['resolved_ids']) == 10
    course['days'][0]['slots'][0]['content_id'] = '없는곳'
    out = update(state)
    assert any(v['rule'] == 'unknown_place' for v in out['removed'])
