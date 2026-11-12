"""검색 결과를 정답 칸과 대조해 점수를 낸다. 검색기를 돌리는 일(3-4)은 여기 없다. (PRD 14번 3단계 중 3-3)

result_ids 는 검색기가 돌려준 장소 ID 를 순위대로 적은 목록, answers 는 retrieval_set.jsonl 의 정답 칸 [{"id", "grade"}] 이다.
정답이 없는 질문(answers 가 빈 목록)은 나눌 수가 0 이라 None 을 돌려준다. 평균에서 빼는 것은 부르는 쪽이 한다.
"""
import math

import config


def _grades(answers: list) -> dict:
    return {a["id"]: a["grade"] for a in answers}


def recall_at_k(result_ids: list, answers: list, k: int | None = None) -> float | None:
    """정답(1점 이상) 가운데 상위 k 곳 안에서 찾은 비율."""
    # 왜: "정답을 놓치지 않았는가" 를 본다. 정답이 k 곳보다 많으면 다 찾을 수 없으므로 분모를 k 로 막는다. 어디: 3-4 기준선 표, 3-5 설정 비교.
    # 교안: RAG 실습1 Q2 의 Recall@k. 분모를 min(정답 수, k) 로 막는 것은 교안에 없는 변형이다.
    k = config.EVAL_K if k is None else k
    grades = _grades(answers)
    if not grades:
        return None
    found = len({pid for pid in result_ids[:k] if pid in grades})
    return found / min(len(grades), k)


def _dcg(gains: list) -> float:
    # 순위가 내려갈수록 덜 쳐 준다: 1위는 그대로, 2위는 1.585 로, 3위는 2 로 나눈다.
    return sum(g / math.log2(rank + 1) for rank, g in enumerate(gains, start=1))


def ndcg_at_k(result_ids: list, answers: list, k: int | None = None) -> float | None:
    """정답을 얼마나 위쪽에, 2점을 1점보다 앞에 놓았는지. 가장 좋은 순서일 때 1.0."""
    # 왜: Recall 은 10위 안이면 1위든 10위든 같게 친다. 순위와 등급(2점 · 1점)을 함께 보려고 쓴다. 어디: 3-4, 3-5.
    # 교안: RAG 실습1 Q2 의 nDCG@k. 교안은 정답이 0/1 이고 여기는 0/1/2 등급을 그대로 이득으로 쓴다.
    k = config.EVAL_K if k is None else k
    grades = _grades(answers)
    if not grades:
        return None
    seen, gains = set(), []
    for pid in result_ids[:k]:
        gains.append(0 if pid in seen else grades.get(pid, 0))   # 같은 곳이 두 번 나오면 한 번만 쳐 준다
        seen.add(pid)
    ideal = sorted(grades.values(), reverse=True)[:k]
    return _dcg(gains) / _dcg(ideal)


def unjudged_at_k(result_ids: list, judged_ids, k: int | None = None) -> int:
    """상위 k 곳 가운데 판정한 적이 없는 곳의 수. 점수가 아니라 경고다."""
    # 왜: 판정하지 않은 곳은 0점으로 계산된다. 설정을 바꿔 새 장소가 올라오면 점수가 실제보다 낮게 나오므로 그 수를 따로 센다. 어디: 3-5.
    # 교안: 직접 대응 없음. 3-2a 풀링의 한계(네 검색기가 고른 곳만 판정함)를 숫자로 드러내는 장치다.
    k = config.EVAL_K if k is None else k
    judged = set(judged_ids)
    return sum(1 for pid in result_ids[:k] if pid not in judged)
