"""글 목록을 OpenAI 임베딩 벡터로 바꾼다. 평가에서 모델을 비교할 때만 쓴다. (PRD 14번 3단계 중 3-5b)

실제 검색(rag/)은 이 파일을 모른다. 이 모델로 바꾸기로 정해지면 그때 옮긴다.
"""
import json
from pathlib import Path

import numpy as np

BATCH = 64


def load_openai_encoder(model_name: str, client=None, cache_path: Path | None = None) -> tuple:
    """(encode, usage) 를 돌려준다. encode 는 rag/dense.py 의 load_encoder 와 같은 모양, usage 는 쓴 토큰 수를 세는 dict."""
    # 왜: DenseIndex 가 벡터 계산 함수를 인자로 받으므로, 같은 모양의 함수만 만들면 검색 코드를 고치지 않고 모델을 바꿔 끼울 수 있다. 어디: eval/compare_embeddings.py.
    # 교안: RAG 실습2 — 임베딩 모델을 바꿔 같은 질문으로 비교하던 부분. 키는 config 가 .env 에서 환경 변수로 올려 둔 것을 SDK 가 읽는다.
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    usage = {"tokens": 0, "requests": 0}
    # 왜: API 가 같은 질문에도 벡터를 아주 조금 다르게 돌려줘, 다시 돌리면 10위 언저리 순위가 바뀐다(3-5b 에서 한 곳). 질문 벡터를 파일에 두어 재현되게 한다. 어디: 질문 한 건 호출.
    # 교안: 4일차 PRD "결과 캐시". 같은 질문을 임베딩 단독 · 합침 · 재정렬이 세 번 묻는 것도 한 번만 보내게 된다.
    cache = {}
    if cache_path is not None and Path(cache_path).exists():
        cache = {text: np.asarray(vec, dtype="float32") for text, vec in json.loads(Path(cache_path).read_text(encoding="utf-8")).items()}

    def encode(texts: list) -> np.ndarray:
        if len(texts) == 1 and texts[0] in cache:
            return cache[texts[0]][None, :]
        rows = []
        for start in range(0, len(texts), BATCH):
            res = client.embeddings.create(model=model_name, input=texts[start:start + BATCH])
            usage["tokens"] += res.usage.total_tokens
            usage["requests"] += 1
            rows.extend(item.embedding for item in sorted(res.data, key=lambda item: item.index))
        emb = np.asarray(rows, dtype="float32")
        emb /= np.linalg.norm(emb, axis=1, keepdims=True)   # 길이를 1 로 맞춰 곱하기만으로 코사인 유사도가 되게 한다
        if len(texts) == 1:
            cache[texts[0]] = emb[0]
            if cache_path is not None:
                Path(cache_path).write_text(json.dumps({t: v.tolist() for t, v in cache.items()}, ensure_ascii=False), encoding="utf-8")
        return emb

    return encode, usage
