"""바꿀 수 있는 값은 전부 여기 둔다. 값을 바꾸면 평가 비교표의 "바꾼 것" 칸에 적는다."""
import os

from dotenv import load_dotenv

load_dotenv()

# --- LLM -----------------------------------------------------------------
# init_chat_model("제공자:모델") 형식. 비교표는 이 두 줄을 각각 돌려 만든다.
MODELS = {
    "claude": "anthropic:claude-sonnet-5-5",   # 2026-11-17 사용자 결정: opus-5-5 에서 바꿈
    "openai": "openai:gpt-5.4-mini",
}
# 왜: Anthropic API 잔액이 떨어져 Claude 호출이 실패한다(2026-11-19 사용자 결정). 코스 생성 기본값만 openai 로 두고 채점자는 그대로다. 어디: make_llm · eval 의 --provider 기본값.
# 교안: 직접 대응 없음. Claude 로 돌릴 때는 LLM_PROVIDER=claude 를 붙인다.
LLM_PROVIDER = os.getenv("LLM_PROVIDER") or "openai"
# 왜: Opus 5.5 · Sonnet 5.5 는 생각(thinking)을 끌 수 없고 effort 로 깊이를 조절한다. 2026-11-17 측정(Sonnet 5.5 코스 작성): low 5 ~ 7초 · medium 6 ~ 13초 · high 17 ~ 27초. 어디: make_llm 이 모델을 만들 때.
# 교안: 직접 대응 없음. 모델마다 받는 설정 이름이 달라 제공자별로 적는다(지시문 · 검색 결과는 두 모델이 같다).
MODEL_OPTIONS = {
    "claude": {"output_config": {"effort": "low"}},
    "openai": {"reasoning_effort": "low"},   # 2026-11-17 결정: Claude 의 effort low 와 맞춘다(기본값은 추론 없음)
}
# LLM 채점자는 비교 대상과 무관하게 고정한다 (PRD 12-2).
JUDGE_MODEL = "anthropic:claude-haiku-5-5"

# --- TourAPI -------------------------------------------------------------
TOURAPI_BASE = os.getenv("TOURAPI_BASE") or "https://apis.data.go.kr/B551011/KorService2"
# 왜: 활용신청 화면마다 End Point 주소가 달라 서비스별로 따로 받는다(2026-11-13 사용자가 .env 에 정리). 어디: ingest/tourapi.py 의 call.
# 교안: 직접 대응 없음. 이름의 대소문자는 .env 에 적힌 그대로(With)이고, 모두 대문자로 적은 경우도 받는다.
TOURAPI_WITH_BASE = os.getenv("TOURAPI_With_BASE") or os.getenv("TOURAPI_WITH_BASE") or "https://apis.data.go.kr/B551011/KorWithService2"
TOURAPI_PET_BASE = os.getenv("TOURAPI_PET_BASE") or "https://apis.data.go.kr/B551011/KorPetTourService2"
# 서비스 이름 → 주소. 여기 없는 서비스 이름은 TOURAPI_BASE 의 윗 주소에 이름을 붙여 쓴다.
TOURAPI_SERVICE_BASES = {"KorWithService2": TOURAPI_WITH_BASE, "KorPetTourService2": TOURAPI_PET_BASE}
# 기상청(공공데이터포털 같은 키 TOURAPI_KEY). 단기예보는 가까운 날(오늘~3일 뒤), 중기예보는 4~10일 뒤.
KMA_SHORT_BASE = os.getenv("KMA_SHORT_BASE") or "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
KMA_MID_BASE = os.getenv("KMA_MID_BASE") or "https://apis.data.go.kr/1360000/MidFcstInfoService"
# 왜: TourAPI 는 지역을 이름이 아니라 법정동 코드로 거른다. 어디: 수집(ingest)의 조회 조건.
# 교안: 4일차 PRD 의 "도시 → 통화 표(코드)" — LLM 이 추측하지 않게 값을 표로 고정하는 방식.
# 값은 2026-11-11 실제 응답에서 읽었다. 예전 areaCode(6/32/39)는 일부 장소에만 붙어 있어 쓰지 않는다
# (부산: areaCode 219건, 법정동 코드 2,226건).
#   codes        : TourAPI 조회 조건
#   addr_keyword : 받은 장소의 주소에 들어 있어야 하는 글자 (코드가 바뀌었는지 감지하는 데 쓴다)
#   verified     : 코드를 실제 응답으로 확인한 날 (화면 출처 표시에 쓴다)
REGIONS = {
    "부산": {"codes": {"lDongRegnCd": "26"}, "addr_keyword": "부산", "verified": "2026-11-11"},  # 측정 2,226건
    "강릉": {"codes": {"lDongRegnCd": "51", "lDongSignguCd": "150"}, "addr_keyword": "강릉", "verified": "2026-11-11"},  # 측정 993건
    "제주": {"codes": {"lDongRegnCd": "50"}, "addr_keyword": "제주", "verified": "2026-11-11"},  # 측정 2,116건
    # 2026-11-11 추가. 진행 중 · 예정 축제가 세 지역 합계 9곳인데 서울만 28곳이라 넣었다.
    "서울": {"codes": {"lDongRegnCd": "11"}, "addr_keyword": "서울", "verified": "2026-11-11"},  # 측정 8,012건
    # 2026-11-11 추가. 전라도는 도 단위라 한 지역 안에 여러 도시(전주 · 군산 · 여수 · 순천 …)가 있다.
    "전북": {"codes": {"lDongRegnCd": "52"}, "addr_keyword": "전북", "verified": "2026-11-11"},  # 측정 2,412건
    # 광주와 전라남도는 법정동 코드가 12 로 같다(주소: 전남광주통합특별시). 예전 지역 코드 5 · 38 로 따로 넣으면 같은 장소를 두 번 받는다.
    "전남광주": {"codes": {"lDongRegnCd": "12"}, "addr_keyword": "전남광주", "verified": "2026-11-11"},  # 측정 3,660건
}
# 목록 한 번 호출에 요청하는 건수. 1000 을 요청해 993건(강릉 전체)을 한 번에 받는 것까지 측정했다.
LIST_PAGE_SIZE = 1000
# 주소가 있는 장소 중 addr_keyword 를 포함해야 하는 최소 비율. 이보다 낮으면 지역 코드가 바뀐 것으로 본다.
REGION_ADDR_MATCH_MIN = 0.9
# 하루 호출 한도. 오퍼레이션마다 따로 1,000건이다 (2026-11-11 활용신청 화면에서 확인).
TOURAPI_DAILY_LIMIT = 1000
TOURAPI_SAFETY_MARGIN = 50  # 한도 직전에 멈추기 위한 여유분 (점검·재시도용으로 남겨 둔다)
TOURAPI_LIVE_MARGIN = 10    # 실시간 재확인(get_place_detail)이 남겨 두는 수. 수집의 여유분 50건 중 40건(코스 2개)까지 쓴다. 수집이 끝나는 11월 20일 뒤에는 하루 990건

