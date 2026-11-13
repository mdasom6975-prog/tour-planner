"""BM25 와 임베딩 검색 결과를 순위로 합친다 (RRF). (PRD 14번 2단계 중 2-3)

가중치 고르기(3단계 평가) · 재정렬(2-4)은 여기 없다.
"""
import time

import config


def rrf(rankings: list, weights: list, k: int = 60) -> list:
    """순위 목록 여러 개를 하나로 합친다. rankings: [[id, …], [id, …]] → 합친 id 목록"""
    # 왜: 두 검색기의 점수는 단위가 달라(BM25 10.2 대 임베딩 0.44) 더할 수 없다. 순위는 어느 쪽이든 1 · 2 · 3위라 공평하게 더할 수 있다. 어디: 합치기.
    # 교안: RAG 실습1 Q6 의 식 그대로 — score(d) = Σ w_i / (k + rank_i(d)), k = 60.
    return [doc for doc, _ in _rrf_scores(rankings, weights, k)]


def _rrf_scores(rankings: list, weights: list, k: int) -> list:
    scores = {}
    for ranking, weight in zip(rankings, weights):
        for rank, doc in enumerate(ranking, start=1):
            scores[doc] = scores.get(doc, 0.0) + weight / (k + rank)
    # 점수가 같으면 먼저 나온 순서를 지킨다 (dict 는 넣은 순서를 기억하고 정렬은 순서를 보존한다).
    return sorted(scores.items(), key=lambda item: -item[1])


class HybridIndex:
    def __init__(self, bm25, dense):
        # 왜: 두 검색기를 받아 쓰기만 한다. 색인을 만드는 일은 각자의 몫이다. 어디: 생성자.
        # 교안: 3일차 Part2 "도구는 한 가지 일만". 검색기를 인자로 받으므로 테스트에서 가짜 검색기로 바꿀 수 있다.
        self.bm25 = bm25
        self.dense = dense

    def search(self, query: str, k: int = 10, region: str | None = None, types: list | None = None,
               today: str | None = None, trace=None, w_dense: float | None = None,
               area: str | None = None) -> dict:
        """성공: {"ok": True, "results": [...], "took_ms"} / 실패: {"ok": False, "reason"}  (BM25 · 임베딩과 같은 모양)"""
        started = time.perf_counter()
        w_dense = config.HYBRID_W_DENSE if w_dense is None else w_dense
        depth = config.RETRIEVE_K

        # 두 검색기에 실행 기록 장치를 그대로 넘긴다. 기록은 search_bm25 → search_dense → fuse_rrf 세 줄이 된다.
        b = self.bm25.search(query, k=depth, region=region, types=types, today=today, trace=trace, area=area)
        d = self.dense.search(query, k=depth, region=region, types=types, today=today, trace=trace, area=area)

        # 왜: 조건 오류(지원하지 않는 지역 등)는 두 검색기가 같은 판정을 하므로 그대로 돌려준다. 어디: 실패 처리.
        # 교안: 3일차 Part2 "에러도 결과로".
        if not d["ok"]:
            return {"ok": False, "reason": d["reason"]}

        # BM25 만 실패하는 경우는 질문에서 낱말을 못 뽑았을 때다. 임베딩 결과만으로 답하고 그 사실을 남긴다.
        note = None
        if not b["ok"]:
            b_results, note = [], f"BM25 를 쓰지 못해 임베딩 결과만 사용: {b['reason']}"
        else:
            b_results = b["results"]

        b_rank = {r["id"]: n for n, r in enumerate(b_results, start=1)}
        d_rank = {r["id"]: n for n, r in enumerate(d["results"], start=1)}
        info = {r["id"]: r for r in d["results"]}
        info.update({r["id"]: r for r in b_results})

        fused = _rrf_scores([list(b_rank), list(d_rank)], [1 - w_dense, w_dense], config.RRF_K)

        # 왜: 어느 검색기가 몇 위로 골랐는지 남겨야 "왜 올라왔는지" 를 보고, 실패 사례에서 어느 쪽이 놓쳤는지 분석할 수 있다. 어디: 결과의 sources.
        # 교안: RAG 실습1 Q6 조건4 "어느 쪽이 왜 약한지 분석" 에 필요한 정보.
        results = []
        for doc, score in fused[:k]:
            item = dict(info[doc])
            item["score"] = round(score, 5)
            item["sources"] = {"bm25": b_rank.get(doc), "dense": d_rank.get(doc)}
            results.append(item)

        took = round((time.perf_counter() - started) * 1000, 2)
        both = len(set(b_rank) & set(d_rank))
        if trace is not None:
            trace.record("fuse_rrf", "node",
                         input={"bm25": len(b_rank), "dense": len(d_rank), "w_dense": w_dense, "rrf_k": config.RRF_K},
                         output={"count": len(results), "in_both": both, "top": [r["title"] for r in results], "note": note},
                         ok=True, took_ms=took)
        out = {"ok": True, "results": results, "took_ms": took, "in_both": both}
        if note:
            out["note"] = note
        return out
