"""harness/logs.py: 파일 두 개 · 날짜별 폴더 · 키 가리기 · 중복 연결 방지를 확인한다."""
import logging
from datetime import datetime

import pytest

import config
from harness.logs import get_logger, redact, setup_logging


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def logs(tmp_path):
    clock = Clock(datetime(2026, 11, 13, 23, 59, 58, 512000))
    setup_logging(base_dir=tmp_path, clock=clock)
    yield tmp_path, clock
    root = logging.getLogger("tour")
    for h in list(root.handlers):   # 테스트가 끝나면 연결을 떼어 실제 logs/ 에 쓰지 않게 한다
        root.removeHandler(h)
        h.close()


def _read(tmp_path, day, name):
    path = tmp_path / day / name
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def test_수준별로_두_파일에_나뉜다(logs):
    tmp_path, _ = logs
    log = get_logger("tools.weather")
    log.debug("디버그"); log.info("정보"); log.warning("경고"); log.error("오류"); log.critical("치명")
    debug, error = _read(tmp_path, "2026-11-13", "debug.log"), _read(tmp_path, "2026-11-13", "error.log")
    assert [line.split()[2] for line in debug] == ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    assert [line.split()[2] for line in error] == ["ERROR", "CRITICAL"]


def test_한_줄의_모양(logs):
    tmp_path, _ = logs
    get_logger("tools.weather").warning("다시 시도 %d회", 1)
    assert _read(tmp_path, "2026-11-13", "debug.log") == ["2026-11-13 23:59:58.512 WARNING  tools.weather 다시 시도 1회"]


def test_자정을_넘기면_새_날짜_폴더(logs):
    tmp_path, clock = logs
    log = get_logger("app")
    log.error("어제 오류")
    clock.now = datetime(2026, 11, 14, 0, 0, 1)
    log.error("오늘 오류")
    assert len(_read(tmp_path, "2026-11-13", "error.log")) == 1 and "어제 오류" in _read(tmp_path, "2026-11-13", "error.log")[0]
    assert len(_read(tmp_path, "2026-11-14", "error.log")) == 1 and "오늘 오류" in _read(tmp_path, "2026-11-14", "debug.log")[0]


def test_예외는_추적과_함께(logs):
    tmp_path, _ = logs
    try:
        {}["없는 칸"]
    except KeyError:
        get_logger("tools.places").exception("상세 조회 실패")
    text = "\n".join(_read(tmp_path, "2026-11-13", "error.log"))
    assert "상세 조회 실패" in text and "Traceback" in text and "KeyError" in text


@pytest.mark.parametrize("raw, hidden", [
    ("GET https://apis.data.go.kr/x?serviceKey=AbCd1234%2Fxyz&numOfRows=10", "AbCd1234"),
    ("헤더 Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
    ("OPENAI_API_KEY=sk-proj-abcdefgh12345678", "abcdefgh12345678"),
    ("키 값만 찍힘 sk-abcdefgh12345678", "abcdefgh12345678"),
    ('{"api_key": "zzzz9999yyyy", "query": "부산"}', "zzzz9999yyyy"),
])
def test_키로_보이는_값은_가린다(logs, raw, hidden):
    tmp_path, _ = logs
    get_logger("ingest").error(raw)
    line = _read(tmp_path, "2026-11-13", "error.log")[0]
    assert hidden not in line and "***" in line


def test_가리면서_다른_내용은_남긴다():
    assert redact("x?serviceKey=AAAA1111&numOfRows=10&pageNo=2") == "x?serviceKey=***&numOfRows=10&pageNo=2"
    assert redact("query_tokens=['부산', '낙곱새'] input_tokens=120") == "query_tokens=['부산', '낙곱새'] input_tokens=120"   # tokens 는 키가 아니다


def test_환경_변수에_있는_키_값은_이름표가_없어도_가린다(logs, monkeypatch):
    tmp_path, _ = logs
    monkeypatch.setenv("TOURAPI_KEY", "plainvalue-1234567890")
    get_logger("ingest").error("요청 실패: plainvalue-1234567890 가 거절됨")
    assert "plainvalue" not in _read(tmp_path, "2026-11-13", "error.log")[0]


def test_두_번_설정해도_한_번만_적힌다(logs):
    tmp_path, clock = logs
    setup_logging(base_dir=tmp_path, clock=clock)
    setup_logging(base_dir=tmp_path, clock=clock)
    get_logger("app").error("한 번")
    assert len(_read(tmp_path, "2026-11-13", "error.log")) == 1 and len(_read(tmp_path, "2026-11-13", "debug.log")) == 1


def test_긴_줄은_줄인다(logs):
    tmp_path, _ = logs
    get_logger("app").info("가" * (config.LOG_MAX_CHARS + 500))
    line = _read(tmp_path, "2026-11-13", "debug.log")[0]
    assert f"(전체 {config.LOG_MAX_CHARS + 500}자)" in line and line.count("가") == config.LOG_MAX_CHARS


def test_라이브러리_로그는_섞이지_않는다(logs):
    tmp_path, _ = logs
    logging.getLogger("urllib3").error("남의 로그")
    assert _read(tmp_path, "2026-11-13", "error.log") == []