# 왜: 5,335건 전부의 상세를 받으면 6일이 걸려, 코스 재료가 되는 유형부터 받는다. 어디: 상세 수집(1-5).
# 교안: 4일차 PRD "하지 않을 것" — 범위를 먼저 좁히고, 기능이 돌아간 뒤에 넓힌다.
# 이름은 유형별 예시 장소를 보고 붙였다. 건수는 2026-11-11 측정 (합계 3,104곳).
DETAIL_TYPES = {
    "12": "관광지",     # 1,051
    "14": "문화시설",   # 261
    "15": "축제·행사",  # 113
    "39": "음식점",     # 1,679
}
# 상세 수집이 연속으로 이만큼 실패하면 멈춘다 (서버 장애 때 한도만 쓰는 것을 막는다).
DETAIL_MAX_CONSECUTIVE_FAILURES = 5
# 호출 사이에 쉬는 시간(초). 초당 호출 제한이 있는지 확인하지 못해 조금 둔다.
TOURAPI_SLEEP_SEC = 0.1
# 2차 확장 후보(지금은 받지 않음): 28 레포츠 251, 38 쇼핑 1,473 중 전통시장, 32 숙박 506

# --- 카카오 로컬 API (지도 링크용 장소 ID 찾기) ---
# 왜: 같은 이름의 다른 지역 가게가 섞이지 않게, 가진 좌표 반경 안에서만 찾는다. 어디: ingest/match_kakao_place.py.
# 교안: 직접 대응 없음. 값은 2026-11-13 음식점 20곳 실호출에서 정했다 (같은 가게의 최대 거리 44m, 영문↔한글 표기 차이는 0~41m).
KAKAO_PLACE_PAGE_URL = "https://place.map.kakao.com/"   # 장소 ID 를 붙이면 가게 정보 + 위치 페이지
KAKAO_LOCAL_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
KAKAO_RADIUS_M = 100            # 이 반경 안의 후보만 본다
KAKAO_CATEGORY_CODES = ("FD6", "CE7")  # 음식점 · 카페만 후보로 인정 (주차장이 걸린 사례 방지)
KAKAO_SOLE_MAX_M = 50           # 이름이 달라도 업종이 맞는 후보가 하나뿐이고 이 안이면 같은 가게로 본다 (임시값, 표본 20곳)
KAKAO_TIMEOUT_SEC = 10
# 왜: 장소 ID 를 모으다 서버·키 문제가 나면 한도만 쓰므로 멈춘다. 어디: ingest/collect_kakao_ids.py.
# 교안: DETAIL_MAX_CONSECUTIVE_FAILURES 와 같은 생각. 초당 호출 제한은 확인하지 못해 조금 쉰다. 일일 한도 수치는 카카오 앱 관리 [통계] > [쿼터] 에서 확인 전이다.
KAKAO_DAILY_LIMIT = 100_000     # 일일 쿼터. 2026-11-13 사용자 확인 (앱 관리 [통계] > [쿼터]). 수치는 카카오가 바꿀 수 있다
KAKAO_MAX_CONSECUTIVE_FAILURES = 5
KAKAO_SLEEP_SEC = 0.1

# --- 임베딩 ---
# 왜: 글을 벡터로 바꿔 "뜻이 가까운" 장소를 찾는 모델이다. 이름을 여기 한 줄에 두어 평가 때 바꿔 끼운다. 어디: rag/dense.py.
# 교안: RAG 실습1 Q4 · 실습2 에서 쓴 모델. 2026-11-11 이 노트북(M3 Pro · 18GB)에서 세 후보를 재고 골랐다.
#   dragonkue/BGE-m3-ko      2,182MB · 8,192토큰까지 읽음(본문 잘림 0건) · 948건 43.7초 · 질문 22ms · 메모리 1.56GB  ← 선택
#   jhgan/ko-sroberta        128토큰까지만 읽어 본문의 94.3% 가 잘림 → 쓰지 않음
#   text-embedding-3-small   OpenAI API. 질문 138ms · 948건에 447,361토큰. "낙곱새" 를 못 찾음 → 3단계 평가에서 비교 대상
# 2026-11-13 평가(고름용 18건, nDCG@10): 재정렬까지 0.863 대 text-embedding-3-small 0.789, 임베딩 단독 0.717 대 0.517 → 그대로 둔다 (eval/README.md)
EMBED_MODEL = "dragonkue/BGE-m3-ko"

