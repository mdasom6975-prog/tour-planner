"""eval/metrics.py 를 손으로 계산한 값과 대조한다."""
import math

import pytest

from eval.metrics import ndcg_at_k, recall_at_k, unjudged_at_k

ANSWERS = [{"id": "A", "grade": 2}, {"id": "B", "grade": 1}, {"id": "C", "grade": 1}]


def test_손으로_계산한_예시():
    results = ["X", "A", "C", "Y"]
    assert recall_at_k(results, ANSWERS) == pytest.approx(2 / 3)
    # 실제: 2위 A 는 2/log2(3), 3위 C 는 1/log2(4). 이상: A, B, C 순서.
    dcg = 2 / math.log2(3) + 1 / 2
    ideal = 2 + 1 / math.log2(3) + 1 / 2
    assert ndcg_at_k(results, ANSWERS) == pytest.approx(dcg / ideal)
    assert ndcg_at_k(results, ANSWERS) == pytest.approx(0.563, abs=0.001)


def test_가장_좋은_순서는_1점():
    assert recall_at_k(["A", "B", "C"], ANSWERS) == 1.0
    assert ndcg_at_k(["A", "B", "C"], ANSWERS) == pytest.approx(1.0)
    assert ndcg_at_k(["A", "C", "B"], ANSWERS) == pytest.approx(1.0)   # 같은 등급끼리는 순서를 바꿔도 같다


def test_2점이_뒤에_있으면_깎인다():
    assert recall_at_k(["B", "C", "A"], ANSWERS) == 1.0
    assert ndcg_at_k(["B", "C", "A"], ANSWERS) < 1.0


def test_빈_결과와_모두_틀린_결과는_0점():
    assert recall_at_k([], ANSWERS) == 0.0
    assert ndcg_at_k([], ANSWERS) == 0.0
    assert ndcg_at_k(["X", "Y"], ANSWERS) == 0.0


def test_정답_없는_질문은_None():
    assert recall_at_k(["X"], []) is None
    assert ndcg_at_k(["X"], []) is None


def test_정답이_k보다_많으면_분모는_k():
    many = [{"id": f"p{i}", "grade": 2} for i in range(62)]
    top10 = [f"p{i}" for i in range(10)]
    assert recall_at_k(top10, many) == 1.0
    assert ndcg_at_k(top10, many) == pytest.approx(1.0)
    assert recall_at_k(top10[:5] + ["X"] * 5, many) == 0.5


def test_k_밖의_정답은_세지_않는다():
    results = ["X"] * 10 + ["A"]
    assert recall_at_k(results, ANSWERS) == 0.0
    assert recall_at_k(results, ANSWERS, k=11) == pytest.approx(1 / 3)


def test_같은_곳이_두_번_나와도_한_번만():
    assert recall_at_k(["A", "A"], ANSWERS) == pytest.approx(1 / 3)
    assert ndcg_at_k(["A", "A"], ANSWERS) == ndcg_at_k(["A", "X"], ANSWERS)


def test_판정하지_않은_곳_세기():
    assert unjudged_at_k(["A", "X", "Y"], {"A", "X"}) == 1
    assert unjudged_at_k(["X"] * 10 + ["Z"], {"X"}) == 0   # 11위는 보지 않는다
