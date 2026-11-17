"""모델 비교표(eval/compare.py)의 계산을 확인한다. 모델을 부르지 않는다. (14번 8-5)"""
import config
from eval.compare import model_row, to_markdown
from tests.test_eval_score import PLACES, row, turn

META = {"models": {"claude": "anthropic:claude-sonnet-5-5", "x": "없는:모델"}, "model_options": {"claude": {"output_config": {"effort": "low"}}},
        "items": ["x"], "places": "p", "place_count": 1}


def test_비용은_토큰_수와_config_단가로만_계산한다():
    rows = [row(turn(input_tokens=1_000_000, output_tokens=100_000, retries={"draft": 3, "search": 1}))]
    got = model_row("claude", rows, PLACES, None, META)
    pin, pout = config.PRICES_PER_MTOK["anthropic:claude-sonnet-5-5"]
    assert got["cost_usd"] == round(pin + pout * 0.1, 4) and got["cost_per_item_usd"] == got["cost_usd"]
    assert (got["redrafts"], got["research"]) == (2, 1)   # 처음 쓴 것은 재작성이 아니다
    assert model_row("x", rows, PLACES, None, META)["cost_usd"] is None   # 단가를 모르면 빈칸


def test_근거성과_포기_문항을_함께_싣고_문장은_싣지_않는다():
    rows = [row(turn()), row(turn(kind="abstain"), expect={"kind": "course"})]
    judged = [{"item": "x", "grounded": True, "reason": "비밀 문장"}, {"item": "x", "grounded": False, "reason": "비밀 문장"}]
    got = model_row("claude", rows, PLACES, judged, META)
    assert got["abstain"] == 1 and got["expect_ok"] == 1 and got["ground"]["rate"] == 0.5
    md = to_markdown("run", META, [got, model_row("x", rows, PLACES, None, META)])
    assert "| 지표 | claude | x |" in md and "1/2 (50.0%)" in md and "채점 안 함" in md and "단가 없음" in md and "비밀 문장" not in md
