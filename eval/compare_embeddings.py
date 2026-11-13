"""임베딩 모델을 바꿔 끼워 같은 질문으로 잰다. config 의 EMBED_MODEL 은 바꾸지 않는다. (PRD 14번 3단계 중 3-5b)

실행:  python -m eval.compare_embeddings     (고름용 20건. 평가용 본문과 질문이 OpenAI API 로 나간다)
결과는 runs/retrieval/embeddings_고름.json 에 저장한다(git 밖).
"""
import json
import time
from pathlib import Path

import config
from eval.metrics import ndcg_at_k, recall_at_k, unjudged_at_k
from eval.openai_encoder import load_openai_encoder
from eval.retrieval_eval import OUT_DIR, SET_PATH, _judged_ids, _mean, _read
from eval.searchers import make_searchers
from rag.rerank import load_scorer

ROOT = Path(__file__).resolve().parent.parent
STAGES = ("dense", "hybrid", "rerank")
EPS = 1e-9


def run(k: int | None = None, alt_encoder=None, scorer=None) -> dict:
    """성공: {"ok": True, "table", "usage", "index", "unjudged_places", "questions"} / 실패: {"ok": False, "reason"}"""
    places_path = ROOT / config.EVAL_PLACES
    if not SET_PATH.exists() or not places_path.exists():
        return {"ok": False, "reason": f"파일이 없습니다: {SET_PATH.name} 또는 {config.EVAL_PLACES}"}
    k = config.EVAL_K if k is None else k
    questions = [q for q in _read(SET_PATH) if q["split"] == "고름"]
    places = _read(places_path)
    judged = _judged_ids()
    scorer = scorer or load_scorer(config.RERANK_MODEL)   # 재정렬 모델은 두 쪽이 같이 쓴다. 달라지는 것은 임베딩뿐이다.

    usage = {"tokens": 0, "requests": 0}
    try:
        if alt_encoder is None:
            alt_encoder, usage = load_openai_encoder(config.EVAL_EMBED_ALT, cache_path=ROOT / config.EVAL_INDEX_DIR / f"queries_{config.EVAL_EMBED_ALT}.json")
        models = {
            config.EMBED_MODEL: make_searchers(places, scorer=scorer),
            config.EVAL_EMBED_ALT: make_searchers(places, encoder=alt_encoder, scorer=scorer, model_name=config.EVAL_EMBED_ALT),
        }
    except Exception as e:   # 키 오류 · 네트워크 오류. 오류 문장에 키 일부가 섞일 수 있어 종류 이름만 남긴다.
        return {"ok": False, "reason": f"임베딩 준비 실패: {type(e).__name__}"}
    index = {name: dense.stats for name, (_, dense) in models.items()}
    doc_tokens = usage["tokens"]

    rows, failed, missing = [], [], {}
    for q in questions:
        row = {"id": q["id"], "query": q["query"], "kind": q["kind"], "by": {}}
        for model, (searchers, _) in models.items():
            for stage in STAGES:
                name = f"{model} · {stage}"
                started = time.perf_counter()
                try:
                    r = searchers[stage](q["query"], k, region=q["region"], today=q["today"])
                except Exception as e:
                    r = {"ok": False, "reason": type(e).__name__}
                ms = round((time.perf_counter() - started) * 1000, 1)
                if not r["ok"]:
                    failed.append({"qid": q["id"], "row": name, "reason": r["reason"]})
                    row["by"][name] = {"ok": False, "ms": ms}
                    continue
                ids = [item["id"] for item in r["results"]]
                # 왜: 정답은 지금 모델이 고른 곳만 보고 매겼다. 다른 모델이 올린 낯선 곳은 0점이 되어 불리하므로 모아서 추가 판정한다. 어디: 미판정 세기.
                # 교안: 직접 대응 없음. 3-5a 와 같은 절차다.
                unjudged = 0
                if not q.get("rule") and q["answers"]:
                    done = judged.get(q["id"], set())
                    unjudged = unjudged_at_k(ids, done, k)
                    for item in r["results"]:
                        if item["id"] not in done:
                            missing[(q["id"], item["id"])] = item["title"]
                row["by"][name] = {"ok": True, "recall": recall_at_k(ids, q["answers"], k), "ndcg": ndcg_at_k(ids, q["answers"], k),
                                   "unjudged": unjudged, "ms": ms, "top": ids}
        rows.append(row)

    # 왜: 같은 단계끼리 견준다(임베딩 단독은 임베딩 단독과). 평균과 함께 좋아진 · 나빠진 질문 수를 센다. 어디: 표.
    # 교안: RAG 실습1 Q7 의 비교표에 모델 축을 하나 더한 것. 바꿀 기준은 3-5a 와 같이 결과를 보기 전에 정했다.
    table = {}
    for model in models:
        for stage in STAGES:
            name, base_name = f"{model} · {stage}", f"{config.EMBED_MODEL} · {stage}"
            cells = [(row["by"][name], row["by"][base_name]) for row in rows
                     if row["by"][name]["ok"] and row["by"][base_name]["ok"] and row["by"][name]["ndcg"] is not None]
            table[name] = {"n": len(cells), "recall": _mean([c["recall"] for c, _ in cells]), "ndcg": _mean([c["ndcg"] for c, _ in cells]),
                           "ms": _mean([row["by"][name]["ms"] for row in rows]),
                           "better": sum(c["ndcg"] > b["ndcg"] + EPS for c, b in cells),
                           "worse": sum(c["ndcg"] < b["ndcg"] - EPS for c, b in cells),
                           "unjudged": sum(c["unjudged"] for c, _ in cells)}
    result = {"ok": True, "k": k, "table": table, "failed": failed, "index": index,
              "usage": {"doc_tokens": doc_tokens, "query_tokens": usage["tokens"] - doc_tokens, "requests": usage["requests"]},
              "unjudged_places": [{"qid": qid, "place_id": pid, "title": title} for (qid, pid), title in sorted(missing.items())],
              "questions": rows}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "embeddings_고름.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    result["path"] = str(out_path)
    return result


if __name__ == "__main__":
    res = run()
    if not res["ok"]:
        print(res["reason"])
        raise SystemExit(1)
    print(f"실패 {len(res['failed'])}건 · 판정하지 않은 곳 {len(res['unjudged_places'])}곳 · 토큰 {res['usage']} · 색인 {res['index']}")
    for name, s in res["table"].items():
        print(f"{name:40s} n={s['n']:2d}  Recall {s['recall']:.3f}  nDCG {s['ndcg']:.3f}  {s['ms']:7.1f}ms  좋아짐 {s['better']:2d} 나빠짐 {s['worse']:2d}  미판정 {s['unjudged']}")
    print("저장:", res["path"])