# --- 검색 ----------------------------------------------------------------
# 왜: 두 검색 결과를 합칠 때의 값들. 평가에서 바꿔 가며 비교하므로 여기 둔다. 어디: rag/hybrid.py.
# 교안: RAG 실습1 Q6 조건 — 각 검색기에서 상위 50개, k = 60, 임베딩 가중치는 0.3 / 0.5 / 0.7 중 평가로 고른다.
RETRIEVE_K = 50          # 각 검색기에서 가져오는 후보 수
RRF_K = 60               # 점수(d) = Σ 가중치 / (RRF_K + 순위)
HYBRID_W_DENSE = 0.5     # 임베딩 가중치 (BM25 는 1 - 이 값). 2026-11-12 평가: 재정렬 뒤 0.3 은 0.801, 0.5 는 0.863, 0.7 은 0.852, 1.0 은 0.864 → 차이 0.02 미만이라 유지
# 왜: 합친 검색의 상위 후보를 질문과 함께 다시 읽어 순위를 매기는 모델과 그 범위. 어디: rag/rerank.py.
# 교안: RAG 실습1 Q7 조건 — CrossEncoder 로 Hybrid 상위 30개를 재정렬해 10개를 돌려준다. 모델도 교안과 같다.
# 2026-11-11 측정(M3 Pro): 후보 10곳 0.56초 · 20곳 1.19초 · 30곳 1.66초 · 50곳 2.59초. 합친 검색(38ms)의 약 45배.
#   임베딩 모델과 함께 올려 메모리 2.05GB. 20위 밖의 좋은 답을 끌어올린 사례가 있어 30곳으로 정했다.
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
RERANK_CANDIDATES = 30   # 재정렬에 넣는 후보 수. 2026-11-12 평가: 20곳은 0.832, 30곳은 0.863 → 0.6초 느려도 30곳 유지
RERANK_K = 10            # 재정렬 뒤 남기는 수
RERANK_BATCH = 4          # 한 번에 읽는 쌍의 수. 2026-11-17 측정(검색 4번 합계): 16 → 9.12초, 8 → 7.87초, 4 → 7.32초. 상위 10곳은 순서까지 같았다
RERANK_ENABLED = True    # 끄면 합친 결과를 그대로 돌려준다 (평가에서 있음/없음을 비교하고, 너무 느릴 때 끈다)

# --- 코스 규칙 (코드가 판정) ----------------------------------------------
MAX_LEG_KM = 30          # 연속한 두 장소의 직선거리 상한(기본)
# 왜: 도시형 지역은 30km가 사실상 무제한이라 지역별로 좁힌다. 근거는 2026-11-13 실측: 지역 안 장소 쌍 거리의 90%가 서울 16.3 · 강릉 20.7 · 부산 24.0km 안이고, 제주 47.7 · 전북 80.4 · 전남광주 107.5km는 30보다 커 기본값을 그대로 쓴다. 어디: validate_course 의 거리 검사.
# 교안: 직접 대응 없음. 값은 90% 거리를 5km 단위로 올림(최대 30). 제주는 PRD 예상(더 짧게)과 반대로 넓게 퍼져 있어 처음에는 줄이지 않았다.
MAX_LEG_KM_BY_REGION = {"서울": 10, "제주": 20, "강릉": 25, "부산": 25}   # 서울은 2026-11-13 사용자 결정으로 20 → 10, 제주는 30(기본) → 20(하루 안에 17km · 29.9km씩 잇는 칸이 나왔다)
# 왜: 칸 사이 상한만으로는 구간마다 20km 씩 오가는 하루도 통과한다. 하루 직선거리 합에도 상한을 둔다(2026-11-17 사용자 결정: 11/16~17 실행 기록 지역별 상위 25% 경계). 어디: graph/validate.py find_violations.
# 교안: 직접 대응 없음. 표본이 지역당 11~19일이라 참고용이다. 여기 없는 지역(측정 표본 부족)은 이 검사를 하지 않는다.
# 5칸(가볼 곳 3곳, 구간 4개)이 되어 4칸(구간 3개) 기준 값 38 · 23 · 16 · 12 를 1.33 배로 올렸다(2026-11-17 사용자 결정, 서울 3일이 12km 를 못 지켜 재작성 3회를 다 쓰고도 24km 가 남았다).
MAX_DAY_KM_BY_REGION = {"제주": 50, "강릉": 31, "부산": 21, "서울": 16}
# 왜: 승인 전 비교안과 실제 검증 기준을 구분한다. 어디: 오프라인 거리 정책 비교 전용(추천, 최대) km.
# 교안: 직접 대응 없음. 실측 이동 시간이나 공식 기준이 아니며 현재 엔진 기준을 덮어쓰지 않는다.
PROPOSED_DAY_KM = {
    "서울": {"transit": (20, 30), "car": (25, 35)},
    "부산": {"transit": (25, 35), "car": (35, 50)},
    "강릉": {"transit": (25, 35), "car": (40, 60)},
    "제주": {"transit": (30, 45), "car": (60, 80)},
}
PROPOSED_WALK_DAY_KM = (3, 5)
RAIN_PROB_THRESHOLD = 60  # 이 값 이상이면 비 오는 날

