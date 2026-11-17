---
name: eval
description: 코스 평가를 돌리고 채점 · 근거성 · 모델 비교표 · 공격 결과표를 만든다. "평가 돌려 줘", "비교표 만들어 줘", "회귀 확인" 같은 요청에 쓴다.
---

# /eval — 평가와 비교표

PRD 12-2 의 평가 하네스를 순서대로 실행한다. 명세는 `PRD.md` 12-2, 형식은 `eval/README.md`.

## 먼저 확인할 것
- 실제 모델을 부르는 단계(①, ③, ⑤)는 비용과 시간이 든다. dev 29건 한 번에 약 8분, 2026-11-17 측정 기준 Sonnet 5.5 로 약 $1.6. **돌리기 전에 사용자에게 어느 단계까지 돌릴지 확인한다.**
- 고칠 때는 dev 만 본다. `--split holdout` 은 사용자가 설정 동결을 말했을 때 한 번만 돌린다. holdout 문항의 결과를 보고 코드를 고치지 않는다.
- `.env` 는 읽지 않는다. 키 점검은 `python scripts/check_keys.py` 로 한다.

## 순서
1. 실행: `.venv/bin/python -m eval.run` (모델 비교는 `--provider claude,openai`, 일부만은 `--ids c01,b02`)
2. 채점(모델 호출 없음): `.venv/bin/python -m eval.score` → `eval/results/<실행>_<모델>.md`
3. 근거성(채점자 `config.JUDGE_MODEL` 호출): `.venv/bin/python -m eval.ground`
4. 모델 비교표(모델 호출 없음): `.venv/bin/python -m eval.compare` → `eval/results/<실행>_compare.md`
5. 공격 평가: `.venv/bin/python -m eval.attack [--provider claude,openai]`

## 보고
- 숫자는 실행 결과에서만 가져온다. 기대 동작 일치, 코스 규칙 위반(합격선 0건), 근거성(합격선 90%), 30초 초과, 토큰 · 비용.
- 직전 실행과 나란히 놓고 달라진 문항과 그대로인 문항을 함께 적는다. 한 번씩만 돌린 값이면 그렇게 밝힌다.
- 실패 문항은 `eval-failure-analyst` 서브에이전트에게 원인 분석을 맡길 수 있다.
- 평가 문장을 지시문 · 퓨샷에 넣지 않는다. 합격선과 기대값은 사용자 결정 없이 바꾸지 않는다.
