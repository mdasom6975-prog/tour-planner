"""검색기 네 가지를 같은 질문으로 돌려 기준선 표를 만든다. 설정을 바꿔 비교하는 일(3-5)은 여기 없다. (PRD 14번 3단계 중 3-4)

실행:  python -m eval.retrieval_eval            (고름용 20건)
       python -m eval.retrieval_eval --split 확인   (설정을 정한 뒤 한 번만)
결과는 runs/retrieval/ 에 저장한다(git 밖).
"""
import argparse
import json
import time
from pathlib import Path

import config
from eval.metrics import ndcg_at_k, recall_at_k, unjudged_at_k
from eval.searchers import make_searchers

ROOT = Path(__file__).resolve().parent.parent
SET_PATH = ROOT / "eval" / "retrieval_set.jsonl"
JUDGED_PATH = ROOT / "eval" / "pool" / "judgments.jsonl"
OUT_DIR = ROOT / "runs" / "retrieval"


def _read(path: Path) -> list:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _mean(values: list):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 4) if values else None


def _judged_ids() -> dict:
    """질문별로 판정한 장소 ID(0점 포함). 판정 파일은 git 밖이라 없을 수 있다."""
    judged = {}
    if JUDGED_PATH.exists():
        for j in _read(JUDGED_PATH):
            judged.setdefault(j["qid"], set()).add(j["place_id"])
    return judged


def run(split: str = "고름", k: int | None = None, encoder=None, scorer=None) -> dict:
    """성공: {"ok": True, "summary", "by_kind", "questions", ...} / 실패: {"ok": False, "reason"}"""
    places_path = ROOT / config.EVAL_PLACES
    if not SET_PATH.exists() or not places_path.exists():
        return {"ok": False, "reason": f"파일이 없습니다: {SET_PATH.name} 또는 {config.EVAL_PLACES}"}
    k = config.EVAL_K if k is None else k
    # 왜: 확인용을 보고 설정을 고르면 그 10건에 맞춘 설정이 된다. 기본은 고름용만 돌린다. 어디: 질문 고르기.
    # 교안: 2일차 Part3 — dev 로 고치고 holdout 은 마지막에 한 번만. CLAUDE.md "평가" 의 같은 규칙.
    questions = [q for q in _read(SET_PATH) if q["split"] == split]
    if not questions:
        return {"ok": False, "reason": f"split 이 '{split}' 인 질문이 없습니다"}
    searchers, dense = make_searchers(_read(places_path), encoder=encoder, scorer=scorer)
    judged = _judged_ids()

    for search in searchers.values():   # 모델을 처음 불러오는 시간이 첫 질문에 섞이지 않게 한 번 돌려 둔다
        search("준비", k)

    rows, failed = [], []
    for q in questions:
        row = {"id": q["id"], "query": q["query"], "kind": q["kind"], "answers": len(q["answers"]), "by": {}}
        for name, search in searchers.items():
            # 왜: 사용자가 실제로 묻는 것과 같게 질문 · 지역 · 날짜만 넘긴다. 조건 질문의 rule 은 정답을 만들 때만 쓰고 검색기에는 주지 않는다. 어디: 검색 호출.
            # 교안: RAG 실습1 Q7 — 같은 질문을 네 검색기에 넣고 같은 정답표로 채점한다.
            started = time.perf_counter()
            r = search(q["query"], k, region=q["region"], today=q["today"])
            ms = round((time.perf_counter() - started) * 1000, 1)
            if not r["ok"]:
                failed.append({"qid": q["id"], "searcher": name, "reason": r["reason"]})
                row["by"][name] = {"ok": False, "reason": r["reason"], "ms": ms}
                continue
            ids = [item["id"] for item in r["results"]]
            # 조건 질문은 규칙이 모든 장소를 판정했으므로 판정하지 않은 곳이 없다. 판정 파일이 없으면 셀 수 없어 None.
            if q.get("rule") or q["answers"] == []:
                unjudged = 0
            else:
                unjudged = unjudged_at_k(ids, judged[q["id"]], k) if q["id"] in judged else None
            row["by"][name] = {"ok": True, "recall": recall_at_k(ids, q["answers"], k), "ndcg": ndcg_at_k(ids, q["answers"], k),
                               "unjudged": unjudged, "ms": ms, "top_score": r["results"][0]["score"] if r["results"] else None,
                               "top": [{"id": item["id"], "title": item["title"]} for item in r["results"]]}
        rows.append(row)

    def table(subset: list) -> dict:
        out = {}
        for name in searchers:
            cells = [row["by"][name] for row in subset if row["by"][name]["ok"]]
            scored = [c for c in cells if c["recall"] is not None]
            out[name] = {"n": len(scored), "recall": _mean([c["recall"] for c in scored]), "ndcg": _mean([c["ndcg"] for c in scored]),
                         "ms": _mean([c["ms"] for c in cells]),
                         "unjudged": None if any(c["unjudged"] is None for c in cells) else sum(c["unjudged"] for c in cells)}
        return out

    kinds = sorted({row["kind"] for row in rows if row["kind"] != "정답 없음"})
    result = {"ok": True, "split": split, "k": k, "questions_total": len(rows), "places": config.EVAL_PLACES,
              "settings": {"dense_model": dense.model_name, "rrf_k": config.RRF_K, "w_dense": config.HYBRID_W_DENSE,
                           "rerank_model": config.RERANK_MODEL, "rerank_candidates": config.RERANK_CANDIDATES},
              "summary": table(rows), "by_kind": {kind: table([row for row in rows if row["kind"] == kind]) for kind in kinds},
              "failed": failed, "questions": rows}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"baseline_{split}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    result["path"] = str(out_path)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="고름", choices=["고름", "확인"])
    args = parser.parse_args()
    res = run(split=args.split)
    if not res["ok"]:
        print(res["reason"])
        raise SystemExit(1)
    print(f"{res['split']}용 {res['questions_total']}건 · 상위 {res['k']}곳 · 실패 {len(res['failed'])}건")
    for name, s in res["summary"].items():
        print(f"{name:8s} n={s['n']:2d}  Recall {s['recall']:.3f}  nDCG {s['ndcg']:.3f}  {s['ms']:8.1f}ms  미판정 {s['unjudged']}")
    print("저장:", res["path"])
