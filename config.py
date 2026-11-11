"""바꿀 수 있는 값은 전부 여기 둔다. 값을 바꾸면 평가 비교표의 "바꾼 것" 칸에 적는다."""
import os

from dotenv import load_dotenv

load_dotenv()

# --- LLM -----------------------------------------------------------------
# init_chat_model("제공자:모델") 형식. 비교표는 이 두 줄을 각각 돌려 만든다.
MODELS = {
    "claude": "anthropic:claude-opus-5-5",
    "openai": "openai:gpt-5.4-mini",
}
LLM_PROVIDER = os.getenv("LLM_PROVIDER") or "claude"
# LLM 채점자는 비교 대상과 무관하게 고정한다 (PRD 12-2).
JUDGE_MODEL = "anthropic:claude-haiku-5-5"

# --- TourAPI -------------------------------------------------------------
TOURAPI_BASE = os.getenv("TOURAPI_BASE") or "https://apis.data.go.kr/B551011/KorService2"
# 왜: TourAPI 는 지역을 이름이 아니라 법정동 코드로 거른다. 어디: 수집(ingest)의 조회 조건.
# 교안: 4일차 PRD 의 "도시 → 통화 표(코드)" — LLM 이 추측하지 않게 값을 표로 고정하는 방식.
# 값은 2026-11-11 실제 응답에서 읽었다. 예전 areaCode(6/32/39)는 일부 장소에만 붙어 있어 쓰지 않는다
# (부산: areaCode 219건, 법정동 코드 2,226건).
REGIONS = {
    "부산": {"lDongRegnCd": "26"},                          # 측정 2,226건
    "강릉": {"lDongRegnCd": "51", "lDongSignguCd": "150"},  # 측정 993건
    "제주": {"lDongRegnCd": "50"},                          # 측정 2,116건
}
# 하루 호출 한도. 오퍼레이션별인지 전체 합산인지 확인 전이라 더 안전한 "전체 합산"으로 센다.
TOURAPI_DAILY_LIMIT = 1000
TOURAPI_SAFETY_MARGIN = 50  # 한도 직전에 멈추기 위한 여유분 (점검·재시도용으로 남겨 둔다)

# --- 검색 ----------------------------------------------------------------
RETRIEVE_K = 30   # 하이브리드 후보 수
RERANK_K = 10     # 재정렬 뒤 남기는 수

# --- 코스 규칙 (코드가 판정) ----------------------------------------------
MAX_LEG_KM = 30          # 연속한 두 장소의 직선거리 상한
RAIN_PROB_THRESHOLD = 60  # 이 값 이상이면 비 오는 날

# --- 반복 상한 -----------------------------------------------------------
MAX_SEARCH_RETRIES = 2
MAX_REDRAFTS = 2