# --- 반복 상한 -----------------------------------------------------------
MAX_SEARCH_RETRIES = 2
MAX_REDRAFTS = 2
# 왜: 모델은 후보의 주소만 보고 코스를 써서, 후보가 넓게 퍼진 지역(제주 3일)에서는 첫 초안이 매번 구간 상한을 넘고 다시 써도 칸이 빠졌다(2026-11-17 측정: 6회 중 6회 초과 · 2회 칸 빠짐). 코드가 후보를 가까운 것끼리 구역으로 묶어 알려 준다. 어디: graph/state.py zone_labels.
# 교안: 설계 원칙 "숫자와 사실 판정은 코드가". 2026-11-17 결정. 구역 이름은 A, B, C … 로 서쪽부터 붙인다.
ZONE_NAMES = "ABCDEF"
REPLACED_REASON = "장소 유형 · 거리 · 휴무 등의 규칙에 맞는 후보로 바꿨습니다."   # 코드가 바꿔 넣은 칸의 이유 문장
# 왜: 서울 3일에서 초안 2는 중복 1건뿐이었는데 다시 쓰다가 휴무 2건 · 거리 초과로 나빠졌다(2026-11-19 추적). 칸 하나의 위반은 모델에게 다시 쓰게 하기 전에 코드가 규칙에 맞는 가까운 후보로 바꾼다. 어디: graph/validate.py repair_slots.
# 교안: 설계 원칙 "판정은 코드가". 2026-11-19 사용자 결정. REPAIR_MAX_SLOTS 곳을 넘게 어긋난 초안은 예전처럼 다시 쓰게 하고, 재작성을 다 쓴 뒤에는 개수와 상관없이 바꿔 본다.
# 왜: 한 코스에 같은 대표메뉴 식당이 겹치면(menu_duplicate, 2026-11-19 T2) 코드가 가까운 다른 식당으로 바꾼다. 어디: graph/validate.py.
# 교안: 직접 대응 없음. SOFT_RULES 는 쏠림 · 메뉴 겹침처럼 "규칙 위반이 아닌 품질 문제"라 재작성을 다 써도 칸을 빼지 않는 규칙이다.
# 왜: 칸 시간대에 문을 닫는 장소(hours_closed, 2026-11-19 T4)도 코드가 가까운 다른 후보로 바꾼다. 다만 이용시간 문장을 정규식으로 읽은 값이고 칸 시각도 대표값이라, 재작성을 다 써도 못 고쳤다고 칸을 비우면 칸이 없어지는 쪽이 더 나쁘다. 그래서 SOFT_RULES 에 둔다. 어디: graph/validate.py.
# 교안: 직접 대응 없음. 규칙 위반 합격선(없는 장소 · 거리 · 휴무 · 기간 밖 축제)에는 들어가지 않는 품질 규칙이다.
REPAIR_RULES = ("distance", "duplicate", "closed", "withdrawn", "excluded", "museum_limit", "slot_type", "cafe_meal", "cafe_slot", "menu_duplicate", "hours_closed")
SOFT_RULES = ("theme_repeat", "menu_duplicate", "hours_closed")
REPAIR_MAX_SLOTS = 2
DAY_REPAIR_BEAM_WIDTH = 24   # 변경 칸 수별로 남기는 하루 동선 후보 수. 유한 탐색이며 해의 존재를 보장하지 않는다
REPAIR_WHY = {"distance": "이동 거리가 멀어", "duplicate": "같은 장소가 겹쳐", "closed": "휴무일이 겹쳐", "withdrawn": "관광공사 목록에서 내려가",
              "excluded": "제외 조건에 걸려", "museum_limit": "박물관 수 제한 때문에", "menu_duplicate": "앞 식당과 대표메뉴가 겹쳐",
              "hours_closed": "그 시간대에 문을 닫아",
              "slot_type": "일정 칸에 맞지 않는 장소 유형이라", "cafe_meal": "식사 칸에 카페가 들어가", "cafe_slot": "카페 칸에 다른 유형이 들어가", "day_distance": "하루 이동 거리가 길어"}
# 왜: 일수가 길수록 코스 · 날씨 조회 · 실시간 재확인(하루 40건)이 늘어 한도를 먼저 정한다. 어디: parse_request 의 일수 검사.
# 교안: 직접 대응 없음. 3일은 임의로 정한 값(2026-11-13)이라 시연 · 평가에서 부족하면 바꾸고 비교표에 적는다.
MAX_TRIP_DAYS = 3
# 왜: 하루 코스는 "오전 · 점심 · 오후 · 저녁"(PRD F3)이라 가볼 곳 2 + 식사 2가 필요하다. 후보가 이보다 적으면 코스를 짤 수 없다. 어디: grade_documents 의 "충분한가" 판정.
# 교안: 직접 대응 없음. 값은 PRD F3 의 하루 구조에서 나왔다.
# 왜: 365일 · 1,522일짜리 상설 공연까지 "축제"로 소개하면 사용자가 오해한다. 이 일수 이하만 축제로 소개하고 나머지는 "상설 · 장기 행사"로 따로 둔다. 어디: fetch_context.
# 교안: 직접 대응 없음. 30일은 제가 정한 값(2026-11-13)이다. 측정: 11/14~16 여행에 겹치는 행사 30건 중 30일 이하 9건 · 100일 이상 15건.
FESTIVAL_MAX_DAYS = 30
# 왜: 하루에 가볼 곳이 2곳뿐이라 코스가 빈약하다는 의견(2026-11-17 사용자 결정). 오후를 둘로 나눠 가볼 곳을 3곳으로 늘린다. 어디: 하루 칸 · grade_documents 의 필요 후보 수.
# 교안: 직접 대응 없음. PRD F3 의 "오전 / 점심 / 오후 / 저녁" 구조를 바꾼 것이다. 하루 이동 거리 상한(MAX_DAY_KM_BY_REGION)은 4칸 기준으로 잡은 값이라 다시 재야 한다.
PLACES_PER_DAY = 3
# 왜: 3곳으로 늘린 뒤 작은 도시 요청이 후보 부족으로 포기됐다(dev c14 6회 중 5회). 다시 찾아도 모자라면 하루 가볼 곳을 이 수로 줄여 짠다. 어디: grade_documents · slots_for.
# 교안: 직접 대응 없음(2026-11-19 사용자 결정). 2는 5칸으로 늘리기 전의 하루 가볼 곳 수다. 이것도 못 채우면 포기한다.
MIN_PLACES_PER_DAY = 2
MEALS_PER_DAY = 2
# 왜: 코스에는 가볼 곳과 음식점이 둘 다 필요해 유형을 두 묶음으로 나눠 따로 찾는다. 어디: retrieve. (축제는 search_festivals 가 따로 맡는다)
# 교안: PRD F2 "콘텐츠 유형은 메타데이터 필터". 이름은 DETAIL_TYPES 의 값과 같아야 한다.
SIGHT_TYPES = ["관광지", "문화시설"]
FOOD_TYPES = ["음식점"]
# 왜: 하루 칸 이름과 부가 코스(비 · 눈이 오면 갈 곳) 규칙을 한곳에 둔다. 실내 여부는 유형으로 코드가 가른다(2026-11-13 결정). 어디: draft_course · respond.
# 교안: 직접 대응 없음. 실내 유형을 문화시설로 둔 것은 임시 기준이라 평가에서 부족하면 바꾼다.
LATE_SLOT = "늦은 오후"
COURSE_SLOTS = ["오전", "점심", "오후", LATE_SLOT, "저녁"]
SIGHT_SLOTS = ("오전", "오후", LATE_SLOT)   # 가볼 곳 칸. 나머지(점심 · 저녁)는 음식점
# 왜: 커피 · 디저트 취향을 말한 사람은 카페가 코스 안에 있어야 한다. 그때만 점심 뒤에 카페 칸을 하나 더한다(2026-11-16 결정, dev c02). 어디: graph/state.py slots_for.
# 교안: 직접 대응 없음. 취향 판별은 낱말 비교로 코드가 한다. 말하지 않으면 칸은 네 개 그대로이고 "근처 카페 추천"만 따로 둔다.
CAFE_SLOT = "카페"
CAFE_WORDS = ("커피", "카페", "디저트", "베이커리", "빵", "찻집")
COURSE_SLOTS_WITH_CAFE = ["오전", "점심", CAFE_SLOT, "오후", LATE_SLOT, "저녁"]
# 왜: 칸의 시간대와 장소의 이용시간이 맞는지 코드가 판정하려면 칸마다 대표 시각이 필요하다(2026-11-19 T4). 시각은 분 단위로 적는다(600 = 10:00). 어디: graph/validate.py hours_closed · eval/quality.py hours_fit.
# 교안: 직접 대응 없음. 값은 사본(2026-11-16)의 이용시간으로 정했다: 오전 칸을 09:00 로 두면 관광지의 23% 가 개장 전이라 판정되고 10:00 이면 3% 다(10:30 2%, 11:00 1%). 점심 12:30 · 저녁 18:30 은 식당 4% · 11% 가 그 시각에 쉰다. 체류 여유(시각 + 머무는 시간)는 두지 않고 "그 시각에 열려 있는가"만 본다.
SLOT_MINUTES = {"오전": 10 * 60, "점심": 12 * 60 + 30, CAFE_SLOT: 14 * 60, "오후": 14 * 60 + 30, LATE_SLOT: 16 * 60 + 30, "저녁": 18 * 60 + 30}
# 왜: "11월 10일"을 모델이 1년 뒤로 읽어도 코스는 짜되, 읽은 날짜와 먼 날짜라는 점을 알린다(2026-11-16 결정, dev b05). 어디: graph/parse.py · graph/course.py.
# 교안: 직접 대응 없음. 90일은 임의 값.
MAX_AHEAD_DAYS = 90
INDOOR_TYPES = ["문화시설"]
BACKUP_MAX = 3

