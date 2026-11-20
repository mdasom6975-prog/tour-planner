"""제안 기준의 경계·비교 재현성·기존 정책 보존을 검증한다."""
from copy import deepcopy
import hashlib
import json

import pytest

import config
from harness.distance_policy import assess_day, compare
from tests.test_regression import fixture


@pytest.mark.parametrize('region', ['서울', '부산', '강릉', '제주'])
@pytest.mark.parametrize('mode', ['transit', 'car', 'walk'])
def test_recommended_and_maximum_boundaries(region, mode):
    policy = assess_day(region, mode, 0)
    recommended, maximum = policy['recommended_km'], policy['max_km']
    assert assess_day(region, mode, recommended)['status'] == 'recommended'
    assert assess_day(region, mode, recommended + .01)['status'] == 'long_day'
    assert assess_day(region, mode, maximum)['status'] == 'long_day'
    assert assess_day(region, mode, maximum + .01)['status'] == 'exceeds_max'


@pytest.mark.parametrize('km', [None, float('nan'), float('inf'), -1])
def test_missing_or_invalid_distance_is_not_passed(km):
    assert assess_day('부산', 'transit', km)['status'] == 'unknown'


def test_unsupported_region_or_unspecified_transport_does_not_get_a_guessed_mode():
    assert assess_day('부산', None, 23.11)['status'] == 'unknown'
    assert assess_day('부산', 'taxi', 23.11)['status'] == 'unknown'
    assert assess_day('전북', 'car', 23.11)['status'] == 'unknown'


def test_same_distance_is_classified_by_transport_and_can_be_stricter_than_legacy():
    assert assess_day('부산', 'transit', 23.11)['status'] == 'recommended'
    assert assess_day('부산', 'transit', 42.29)['status'] == 'exceeds_max'
    assert assess_day('부산', 'car', 42.29)['status'] == 'long_day'
    assert assess_day('제주', 'transit', config.MAX_DAY_KM_BY_REGION['제주'])['status'] == 'exceeds_max'


def test_comparison_preserves_snapshots_and_runtime_limits(tmp_path):
    f = fixture()
    data = (json.dumps(f, ensure_ascii=False) + '\n').encode()
    (tmp_path/'case.json').write_bytes(data)
    manifest = {'version': 1, 'cases': [{'id': f['id'], 'file': 'case.json', 'sha256': hashlib.sha256(data).hexdigest()}]}
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    before = deepcopy(config.MAX_DAY_KM_BY_REGION)
    result = compare(tmp_path, tmp_path/'output')
    assert result['baseline']['PASS'] == 1
    assert result['runtime_policy_changed'] is False
    assert len(result['rows']) == 4
    assert config.MAX_DAY_KM_BY_REGION == before
    assert (tmp_path/'case.json').read_bytes() == data
    assert (tmp_path/'output/distance-comparison.md').exists()
