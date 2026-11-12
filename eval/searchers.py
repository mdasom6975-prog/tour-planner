"""평가용 데이터로 검색기 네 가지를 조립한다. 후보 모으기(build_pool)와 채점(retrieval_eval)이 같이 쓴다."""
from pathlib import Path

import config
from rag.bm25 import Bm25Index
from rag.dense import DenseIndex
from rag.hybrid import HybridIndex
from rag.rerank import Reranker

ROOT = Path(__file__).resolve().parent.parent


def make_searchers(places: list, encoder=None, scorer=None) -> tuple:
    """({"bm25" · "dense" · "hybrid" · "rerank": search(query, k, region, today)}, dense) 를 돌려준다."""
    # 왜: Retriever 를 쓰지 않고 네 검색기를 직접 조립한다. 단계별 결과가 따로 필요하고, 벡터 폴더를 평가용으로 바꿔야 실제 색인을 건드리지 않는다. 어디: eval/ 전체.
    # 교안: RAG 실습1 Q7 — BM25 / Dense / Hybrid / +Rerank 네 가지를 같은 질문으로 돌려 비교하던 구성.
    bm25 = Bm25Index(places)
    dense = DenseIndex(places, index_dir=ROOT / config.EVAL_INDEX_DIR, encoder=encoder)
    hybrid = HybridIndex(bm25, dense)
    reranker = Reranker(hybrid, places, scorer=scorer)
    searchers = {
        "bm25": lambda q, k, **kw: bm25.search(q, k=k, **kw),
        "dense": lambda q, k, **kw: dense.search(q, k=k, **kw),
        "hybrid": lambda q, k, **kw: hybrid.search(q, k=k, **kw),
        "rerank": lambda q, k, **kw: reranker.search(q, k=k, enabled=True, **kw),
    }
    return searchers, dense
