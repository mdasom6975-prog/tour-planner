"""BM25 키워드 검색기. 질문과 본문에 같은 낱말이 얼마나 겹치는지로 순위를 매긴다. (PRD 14번 2단계 중 2-1)

임베딩 검색 · 합치기 · 재정렬 · 실행 기록은 여기 없다.
"""
import json
import time
from pathlib import Path

from kiwipiepy import Kiwi
from rank_bm25 import BM25Okapi

import config

PLACES_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "places.jsonl"

# 왜: 조사 · 어미는 모든 문서에 나와 검색에 도움이 안 된다. 뜻을 가진 품사만 남긴다. 어디: tokenize.
# 교안: RAG 실습1 Q3 — Kiwi 형태소 분석으로 명사 · 용언 어간만 뽑아 BM25 에 넣던 토크나이저.
KEEP_ANY_LENGTH = {"NNG", "NNP", "SL", "SN", "SH", "XR"}  # 일반명사 · 고유명사 · 외국어 · 숫자 · 한자 · 어근
KEEP_IF_LONG = {"VV", "VA"}                               # 동사 · 형용사 어간은 두 글자 이상만 ("오", "가", "있" 은 잡음)

_kiwi = None


def tokenize(text: str) -> list:
    # 왜: Kiwi 를 불러오는 데 1초쯤 걸려, 처음 쓸 때 한 번만 만든다. 어디: 색인 만들기와 질문 분석 양쪽.
    # 교안: 직접 대응 없음 (지연 초기화). 문서와 질문을 "같은 방식" 으로 나눠야 낱말이 맞는다는 점은 실습1 Q3.
    global _kiwi
    if _kiwi is None:
        _kiwi = Kiwi()
    tokens = []
    for t in _kiwi.tokenize(text or ""):
        if t.tag in KEEP_ANY_LENGTH or (t.tag in KEEP_IF_LONG and len(t.form) > 1):
            tokens.append(t.form.lower())
    return tokens


class Bm25Index:
    def __init__(self, places: list):
        # 왜: 색인은 저장하지 않고 시작할 때 만든다. 저장하면 "데이터는 바뀌었는데 색인은 옛것" 이 될 수 있다. 어디: 생성자.
        # 교안: RAG 실습1 Q3 — BM25Okapi(낱말 목록들) 로 색인을 만드는 부분.
        started = time.perf_counter()
        self.places = places
        self.tokens = [tokenize(p["search_text"]) for p in places]
        self.bm25 = BM25Okapi(self.tokens)
        self.build_sec = round(time.perf_counter() - started, 2)

    @classmethod
    def from_file(cls, path: Path = PLACES_PATH) -> "Bm25Index":
        with Path(path).open(encoding="utf-8") as f:
            return cls([json.loads(line) for line in f if line.strip()])

    def search(self, query: str, k: int = 10, region: str | None = None, types: list | None = None) -> dict:
        """성공: {"ok": True, "results": [...], "took_ms"} / 실패: {"ok": False, "reason"}"""
        started = time.perf_counter()

        # 왜: 없는 지역 · 유형으로 찾으면 "결과 없음" 과 "잘못된 조건" 을 구분할 수 없다. 어디: 입력 검사.
        # 교안: 3일차 Part2 "에러도 결과로" / 4일차 PRD F1 "지원하지 않는 지역이면 지어내지 않고 안내".
        if region is not None and region not in config.REGIONS:
            return {"ok": False, "reason": f"지원하지 않는 지역: {region}. 가능: {list(config.REGIONS)}"}
        known_types = set(config.DETAIL_TYPES.values())
        if types and not set(types) <= known_types:
            return {"ok": False, "reason": f"지원하지 않는 유형: {sorted(set(types) - known_types)}. 가능: {sorted(known_types)}"}

        q_tokens = tokenize(query)
        if not q_tokens:
            return {"ok": False, "reason": "질문에서 검색할 낱말을 찾지 못했습니다"}

        scores = self.bm25.get_scores(q_tokens)

        # 왜: 지역 · 유형은 점수가 아니라 조건이다. "강릉" 이 본문에 여러 번 나온 부산 식당이 올라오면 안 된다. 어디: 점수 뒤 거르기.
        # 교안: PRD F2 "메타데이터 필터". RAG 실습1 에는 없던 부분으로, 장소 데이터라서 필요하다.
        ranked = []
        for i, place in enumerate(self.places):
            if scores[i] <= 0:
                continue
            if region is not None and place["region"] != region:
                continue
            if types and place["type"] not in types:
                continue
            ranked.append((float(scores[i]), i))
        ranked.sort(reverse=True)

        results = []
        for score, i in ranked[:k]:
            p = self.places[i]
            results.append({
                "id": p["id"],
                "title": p["title"],
                "type": p["type"],
                "region": p["region"],
                "score": round(score, 3),
                "snippet": p["overview"][:80],
            })
        return {
            "ok": True,
            "results": results,
            "query_tokens": q_tokens,
            "took_ms": round((time.perf_counter() - started) * 1000, 2),
        }
