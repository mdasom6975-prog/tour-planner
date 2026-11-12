# 어디갈래 — 국내 여행 코스 플래너

한국관광공사 TourAPI 데이터로 국내 여행 코스를 짜 주는 1인 프로젝트입니다.
지원 지역은 부산 · 강릉 · 제주 · 서울 · 전북 · 전남광주 여섯 곳입니다.

## 필수 항목 세 가지

| 항목 | 위치 | 내용 |
|---|---|---|
| RAG | `rag/` | BM25 + 임베딩 → 순위 합치기(RRF) → 재정렬 |
| 오케스트레이션 | `graph/` (예정) | LangGraph로 조건 이해 → 검색 → 코스 작성 → 검증 → 재작성 |
| 하네스 엔지니어링 | `harness/`, `eval/` (예정) | 실행 기록, 평가셋, 두 모델(Claude · OpenAI) 비교표 |

## 준비

Python 3.14 기준입니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env`에 키 세 개를 넣습니다. 발급 위치는 `.env.example`의 주석에 있습니다.

| 이름 | 용도 |
|---|---|
| `TOURAPI_KEY` | 공공데이터포털 한국관광공사 국문 관광정보 서비스 |
| `ANTHROPIC_API_KEY` | Claude (기본 모델) |
| `OPENAI_API_KEY` | OpenAI (비교용) |

키가 동작하는지 점검합니다. 키 값은 출력하지 않습니다.

```bash
python scripts/check_keys.py
```

## 데이터 받기

`data/`는 git에 올리지 않으므로 처음에는 직접 받아야 합니다.
TourAPI는 오퍼레이션마다 하루 1,000건까지 호출할 수 있어, 전체(약 10,440곳)를 받는 데 여러 날이 걸립니다.

1. 지역별 장소 목록을 받습니다. 이미 받은 지역은 건너뜁니다.

```bash
python -m ingest.collect_list 부산 강릉 제주 서울 전북 전남광주
```

2. 반려동물 동반 정보를 받습니다.

```bash
python -m ingest.collect_pet
```

3. 매일 한 번, 오전 8시 이후에 실행합니다. 표출 여부(동기화 목록), 축제 목록, 소개글, 휴무일 · 이용시간, 무장애 정보를 한도까지 받고 검색용 데이터(`data/processed/places.jsonl`)를 다시 만듭니다. 중간에 끊겨도 받은 곳은 건너뛰고 이어받습니다.

```bash
python scripts/daily_collect.py
```

### 데이터 사본 (백업과 복원)

수집에 여러 날이 걸리므로, 받은 데이터를 비공개 저장소의 릴리스(`data-backup`)에 날짜별로 올려 둡니다. `gh` 로그인이 필요하고, 저장소가 비공개가 아니면 올리지 않습니다. `.env`는 들어가지 않습니다.

매일 수집이 끝난 뒤 올립니다.

```bash
python scripts/backup_data.py
```

다른 기기에서는 수집 대신 가장 최근 사본을 내려받아 풉니다. 이미 `data/`가 있으면 `--force`를 붙여야 덮어씁니다.

```bash
python scripts/backup_data.py --restore
```

## 실행

가상환경을 켠 터미널에서 실행합니다. 가상환경 밖에서 띄우면 `kiwipiepy`를 찾지 못해 오류가 납니다.

```bash
source .venv/bin/activate
```

```bash
streamlit run app.py
```

브라우저에서 http://localhost:8501 을 엽니다. 화면 위의 개발자 모드를 켜면 어떤 도구가 어떤 순서로 불렸는지 볼 수 있습니다.

처음 실행할 때는 임베딩 모델(`dragonkue/BGE-m3-ko`, 약 2.2GB)과 재정렬 모델(`BAAI/bge-reranker-v2-m3`)을 내려받고 장소를 벡터로 바꾸느라 시간이 걸립니다. 벡터는 `data/index/`에 저장되어 다음부터는 바뀐 장소만 다시 계산합니다.

## 폴더 구성

| 경로 | 역할 |
|---|---|
| `app.py` | Streamlit 화면 |
| `config.py` | 바꿀 수 있는 값 전부 (모델 이름, 지역 코드, 검색 개수, 한도) |
| `ingest/` | TourAPI 호출, 수집, 정제, 휴무일 해석 |
| `rag/` | 검색. 바깥에서는 `rag/retriever.py`의 `Retriever.search`만 부릅니다 |
| `harness/` | 실행 기록 (`runs/날짜/실행번호.jsonl`) |
| `scripts/` | 키 점검, 매일 수집, 데이터 사본, 목록 집계 |
| `data/` | 받은 원본(`raw/`), 정제본(`processed/`), 벡터(`index/`). git에 올리지 않습니다 |
| `PRD.md` | 명세. 범위, 합격선, 구현 순서 |
| `CLAUDE.md` | 작업 규칙과 설계 원칙 |

## 출처

출처 : ⓒ한국관광공사

관광 정보와 사진은 한국관광공사 TourAPI에서 받았습니다. 이용 조건은 [한국관광콘텐츠랩 저작권 정책](https://api.visitkorea.or.kr/#/useServiceGuide/2)을 따릅니다.