# --- 데이터 사본 ----------------------------------------------------------
# 왜: data/ 는 git 에 올리지 않아 노트북 한 대에만 있었다. 비공개 저장소의 릴리스에 날짜별 사본을 둔다. 어디: scripts/backup_data.py.
# 교안: 직접 대응 없음 (유실 대비 · 다른 기기에서 시연). 릴리스 이름을 여기 두어 스크립트에 글자를 박지 않는다.
BACKUP_RELEASE_TAG = "data-backup"

# --- 검색 평가 (3단계) ----------------------------------------------------
# 왜: 수집으로 장소가 날마다 늘어, 평가는 날짜로 고정한 사본에 대해 잰다. 벡터도 따로 두어 평가가 실제 색인(data/index)을 줄이지 않게 한다. 어디: eval/.
# 교안: RAG 실습1 Q2 — 정답 목록(qrels)과 문서 묶음(corpus)을 고정해야 점수를 비교할 수 있다.
EVAL_PLACES = "data/eval/places_2026-11-12.jsonl"
EVAL_INDEX_DIR = "data/eval/index"
# 왜: 코스 평가(8단계)는 카페 · 분류 칸이 있는 새 사본을 쓴다. dev 로 고치는 동안은 11/16 사본, 수집이 끝나면 최종 사본으로 바꿔 비교표와 holdout 을 돌린다(2026-11-16 결정). 어디: eval/run.py.
# 교안: RAG 실습1 Q2 — 문서 묶음을 고정. 검색 평가(EVAL_PLACES)와는 사본이 다르다.
EVAL_COURSE_PLACES = "data/eval/places_2026-11-16.jsonl"
EVAL_COURSE_INDEX_DIR = "data/eval/index_2026-11-16"
EVAL_COURSE_SET = "eval/course_set.jsonl"
EVAL_RUNS_DIR = "runs/eval"       # 문항별 실행 기록(관광공사 문장이 섞여 git 에 올리지 않는다). 비교표는 eval/results/
EVAL_RESULTS_DIR = "eval/results"   # 채점 결과표(장소 이름과 숫자만). git 에 올린다
EVAL_MAX_SEC = 30                   # 요청 1건 소요 합격선 (PRD 12-2)
# 왜: 비교표의 비용 열은 실행 기록의 토큰 수에 공식 단가를 곱해 계산한다(PRD 12-2). 단가는 바뀌므로 확인한 날짜와 출처를 함께 적는다. 어디: eval/compare.py.
# 교안: 2일차 Part3 비교표의 비용 열. 단위는 100만 토큰당 달러(입력, 출력). 캐시 · 배치 할인은 쓰지 않아 넣지 않았다.
PRICES_CHECKED = "2026-11-17"   # platform.claude.com/docs/en/about-claude/pricing · developers.openai.com/api/docs/pricing
PRICES_PER_MTOK = {
    "anthropic:claude-sonnet-5-5": (2.00, 10.00),
    "openai:gpt-5.4-mini": (0.75, 4.50),
}
GROUND_PASS_RATE = 0.9        # 근거성 합격선(PRD 12-2): 근거 있는 이유 문장 90% 이상
GROUND_SOURCE_CHARS = 1500    # 채점자에게 보여 주는 소개글 길이. 코스 작성은 앞부분(SNIPPET_CHARS)만 보지만 채점은 출처 문서를 넉넉히 본다
GROUND_NEAR_KM = 5.0          # 이유 문장의 "가깝다 · 근처 · 이동이 짧다"를 인정하는 직전 장소와의 직선 거리(2026-11-17 정함: 사람 표본에서 3.6km 는 인정, 8km 대는 불인정)
# 고정 날씨표: 적지 않은 날은 맑음. 비 · 눈 분기를 타 보도록 이틀만 다르게 둔다(값은 임의).
EVAL_WEATHER_DEFAULT = {"temp_max": 12.0, "temp_min": 4.0, "rain_prob": 10, "snow_cm": 0.0}
EVAL_WEATHER = {"2026-11-22": {"temp_max": 9.0, "temp_min": 5.0, "rain_prob": 80, "snow_cm": 0.0},
                "2026-11-29": {"temp_max": 1.0, "temp_min": -4.0, "rain_prob": 70, "snow_cm": 2.0}}
