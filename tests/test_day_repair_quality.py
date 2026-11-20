"""거리 보정과 병합된 메뉴·영업시간 검사가 함께 작동하는지 확인한다."""
from copy import deepcopy

from graph.validate import validate_update
from harness.trace import Trace
from tests.test_day_repair import case, state_for
from tests.test_validate import live, place


def run(stored_hours='00:00~24:00', live_hours=None, duplicate_menu=False, alternative=False):
    course, cands = case()
    if alternative:
        cands['alternative'] = place('alternative', 'food', '음식점', lon=129.045)
    state = state_for(course, cands)
    state['rechecked'].pop('alternative', None)
    stored = {cid: {**c, 'hours_text': '00:00~24:00'} for cid, c in cands.items()}
    stored['near']['hours_text'] = stored_hours
    if duplicate_menu:
        stored['f0']['extra'] = {'menu_main': '물회'}
        stored['near']['extra'] = {'menu_main': '물회'}
        stored['far']['extra'] = {'menu_main': '곰탕'}
    calls = []
    def detail(cid):
        calls.append(cid)
        hours = live_hours if cid == 'near' and live_hours is not None else stored[cid]['hours_text']
        return {'ok': True, **live(), 'place': {**live()['place'], 'hours_text': hours}}
    original = deepcopy(state)
    out = validate_update(stored, detail, Trace(save=False))(state)
    assert state == original
    return out, calls


def test_known_closed_restaurant_is_not_selected_to_reduce_distance():
    out, calls = run(stored_hours='10:00~11:00')
    assert not out['replaced'] and not out.get('removed')
    assert {v['rule'] for v in out['violations']} == {'day_distance'}
    assert calls == []


def test_open_alternative_is_selected_instead_of_closed_nearest():
    out, calls = run(stored_hours='10:00~11:00', alternative=True)
    assert out['violations'] == []
    assert 'alternative' in [s['content_id'] for d in out['course']['days'] for s in d['slots']]
    assert calls == ['alternative']


def test_newly_rechecked_hours_override_stored_hours_before_accepting_repair():
    out, calls = run(live_hours='10:00~11:00')
    assert calls == ['near']
    assert out['rechecked']['near']['place']['hours_text'] == '10:00~11:00'
    assert not out['replaced'] and not out.get('removed')
    assert {v['rule'] for v in out['violations']} == {'day_distance'}
    assert out['course']['days'][0]['slots'][-1]['content_id'] == 'far'


def test_duplicate_menu_is_not_introduced_to_reduce_distance():
    out, calls = run(duplicate_menu=True)
    assert not out['replaced']
    assert {v['rule'] for v in out['violations']} == {'day_distance'}
    assert calls == []
