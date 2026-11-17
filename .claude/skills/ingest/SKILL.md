---
name: ingest
description: 지역 데이터 수집 · 정제 · 검색 인덱싱 절차를 안내하고, 사용자가 요청한 단계만 실행한다. "수집 돌려 줘", "인덱스 다시 만들어 줘", "지역 추가" 같은 요청에 쓴다.
---

# /ingest — 수집 · 인덱싱

명세는 `PRD.md` 14번 1 · 2단계, 호출 한도와 저장 규칙은 `CLAUDE.md` "비밀 · 데이터".

## 지켜야 할 것
- TourAPI 는 하루 호출 한도가 있다. `data/raw/` 에 저장한 것을 다시 쓰고, 같은 것을 두 번 받지 않는다.
- **수집은 사용자가 요청했을 때만 실행한다.** 이 스킬을 읽었다고 수집을 시작하지 않는다. 수집 일정 · 순서 · 범위는 사용자가 정한다.
- `data/raw/` · `data/processed/` · `data/index/` · `data/eval/` 는 git 에 올리지 않는다. 관광공사 데이터는 공개 저장소에 다시 배포하지 않는다.
- `.env` 는 읽지 않는다. 로그에 요청 주소와 키를 남기지 않는다.

## 순서
1. 키 점검: `.venv/bin/python scripts/check_keys.py`
2. 매일 수집: `.venv/bin/python scripts/daily_collect.py` (목록 · 상세 · 새 음식점의 카카오 장소 ID)
3. 백업: `.venv/bin/python scripts/backup_data.py`
4. 현황: `.venv/bin/python scripts/list_stats.py`
5. 검색 평가(고름용 20건): `.venv/bin/python -m eval.retrieval_eval`. 확인용은 설정을 바꾼 뒤 한 번만.

## 새 지역을 넣을 때
- `config.REGIONS` 에 지역 코드와 확인 날짜를 적는다. 표에 없는 지역은 조건 해석이 되묻는다.
- 수집 → 정제 → 인덱스 순서로 다시 만들고, 건수는 실제 실행 결과로만 말한다.
- 평가용 고정 사본(`config.EVAL_COURSE_PLACES`)은 바꾸지 않는다. 사본을 바꾸면 기준선이 달라지므로 사용자 결정이 필요하다.