EVAL_POOL_DEPTH = 20     # 정답 후보를 모을 때 검색기마다 가져오는 수
EVAL_SEED = 12           # 후보를 섞는 난수 씨앗 (재현용)
EVAL_K = 10              # Recall@k · nDCG@k 의 k (화면에 보이는 결과 수와 같게)
# 왜: 설정 비교(3-5a)에서 돌려 볼 값들. 고른 값은 위의 HYBRID_W_DENSE · RERANK_CANDIDATES 에 적는다. 어디: eval/compare_settings.py.
# 교안: RAG 실습1 Q6(가중치 0.3 / 0.5 / 0.7) · Q7(재정렬 후보 수). 1.0 은 BM25 를 뺀 경우로, 기준선에서 임베딩 단독이 합침보다 높아 추가했다.
EVAL_W_DENSE_GRID = [0.3, 0.5, 0.7, 1.0]
EVAL_RERANK_CAND_GRID = [20, 30]
EVAL_EMBED_ALT = "text-embedding-3-small"   # 임베딩 모델 비교(3-5b)의 상대. OpenAI API 라 본문과 질문이 밖으로 나간다
EARTH_RADIUS_KM = 6371.0   # 직선거리 계산에 쓰는 지구 반지름(평균값)
SNIPPET_CHARS = 200        # search_places 가 돌려주는 소개 발췌 길이. 요약하지 않고 원문 앞부분을 그대로 자른다 (PRD 11번 저작권)

# --- 날씨 (4-4) -----------------------------------------------------------
# 왜: 바깥 API 의 주소 · 대기 시간 · 예보 범위를 한 곳에 둔다. 어디: tools/weather.py.
# 교안: 3일차 day3_tools.py 의 get_weather 와 같은 Open-Meteo(키 없음). 눈(snowfall_sum)은 "비나 눈이 오면 갈 곳" 요구로 추가했다.
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_DAILY = "temperature_2m_max,temperature_2m_min,precipitation_probability_max,snowfall_sum"
# 2026-11-13 실제 호출: 응답 0.63~0.70초, 예보는 오늘 포함 16일(17일째는 서버가 400 으로 거절). 같은 날 약 20분 동안 서버가 응답하지 않았다.
WEATHER_TIMEOUT_SEC = 5      # 평소의 7배쯤. 한 번 더 시도하므로 서버가 죽었을 때 최대 10초를 기다린다
WEATHER_RETRIES = 1          # 연결 실패 · 시간 초과 · 서버 오류(5xx)일 때 다시 시도하는 횟수
WEATHER_FORECAST_DAYS = 16   # 오늘을 포함해 예보가 나오는 일수

# --- 로그 (L-1) -----------------------------------------------------------
# 왜: 프로그램에 무슨 일이 있었는지(서버 장애 · 다시 시도 · 예외)를 날짜별 파일로 남긴다. 질문 한 건의 단계를 남기는 실행 기록(runs/)과는 다른 것이다. 어디: harness/logs.py.
# 교안: 직접 대응 없음. 2026-11-13 날씨 서버가 20분 죽었을 때 남은 기록이 없어서 넣었다.
LOG_DIR = "logs"           # logs/날짜/debug.log (전부) · logs/날짜/error.log (ERROR 이상)
LOG_MAX_CHARS = 1000       # 한 줄에 적는 글자 수 상한. 소개글 · 질문 전문이 통째로 남지 않게 한다


# 왜: 후속 수정이 같은 대화의 코스를 이어 받으려면 State 를 저장해야 한다. 새로고침해도 이어 가도록 파일로 둔다. 어디: graph/runtime.py 의 open_checkpointer.
# 교안: 3일차 05 checkpointer — thread_id 가 대화 하나다.
CHAT_DB_PATH = "data/chat.sqlite"

# 왜: 관광공사는 카페도 음식점(contenttypeid 39)으로 줘서 점심 · 저녁 후보에 섞였다. 원본 목록의 분류(lclsSystm2) FD05 가 카페 · 전통찻집이다. 어디: ingest/clean.py 의 is_cafe, graph/retrieval.py.
# 교안: 직접 대응 없음. 점심 · 저녁은 식당만, 카페는 "근처 카페 추천" CAFE_PICKS 곳을 따로 둔다(2026-11-13 결정).
CAFE_CLASS = "FD05"
CAFE_PICKS = 2
SEARCH_K = 15        # 종류(가볼 곳 · 식당 · 카페 · 실내)마다 남기는 후보 수. 10 → 15 (2026-11-19 사용자 결정: 가볼 곳이 하루 3곳이 되어 서울 3일 후보가 필요량 9곳과 같았다). 재정렬 후보는 RERANK_CANDIDATES(30)까지라 음식점 · 실내는 그 안에서 걸러진다
OVERFETCH = 3   # 카페 · 박물관을 걸러 내고도 후보가 SEARCH_K 곳 남도록 음식점 · 실내(문화시설)는 이 배수만큼 넉넉히 찾는다

