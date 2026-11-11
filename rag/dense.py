"""임베딩 검색기. 글을 벡터로 바꿔 질문과 뜻이 가까운 장소를 찾는다. (PRD 14번 2단계 중 2-2b)

BM25 와 같은 모양의 search() 를 가진다. 합치기(2-3) · 재정렬(2-4)은 여기 없다.
"""
import hashlib
import json
import time
from pathlib import Path

import numpy as np

import config
from rag.filters import check_filters, is_visible

ROOT = Path(__file__).resolve().parent.parent
PLACES_PATH = ROOT / "data" / "processed" / "places.jsonl"
INDEX_DIR = ROOT / "data" / "index"


def load_encoder(model_name: str):
    """글 목록을 받아 길이 1 로 맞춘 벡터들을 돌려주는 함수를 만든다."""
    # 왜: 라이브러리와 모델을 불러오는 데 각각 4초쯤 걸려, 실제로 필요할 때 한 번만 불러온다. 어디: 색인을 만들 때.
    # 교안: RAG 실습1 Q4 — SentenceTransformer 로 corpus 를 임베딩하던 부분. 2-0 에서 본 대로 맥의 가속 장치(MPS)를 쓴다.
    import torch
    from sentence_transformers import SentenceTransformer

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = SentenceTransformer(model_name, device=device)

    def encode(texts: list) -> np.ndarray:
        # 벡터의 길이를 1 로 맞춰 두면 두 벡터를 곱하기만 해도 가까운 정도(코사인 유사도)가 나온다.
        return np.asarray(model.encode(texts, batch_size=16, normalize_embeddings=True, show_progress_bar=False), dtype="float32")

    return encode


def _fingerprint(text: str) -> str:
    # 왜: 본문이 바뀌었는지 알아야 그 장소만 다시 계산할 수 있다. 글 전체 대신 짧은 지문을 저장해 비교한다. 어디: 저장분 재사용 판단.
    # 교안: 직접 대응 없음. 4일차 PRD "결과 캐시" 를 "데이터는 바뀌었는데 캐시는 옛것" 이 되지 않게 만든 것.
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


class DenseIndex:
    def __init__(self, places: list, model_name: str | None = None, index_dir: Path = INDEX_DIR, encoder=None):
        # 왜: 모델과 저장 위치를 바꿔 끼울 수 있어야 평가에서 모델을 비교하고, 테스트에서 가짜 모델로 빠르게 돌린다. 어디: 생성자.
        # 교안: 4일차 PRD "가짜 날씨 데이터를 주입" — 외부 의존(여기서는 임베딩 모델)을 인자로 받는다.
        started = time.perf_counter()
        self.places = places
        self.model_name = model_name or config.EMBED_MODEL
        # 모델마다 파일을 따로 둔다. 다른 모델의 벡터가 섞이면 비교가 무의미해진다.
        self.path = Path(index_dir) / f"dense_{self.model_name.replace('/', '__')}.npz"
        self.encode = encoder or load_encoder(self.model_name)
        self.emb, self.stats = self._load_or_build()
        self.stats["build_sec"] = round(time.perf_counter() - started, 2)

    @classmethod
    def from_file(cls, path: Path = PLACES_PATH, **kwargs) -> "DenseIndex":
        with Path(path).open(encoding="utf-8") as f:
            return cls([json.loads(line) for line in f if line.strip()], **kwargs)

    def _load_or_build(self):
        # 왜: 948건을 벡터로 바꾸는 데 43.7초(9,400건이면 약 7분)가 걸려, 계산한 것은 저장하고 바뀐 장소만 다시 계산한다. 어디: 색인 준비.
        # 교안: RAG 실습1 Q4 는 매번 전체를 계산했다. 여기서는 매일 장소가 늘어나므로 저장과 부분 갱신이 필요하다.
        stored = {}
        if self.path.exists():
            data = np.load(self.path, allow_pickle=False)
            if str(data["model"]) == self.model_name:
                stored = {i: (h, row) for i, h, row in zip(data["ids"].tolist(), data["hashes"].tolist(), data["emb"])}

        hashes = [_fingerprint(p["search_text"]) for p in self.places]
        rows = [None] * len(self.places)
        todo = []
        for n, (place, h) in enumerate(zip(self.places, hashes)):
            old = stored.get(place["id"])
            if old is not None and old[0] == h:
                rows[n] = old[1]
            else:
                todo.append(n)

        if todo:
            new = self.encode([self.places[n]["search_text"] for n in todo])
            for n, vec in zip(todo, new):
                rows[n] = vec
        emb = np.vstack(rows).astype("float32") if rows else np.zeros((0, 1), dtype="float32")

        current_ids = {p["id"] for p in self.places}
        removed = len([i for i in stored if i not in current_ids])
        stats = {"docs": len(self.places), "reused": len(self.places) - len(todo), "computed": len(todo), "removed": removed}

        # 바뀐 것이 있을 때만 다시 저장한다. 사라진 장소의 벡터는 여기서 빠진다.
        if todo or removed or not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            np.savez(self.path, model=np.array(self.model_name), ids=np.array([p["id"] for p in self.places]),
                     hashes=np.array(hashes), emb=emb)
        return emb, stats

    def search(self, query: str, k: int = 10, region: str | None = None, types: list | None = None,
               today: str | None = None, trace=None) -> dict:
        """성공: {"ok": True, "results": [...], "took_ms"} / 실패: {"ok": False, "reason"}  (BM25 와 같은 모양)"""
        started = time.perf_counter()
        result = self._search(query, k, region, types, today)
        result["took_ms"] = round((time.perf_counter() - started) * 1000, 2)

        # 왜: 검색 1회가 실행 기록 1줄이 된다. BM25 와 같은 형식으로 남겨 화면과 평가가 두 검색을 같은 방식으로 읽는다. 어디: 검색 끝.
        # 교안: PRD 12-1 실행 기록 (2-a 에서 정한 형식).
        if trace is not None:
            output = {"count": len(result["results"]), "top": [r["title"] for r in result["results"]]} if result["ok"] else {"reason": result["reason"]}
            trace.record("search_dense", "tool",
                         input={"query": query, "k": k, "region": region, "types": types, "today": today, "model": self.model_name},
                         output=output, ok=result["ok"], took_ms=result["took_ms"])
        return result

    def _search(self, query: str, k: int, region: str | None, types: list | None, today: str | None) -> dict:
        problem = check_filters(region, types)
        if problem:
            return {"ok": False, "reason": problem}
        if not (query or "").strip():
            return {"ok": False, "reason": "질문이 비어 있습니다"}

        # 왜: 질문도 같은 모델로 벡터로 바꿔야 장소 벡터와 비교할 수 있다. 전체와 비교해도 3,104건에 0.13ms 라 FAISS 없이 곱셈으로 한다. 어디: 점수 계산.
        # 교안: RAG 실습1 Q4 의 Dense 검색. FAISS 를 쓰지 않는 이유는 PRD 13번 (2-0 에서 측정).
        q = self.encode([query])[0]
        scores = self.emb @ q

        # 조건(지역 · 유형 · 끝난 행사 제외)은 BM25 와 똑같이 rag/filters.py 가 판정한다.
        results = []
        for i in np.argsort(-scores):
            place = self.places[i]
            if not is_visible(place, region, types, today):
                continue
            results.append({
                "id": place["id"],
                "title": place["title"],
                "type": place["type"],
                "region": place["region"],
                "score": round(float(scores[i]), 3),
                "snippet": place["overview"][:80],
            })
            if len(results) == k:
                break
        return {"ok": True, "results": results}
