"""검색 창구. BM25 → 임베딩 → 합치기 → 재정렬을 조립해 search 하나로 내놓는다. (PRD 14번 2단계 중 2-5a)

화면 연결(2-5b) · 도구로 감싸기(4단계) · 점수로 "찾지 못했습니다" 판단(5단계)은 여기 없다.
"""
import json
import time
from pathlib import Path

from rag.bm25 import PLACES_PATH, Bm25Index
from rag.dense import DenseIndex
from rag.hybrid import HybridIndex
from rag.rerank import Reranker


class Retriever:
    def __init__(self, places: list, encoder=None, scorer=None):
        # 왜: 화면 · 도구 · 평가가 검색기 네 개를 각자 조립하면 설정이 어긋난다. 조립을 한 곳에 두고 장소 목록도 한 번만 읽어 나눠 쓴다. 어디: 생성자.
        # 교안: RAG 실습1 Q7 — BM25 · 임베딩 · RRF · 재정렬을 겹쳐 하나의 retriever 로 쓰던 구조.
        started = time.perf_counter()
        self.places = places
        self.bm25 = Bm25Index(places)
        self.dense = DenseIndex(places, encoder=encoder)
        self.hybrid = HybridIndex(self.bm25, self.dense)
        self.reranker = Reranker(self.hybrid, places, scorer=scorer)
        # 준비에 걸린 시간과 새로 계산한 벡터 수. 화면과 평가가 "왜 느렸는지" 를 볼 때 쓴다.
        self.stats = {"places": len(places), "bm25_build_sec": self.bm25.build_sec,
                      "dense": self.dense.stats, "build_sec": round(time.perf_counter() - started, 2)}

    @classmethod
    def from_file(cls, path: Path = PLACES_PATH, **kwargs) -> "Retriever":
        with Path(path).open(encoding="utf-8") as f:
            return cls([json.loads(line) for line in f if line.strip()], **kwargs)

    def search(self, query: str, k: int | None = None, region: str | None = None, types: list | None = None,
               today: str | None = None, trace=None, rerank: bool | None = None) -> dict:
        """성공: {"ok": True, "results": [...], "took_ms", "reranked", ...} / 실패: {"ok": False, "reason"}"""
        # 왜: 바깥에서는 이 함수만 부른다. k 와 재정렬 여부를 비워 두면 config 값을 쓰므로 호출하는 쪽에 숫자가 흩어지지 않는다. 어디: 검색 입구.
        # 교안: 4일차 PRD "도구는 한 가지 일만, 실패도 결과로" — 아래 검색기가 준 {"ok": False, "reason"} 을 그대로 올려 보낸다.
        return self.reranker.search(query, k=k, region=region, types=types, today=today, trace=trace, enabled=rerank)