# 왜: 강릉 부모님 코스에 박물관만 나왔다. 원본 분류 VE07(박물관 · 미술관 · 전시관)은 날씨와 상관없이 본 코스 + 부가 코스를 합쳐 1곳만 둔다. 어디: ingest/clean.py 의 category, graph/retrieval.py · course.py · validate.py.
# 교안: 직접 대응 없음(2026-11-13 결정). 후보로는 MUSEUM_CANDIDATES 곳까지만 남겨 LLM 이 그 안에서 1곳을 고르게 한다.
MUSEUM_CLASS = "VE07"
MUSEUM_MAX = 1
MUSEUM_CANDIDATES = 3
# 왜: 공격 평가(9단계)에서 소개글의 지시대로 이유 문장에 전화번호 · 링크가 들어가 최종 답까지 나갔다(gpt-5.4-mini i4 · i7). 이유 문장은 장소를 고른 까닭만 적는 칸이라 연락처 · 링크가 있으면 그 문장을 통째로 바꾼다. 어디: graph/course.py pack_course.
# 교안: PRD 11번 간접 인젝션 "출력은 검사를 통과해야만 화면에 나간다". 2026-11-17 결정.
REASON_BLOCK_PATTERN = r"https?://|www\.|[\w-]+\.(?:com|net|org|kr|io|example)\b|0\d{1,2}[-.\s)]\s?\d{3,4}[-.\s]\d{4}"
REASON_REMOVED_TEXT = "이유 문장에 연락처 · 링크가 들어 있어 지웠습니다."
CANNOT_DO_WORDS = ("예약", "예매", "결제", "발권")   # 취향에 이 낱말이 있으면 "해 드리지 못하는 요청"으로 옮기고 안내한다(PRD 4번 하지 않을 것)
MUSEUM_WORDS = ("박물관", "미술관", "전시")   # 취향에 이 낱말이 있으면 "1곳만 넣었다"는 안내를 붙인다
# 왜: "빵 맛집" 같은 음식 취향을 가볼 곳 판정에 보내면 해변 · 시장 · 문화시설이 "빵과 무관"하다며 모두 탈락해 0곳 포기가 났다(2026-11-17 강릉 · 부산 재현). 어디: graph/retrieval.py grade_update.
# 교안: 직접 대응 없음(2026-11-17 결정). 이 낱말이 든 취향은 가볼 곳 판정에서 빼고 식당 칸을 고르는 쪽에서만 쓴다.
FOOD_PREF_WORDS = ("빵", "베이커리", "제과", "맛집", "식당", "음식", "커피", "카페", "디저트", "먹")
# 왜: "빵 맛집" · "닭강정" 요청에 점심 · 저녁이 모두 같은 음식 가게가 됐다(2026-11-17 실행 기록). 취향 질의로만 잡힌 식당(theme 표시)은 하루 식사 칸에 MAX_THEME_MEALS 곳까지만 넣는다. 어디: graph/validate.py find_violations.
# 교안: 직접 대응 없음(2026-11-17 결정). 낱말 목록 대신 검색이 theme 표시를 단다(graph/retrieval.py).
MAX_THEME_MEALS = 1

# 왜: 같은 종류 칸(오전↔오후, 점심↔저녁)을 맞바꾸면 하루 이동 거리가 줄지만, 이유 문장이 "오전에 봅니다"처럼 시간대를 말하면 문장과 칸이 어긋난다(2026-11-17). 어디: graph/validate.py reorder_day.
# 교안: 직접 대응 없음(2026-11-17 결정, 평가 코스 36일 측정: 맞바꿈으로 10% 이상 줄어드는 날 14~18일). 최소 이득 미만이면 바꾸지 않고, 이유에 시간 낱말이 있으면 그 쌍은 바꾸지 않는다.
REORDER_MIN_GAIN_KM = 0.5
REORDER_TIME_WORDS = ("오전", "오후", "점심", "저녁", "아침", "낮", "밤", "브런치", "야경", "일몰", "석양", "해질")

# 왜: 축제 갤러리에 카드가 너무 많으면 가로로 끝없이 넘겨야 한다. 어디: graph/present.py 의 festival_cards.
# 교안: 직접 대응 없음(2026-11-13 요청). 기간 안 축제를 먼저, 상설 · 장기 행사를 뒤에 둔다.
GALLERY_MAX = 20

# 왜: 사용자가 "바다"를 말하지 않으면 제주 코스에 바다가 0곳이었다(2026-11-13 실측). 지역마다 대표 취향을 칩으로 눌러 고르게 한다. 어디: app.py 의 취향 칩 → 질문 뒤에 "취향: …"으로 덧붙는다.
# 교안: 직접 대응 없음. 칩 목록은 저장 데이터의 분류(바다·오름·한옥 등)를 보고 정한 초안이며 실제 검색 결과로 다듬는다.
REGION_THEMES = {
    "제주": ["바다", "오름", "숲", "폭포", "해녀", "박물관"],
    "강릉": ["바다", "커피거리", "한옥", "호수", "시장", "박물관"],
    "부산": ["바다", "야경", "시장", "사찰", "영화", "카페"],
    "서울": ["궁궐", "한옥마을", "미술관", "쇼핑", "한강공원", "야경"],
    "전북": ["한옥마을", "시장", "사찰", "산", "먹거리", "역사"],
    "전남광주": ["바다", "섬", "정원", "사찰", "시장", "산"],
}
# 왜: "산도 넣어 줘" 같은 추가 요청은 이미 찾아 둔 후보에 없을 수 있어 그 취향으로 한 번 더 찾는다. 어디: graph/edit.py 의 add_candidates.
# 교안: 직접 대응 없음(2026-11-13 요청). 한 요청에서 새로 찾는 취향 · 이름 수와 취향마다 더하는 후보 수의 상한.
ADD_MAX_TERMS = 3
ADD_K = 5

