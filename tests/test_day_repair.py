"""하루 거리 보정은 모든 칸·제약을 지키는 완성된 경로만 적용한다."""
from copy import deepcopy

import config
from graph.validate import repair_day_distance, validate_update, find_violations, _legs
from harness.trace import Trace
from tests.test_validate import D1, D2, place, one_day, live


def case():
    rows = [place('s0', 'sight', '관광지', lon=129.0), place('f0', 'food', '음식점', lon=129.01),
            place('s1', 'sight', '관광지', lon=129.02), place('s2', 'sight', '관광지', lon=129.03),
            place('far', 'food', '음식점', lon=129.30), place('near', 'food', '음식점', lon=129.04)]
    return one_day(['s0', 'f0', 's1', 's2', 'far']), {c['id']: c for c in rows}


def repair(course, cands, rechecked=None, table=None):
    return repair_day_distance(course, cands, [d['date'] for d in course['days']], rechecked or {},
                               '부산', config.COURSE_SLOTS, [], table)


def test_compact_complete_course_preserves_input_and_minimizes_changes():
    course, cands = case()
    saved = deepcopy(course)
    out, changed = repair(course, cands)
    assert course == saved
    assert len(out['days'][0]['slots']) == 5
    assert len(changed) == 1 and changed[0]['id'] == 'near'
    assert find_violations(out, cands, [D1], {}, '부산') == []
    assert _legs(out['days'][0]['slots'], cands)[0] <= config.MAX_DAY_KM_BY_REGION['부산']


def test_no_solution_keeps_original_and_distance_warning():
    course, cands = case()
    del cands['near']
    out, changed = repair(course, cands)
    assert out == course and changed == []
    assert any(v['rule'] == 'day_distance' for v in find_violations(out, cands, [D1], {}, '부산'))


def test_closed_or_withdrawn_or_excluded_candidate_is_not_selected():
    course, cands = case()
    assert repair(course, cands, table={'near': {D1: 'closed'}})[1] == []
    assert repair(course, cands, rechecked={'near': live(withdrawn=True)})[1] == []
    assert repair(course, cands, rechecked={'near': live(status='weekly', weekdays=['토'])})[1] == []
    out, changed = repair_day_distance(course, cands, [D1], {}, '부산', config.COURSE_SLOTS, [cands['near']['title']])
    assert changed == []


def test_other_day_and_optional_recommendations_reserve_places():
    course, cands = case()
    course['cafes'] = [{'content_id': 'near', 'reason': 'r'}]
    assert repair(course, cands)[1] == []
    course.pop('cafes')
    course['days'].append({'date': D2, 'slots': [{'slot': '점심', 'content_id': 'near', 'reason': 'r'}]})
    assert repair(course, cands)[1] == []


def state_for(course, cands, mode='new', draft=3):
    return {'course': course, 'candidates': list(cands.values()), 'rechecked': {cid: live() for cid in cands if cid != 'near'},
            'request': {'region': '부산', 'start_date': D1, 'days': 1}, 'mode': mode, 'retries': {'draft': draft}}


def test_edit_and_not_exhausted_do_not_replace_for_day_distance():
    course, cands = case()
    for mode, draft in [('edit', 3), ('new', 1)]:
        out = validate_update({}, None, Trace(save=False))(state_for(course, cands, mode, draft))
        assert not out['replaced']
        assert any(v['rule'] == 'day_distance' for v in out['violations'])


def test_live_recheck_accepts_open_and_rejects_closed_substitute():
    course, cands = case()
    called = []
    def detail(cid):
        called.append(cid)
        return {'ok': True, **live()}
    out = validate_update({}, detail, Trace(save=False))(state_for(course, cands))
    assert called == ['near'] and out['violations'] == [] and len(out['course']['days'][0]['slots']) == 5
    def closed(cid):
        return {'ok': True, **live(status='weekly', weekdays=['토'])}
    out = validate_update({}, closed, Trace(save=False))(state_for(course, cands))
    assert not out['replaced'] and not out.get('removed')
    assert any(v['rule'] == 'day_distance' for v in out['violations'])


def test_compliant_course_is_unchanged_and_unknown_coordinates_cannot_fill_gap():
    course, cands = case()
    course['days'][0]['slots'][-1]['content_id'] = 'near'
    out, changed = repair(course, cands)
    assert out is course and changed == []
    course['days'][0]['slots'][-1]['content_id'] = 'far'
    cands['near'].pop('lat')
    assert repair(course, cands)[1] == []


def test_incomplete_course_is_not_silently_filled():
    course, cands = case()
    course['days'][0]['slots'].pop(2)
    out, changed = repair(course, cands)
    assert out is course and changed == []
