"""재정렬. 합친 검색의 상위 후보를 질문과 함께 다시 읽어 순위를 매긴다. (PRD 14번 2단계 중 2-4)

점수로 "찾지 못했습니다" 를 판단하는 일(5단계) · 화면 연결(2-5)은 여기 없다.
"""
import time

import config


def load_scorer(model_name: str):
    """(질문, 본문) 쌍 목록을 받아 점수 목록을 돌려주는 함수를 만든다."""
    # 왜: 임베딩은 질문과 본문을 따로 벡터로 바꾸지만, 재정렬은 한 쌍으로 함께 읽어 조건에 맞는지를 더 자세히 본다. 어디: 점수 계산.
    # 교안: RAG 실습1 Q7 — sentence_transformers.CrossEncoder 를 가속 장치에 올려 쓰던 부분.
    import torch
    from sentence_transformers import CrossEncoder

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = CrossEncoder(model_name, device=device)

    def score(pairs: list) -> list:
        return [float(s) for s in model.predict(pairs, batch_size=16, show_progress_bar=False)]

    return score


class Reranker:
    def __init__(self, base, places: list, model_name: str | None = None, scorer=None):
        # 왜: 후보를 주는 검색기와 점수를 주는 모델을 받아 쓰기만 한다. 둘 다 바꿔 끼울 수 있어 가짜로 테스트할 수 있다. 어디: 생성자.
        # 교안: 4일차 PRD "가짜 날씨 데이터를 주입" — 외부 의존(여기서는 2GB 모델)을 인자로 받는다.
        self.base = base
        self.text_of = {p["id"]: p["search_text"] for p in places}
        self.model_name = model_name or config.RERANK_MODEL
        self._scorer = scorer

    def _score(self, pairs: list) -> list:
        # 재정렬을 꺼 두면 모델을 불러오지 않도록, 처음 점수를 낼 때 불러온다.
        if self._scorer is None:
            self._scorer = load_scorer(self.model_name)
        return self._scorer(pairs)

    def search(self, query: str, k: int | None = None, region: str | None = None, types: list | None = None,
               today: str | None = None, trace=None, enabled: bool | None = None,
               candidates: int | None = None, w_dense: float | None = None) -> dict:
        """성공: {"ok": True, "results": [...], "took_ms"} / 실패: {"ok": False, "reason"}  (다른 검색기와 같은 모양)"""
        started = time.perf_counter()
        k = config.RERANK_K if k is None else k
        enabled = config.RERANK_ENABLED if enabled is None else enabled
        candidates = config.RERANK_CANDIDATES if candidates is None else candidates
        # 평가(3-5)에서 설정을 바꿔 비교할 때만 값을 넘긴다. 넘기지 않으면 아래 검색기가 config 의 값을 쓴다.
        extra = {} if w_dense is None else {"w_dense": w_dense}

        # 왜: 재정렬은 느려서(30곳에 1.7초) 전체가 아니라 이미 추려진 상위 후보에만 쓴다. 어디: 후보 가져오기.
        # 교안: RAG 실습1 Q7 조건1 — Hybrid 상위 30개를 재정렬해 10개를 돌려준다.
        found = self.base.search(query, k=candidates, region=region, types=types, today=today, trace=trace, **extra)
        if not found["ok"]:
            return found
        cands = found["results"]
        for n, c in enumerate(cands, start=1):
            c["hybrid_rank"] = n

        if not enabled or not cands:
            return {"ok": True, "results": cands[:k], "took_ms": round((time.perf_counter() - started) * 1000, 2), "reranked": False}

        # 왜: 후보가 한 곳뿐이어도 점수를 낸다. 순서는 안 바뀌지만 점수가 "답이 될 만한 후보가 있는지" 를 알려 준다. 어디: 점수 계산.
        # 교안: 직접 대응 없음. 2-4a 측정에서 답이 분명한 질문은 1위 점수가 0.8 이상, 답이 없는 질문은 0.02 이하였다.
        t = time.perf_counter()
        scores = self._score([(query, self.text_of[c["id"]]) for c in cands])
        rerank_ms = round((time.perf_counter() - t) * 1000, 2)

        order = sorted(range(len(cands)), key=lambda i: -scores[i])
        results = []
        for i in order[:k]:
            item = dict(cands[i])
            item["hybrid_score"] = item["score"]
            item["score"] = round(scores[i], 4)   # 이 단계의 점수 = 재정렬 점수
            results.append(item)

        took = round((time.perf_counter() - started) * 1000, 2)
        top_score = results[0]["score"] if results else None
        # 원래 k 위 밖에 있다가 재정렬로 올라온 곳의 수. 재정렬이 무엇을 바꿨는지 보는 값이다.
        lifted = sum(r["hybrid_rank"] > k for r in results)
        if trace is not None:
            trace.record("rerank", "tool",
                         input={"query": query, "candidates": len(cands), "k": k, "model": self.model_name},
                         output={"count": len(results), "top_score": top_score, "lifted_from_below": lifted,
                                 "top": [f"{r['title']} (원래 {r['hybrid_rank']}위)" for r in results]},
                         ok=True, took_ms=rerank_ms)
        return {"ok": True, "results": results, "took_ms": took, "rerank_ms": rerank_ms,
                "top_score": top_score, "lifted_from_below": lifted, "reranked": True}