# 왜: 코스 품질 지표(2026-11-19 T1)에서 요청 문장에 이 낱말이 있을 때만 "조건 정보가 있는 장소 비율"을 잰다. 합격선이 아니라 현재 값 기록용이다. 어디: eval/quality.py.
# 교안: 직접 대응 없음. 낱말 목록은 초안이며, 낱말이 없으면 해당 없음(None)으로 둔다.
ACCESS_REQUEST_WORDS = ("휠체어", "무장애", "유모차", "거동", "장애")
PET_REQUEST_WORDS = ("반려", "강아지", "애견", "멍멍이", "펫")
# 왜: "장애"가 "장애물"에, "펫"이 "카펫"에 걸려 조건을 말하지 않은 요청을 조건 요청으로 셌다(T1 크리틱 · 2026-11-19 T3). 위 낱말을 찾기 전에 이 낱말들을 지운다. 어디: tools/conditions.py request_wants (요청 반영 지표 · 검색 가중이 같이 쓴다).
# 교안: 직접 대응 없음. 새 오탐이 나오면 여기에 한 낱말씩 더한다.
REQUEST_FALSE_HITS = ("장애물", "카펫")
# 왜: 관광공사 무장애 원문은 "휠체어 접근 가능함"이 표준 문구인데(저장 1,928곳 중 1,074곳) 예전 판정은 "휠체어 접근이 가능"만 찾아 41곳만 가능으로 읽었다(2026-11-19 T3 실제 데이터 확인). 반대로 "휠체어 접근 어려움 · 불가"가 한 군데라도 있으면 가능으로 단정하지 않는다. 어디: tools/conditions.py wheelchair_ok (후보 줄 · 가중 · 평가 지표가 같이 쓴다. 화면 카드 graph/course.py access_text 는 예전 판정 그대로).
# 교안: 직접 대응 없음. 한계: "휠체어 출입 가능" · "휠체어 사용자 이용 쉬움" 같은 다른 문구는 가능으로 세지 않는다(보수적).
ACCESS_POSITIVE_PATTERN = r"휠체어\s*접근\s*(?:이\s*)?가능"
ACCESS_NEGATIVE_PATTERN = r"휠체어[^,.;_]{0,12}(?:불가|어려)"
# 왜: 요청에 무장애 · 반려동물 낱말이 있어도 검색은 의미 유사도만 봐서, 조건이 긍정으로 저장된 장소가 후보 15곳 밖에 남았다. 해당 장소를 이 칸 수만큼 앞으로 올린다(거르지 않는다 — PRD 4번). 어디: tools/places.py search_places 의 k 자르기 직전.
# 교안: 직접 대응 없음(2026-11-19 T3). 후보 풀은 재정렬 후보 수(RERANK_CANDIDATES)까지다. 값은 임의로 정했고 dev 에는 해당 문항이 없어 효과는 실제 데이터 전 · 후 비교로만 봤다.
REQUEST_BOOST_RANKS = 8
REQUEST_BOOST_POOL = RERANK_CANDIDATES   # 가중할 때 검색기에서 받아 순서를 바꾸는 후보 수
# 왜: 후보 줄이 길어지면 코스 작성 입력 토큰이 늘어 무장애 · 메뉴 문구는 앞부분만 옮긴다. 어디: tools/conditions.py access_brief · menu_label (코스 작성 후보 줄).
# 교안: 직접 대응 없음. 항목 우선순위는 이동 · 동행(아이 · 부모님)에 쓸모가 큰 순서다.
CAND_ACCESS_KEYS = ("휠체어", "접근로", "엘리베이터", "유아차", "수유실")
CAND_ACCESS_MAX_ITEMS = 3
CAND_ACCESS_ITEM_CHARS = 30
CAND_ACCESS_CHARS = 110
CAND_MENU_CHARS = 30
# 왜: 대표메뉴 키워드를 가를 때 "세트 · 정식"처럼 어느 식당에나 붙는 말은 메뉴 겹침으로 세지 않는다. 어디: graph/menu.py (T2 검증도 같은 함수를 쓴다).
# 교안: 직접 대응 없음. 정규화 규칙 초안: 구분자(, / · 줄바꿈 공백 괄호)로 나누고 소문자로 바꾸며 MENU_KEYWORD_MIN_LEN 글자 미만과 아래 낱말은 버린다.
MENU_KEYWORD_MIN_LEN = 2
MENU_STOPWORDS = ("세트", "정식", "메뉴", "기본", "기본상", "스페셜", "프리미엄", "특선", "모둠", "대표")

# 왜: 칸의 대표 시각에 문을 여는 곳을 처음부터 고르게 하려고 후보 줄에 이용시간을 싣는다(2026-11-19 T5). 원문은 길 수 있어(최대 300자) 코드가 읽은 값(예: 11:00~20:00) 또는 원문 앞부분만 이 길이까지 옮긴다. 어디: tools/conditions.py hours_label (코스 작성 · 수정 후보 줄).
# 교안: PRD 8번 "LLM 은 받은 장소 정보를 옮겨 적기만". 값을 새로 만들지 않고, 이용시간 정보가 없으면 칸 자체를 넣지 않는다.
CAND_HOURS_CHARS = 60
# 왜: 판정 지시문(grade_documents)이 후보 줄에서 무장애 · 반려동물을 보지 못해 "휠체어 · 반려동물" 요청에 맞는 장소를 알아보지 못했다(T3 한계). 판정 줄에는 코스 작성 줄보다 짧게 옮긴다. 어디: graph/retrieval.py _view.
# 교안: 직접 대응 없음(2026-11-19 T5). 판정은 정보가 없다는 이유만으로 탈락시키지 않는다.
GRADE_COND_CHARS = 60
