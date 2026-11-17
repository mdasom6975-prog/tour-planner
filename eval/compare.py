"""한 번의 실행에서 돌린 모델들을 한 표에 놓는다. 모델을 부르지 않는다. (PRD 12-2 모델 비교표, 14번 8-5)

먼저 python -m eval.run --provider claude,openai → python -m eval.ground 를 돌린 뒤 쓴다.
실행:  python -m eval.compare                 (가장 최근 실행)
       python -m eval.compare runs/eval/20261117-143500
"""
import json
import sys
from pathlib import Path

import config
from eval.ground import summarize
from eval.score import ROOT, latest_run, score_rows


def model_row(provider: str, rows: list, places: dict, judged: list | None, meta: dict) -> dict:
    """모델 하나의 비교표 한 줄. judged 는 근거성 채점 결과(없으면 None)."""
    s = score_rows(rows, places)
    model = meta.get("models", {}).get(provider, "?")
    tokens_in = sum(t["input_tokens"] for r in rows for t in r["turns"])
    tokens_out = sum(t["output_tokens"] for r in rows for t in r["turns"])
    # 왜: 비용은 기억이 아니라 실행 기록의 토큰 수 × config 의 공식 단가로만 계산한다. 단가가 없는 모델은 빈칸으로 둔다. 어디: 비용 열.
    # 교안: 2일차 Part3 비교표. 출력 토큰에는 모델이 생각하는 데 쓴 토큰도 들어 있다.
    price = config.PRICES_PER_MTOK.get(model)
    cost = round((tokens_in * price[0] + tokens_out * price[1]) / 1_000_000, 4) if price else None
    g = summarize(judged) if judged else None
    attack = s["by_case"].get("공격", {"items": 0, "expect_ok": 0})
    return {"provider": provider, "model": model, "options": meta.get("model_options", {}).get(provider, {}),
            "items": s["count"], "expect_ok": s["expect_ok"], "by_case": s["by_case"], "attack_ok": attack["expect_ok"], "attack_items": attack["items"],
            "courses": s["courses"], "abstain": sum(1 for i in s["items"] if i["kind"] == "abstain"),
            "rule_total": s["rule_total"], "rule_violations": s["rule_violations"],
            "ground": g and {k: g[k] for k in ("sentences", "grounded", "rate", "unjudged", "pass")},
            "redrafts": sum(max(t.get("retries", {}).get("draft", 0) - 1, 0) for r in rows for t in r["turns"]),
            "research": sum(t.get("retries", {}).get("search", 0) for r in rows for t in r["turns"]),
            "removed": s["removed"], "slow": s["slow"], "course_sec_avg": s["course_sec_avg"], "course_sec_max": s["course_sec_max"],
            "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": cost,
            "cost_per_item_usd": round(cost / s["count"], 4) if cost is not None and s["count"] else None,
            "failed": [(i["id"], "; ".join(i["failures"])) for i in s["items"] if not i["expect_ok"]]}


def to_markdown(run: str, meta: dict, rows: list) -> str:
    """비교표. 지표가 줄, 모델이 칸이다. 관광공사 문장과 이유 문장은 넣지 않는다."""
    def cell(r, key):
        g = r["ground"]
        return {
            "모델": r["model"], "설정": json.dumps(r["options"], ensure_ascii=False) or "—",
            "기대 동작 일치": f"{r['expect_ok']}/{r['items']}",
            "유형별 (정상 · 경계 · 엣지 · 공격)": " · ".join(f"{v['expect_ok']}/{v['items']}" for v in r["by_case"].values()),
            "코스 규칙 위반 (합격선 0건)": f"{r['rule_total']}건 (코스 {r['courses']}건)",
            "근거성 (합격선 90%)": f"{g['grounded']}/{g['sentences']} ({g['rate'] * 100:.1f}%)" if g and g["rate"] is not None else "채점 안 함",
            "공격 문항 기대 동작": f"{r['attack_ok']}/{r['attack_items']}",
            "포기로 끝난 문항": f"{r['abstain']}건",
            "코스 재작성 · 재검색 횟수": f"{r['redrafts']}회 · {r['research']}회",
            "검증기가 뺀 장소": f"{r['removed']}곳",
            f"{config.EVAL_MAX_SEC}초 넘긴 문항": f"{r['slow']}/{r['items']}",
            "코스 평균 · 최대 시간": f"{r['course_sec_avg']}초 · {r['course_sec_max']}초",
            "토큰 (입력 · 출력)": f"{r['tokens_in']:,} · {r['tokens_out']:,}",
            "비용 (전체 · 문항당)": f"${r['cost_usd']:.2f} · ${r['cost_per_item_usd']:.4f}" if r["cost_usd"] is not None else "단가 없음",
        }[key]
    keys = ["모델", "설정", "기대 동작 일치", "유형별 (정상 · 경계 · 엣지 · 공격)", "코스 규칙 위반 (합격선 0건)", "근거성 (합격선 90%)", "공격 문항 기대 동작",
            "포기로 끝난 문항", "코스 재작성 · 재검색 횟수", "검증기가 뺀 장소", f"{config.EVAL_MAX_SEC}초 넘긴 문항", "코스 평균 · 최대 시간",
            "토큰 (입력 · 출력)", "비용 (전체 · 문항당)"]
    lines = [f"# 모델 비교 {run}", "",
             f"- 같은 평가셋({len(meta.get('items', []))}건) · 같은 데이터({meta.get('places', '?')}, {meta.get('place_count', '?')}곳) · 같은 지시문 · 고정 날씨 · 저장분만 사용. 코드 {meta.get('git', '?')}.",
             f"- 채점자 {config.JUDGE_MODEL} 고정. 단가는 {config.PRICES_CHECKED} 에 공식 가격 페이지에서 확인한 값(100만 토큰당 입력 · 출력 달러), 캐시 · 배치 할인 없음.",
             "- 두 모델은 등급이 다르다. 품질과 비용을 함께 읽는다.", "",
             "| 지표 | " + " | ".join(r["provider"] for r in rows) + " |", "| --- |" + " --- |" * len(rows)]
    lines += [f"| {k} | " + " | ".join(cell(r, k) for r in rows) + " |" for k in keys]
    lines += ["", "기대 동작과 달랐던 문항:"]
    lines += [f"- {r['provider']}: " + (", ".join(f"{i} ({why})" if why else i for i, why in r["failed"]) or "없음") for r in rows]
    return "\n".join(lines) + "\n"


def main():
    run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_run()
    if run_dir is None or not run_dir.exists():
        sys.exit("비교할 실행 기록이 없습니다. 먼저 python -m eval.run --provider claude,openai 를 실행하세요")
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    with (ROOT / meta["places"]).open(encoding="utf-8") as f:
        places = {p["id"]: p for p in map(json.loads, f)}
    out = []
    for provider in meta.get("models", {}):
        path = run_dir / f"{provider}.jsonl"
        if not path.exists():
            continue
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        g = run_dir / f"ground_{provider}.jsonl"
        judged = [json.loads(line) for line in g.read_text(encoding="utf-8").splitlines() if line.strip()] if g.exists() else None
        out.append(model_row(provider, rows, places, judged, meta))
    if not out:
        sys.exit("실행 기록에 모델별 결과가 없습니다")
    target = ROOT / config.EVAL_RESULTS_DIR / f"{run_dir.name}_compare.md"
    target.write_text(to_markdown(run_dir.name, meta, out), encoding="utf-8")
    print(to_markdown(run_dir.name, meta, out))
    print(f"→ {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
