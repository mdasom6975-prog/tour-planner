"""로그. 프로그램에 있었던 일을 날짜별 파일 두 개로 남긴다: debug.log(전부) · error.log(ERROR 이상). (L-1)

질문 한 건의 단계를 남기는 실행 기록(harness/trace.py)과는 다르다. 기존 코드에 로그를 넣는 일(L-2)은 여기 없다.
쓰는 법:  setup_logging() 을 프로그램 시작에 한 번,  log = get_logger("tools.weather");  log.warning("...")
"""
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import config

ROOT = Path(__file__).resolve().parent.parent
BASE = "tour"   # 우리 코드의 로그만 모은다. 라이브러리(urllib3 등)의 로그는 섞지 않는다.

# 왜: 관광공사 API 는 키를 주소에 붙여 보낸다. 요청 주소나 오류 문장을 그대로 적으면 키가 파일에 남는다. 어디: 파일에 쓰기 직전의 모든 줄.
# 교안: 2일차 Part4 "비밀은 .env 에만 — 키는 코드 · 지시문 · 로그에 남기지 않는다". 실행 기록의 summarize 와 같은 목적이다.
SECRET_NAMES = ("key", "token", "secret", "password", "authorization")
PATTERNS = [
    (re.compile(r"(?i)\bBearer\s+\S+"), "Bearer ***"),   # 이름표 규칙보다 먼저: "Authorization: Bearer 값" 의 값을 통째로 가린다
    (re.compile(r"(?i)\b([\w-]*(?:key|token|secret|password|authorization))([\"']?\s*[=:]\s*[\"']?)[^\s&\"',}]+"), r"\1\2***"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"), "sk-***"),
]


def redact(text: str) -> str:
    """키로 보이는 값을 *** 로 바꾼다."""
    # 환경 변수에 올라와 있는 키의 값 자체도 가린다. 이름표 없이 값만 찍혀도 걸린다. (값을 읽기만 하고 어디에도 적지 않는다)
    for name, value in os.environ.items():
        if name.lower().endswith(SECRET_NAMES) and len(value) >= 8 and value in text:
            text = text.replace(value, "***")
    for pattern, repl in PATTERNS:
        text = pattern.sub(repl, text)
    return text


class DailyFileHandler(logging.Handler):
    """logs/날짜/파일이름 에 한 줄씩 덧붙인다. 날짜가 바뀌면 새 폴더로 넘어간다."""
    def __init__(self, filename: str, level: int, base_dir: Path, clock):
        super().__init__(level)
        self.filename, self.base_dir, self.clock = filename, Path(base_dir), clock
        self.day, self.stream = None, None

    def emit(self, record: logging.LogRecord) -> None:
        # 왜: 앱을 며칠 켜 두어도 날짜별로 나뉘어야 한다. 줄을 쓸 때마다 오늘 날짜를 보고, 바뀌었으면 파일을 새로 연다. 어디: 한 줄 쓰기.
        # 교안: 직접 대응 없음. 시계를 인자로 받는 것은 4일차 PRD "외부 의존 주입" — 테스트에서 자정을 넘겨 볼 수 있다.
        try:
            now = self.clock()
            day = f"{now:%Y-%m-%d}"
            if day != self.day:
                self.close_stream()
                folder = self.base_dir / day
                folder.mkdir(parents=True, exist_ok=True)
                self.stream, self.day = (folder / self.filename).open("a", encoding="utf-8"), day
            message = record.getMessage()
            if len(message) > config.LOG_MAX_CHARS:
                message = f"{message[:config.LOG_MAX_CHARS]}…(전체 {len(message)}자)"
            line = f"{now:%Y-%m-%d %H:%M:%S}.{now.microsecond // 1000:03d} {record.levelname:<8} {record.name.removeprefix(BASE + '.')} {message}"
            if record.exc_info:   # 예외는 어디서 났는지(추적)를 함께 적는다
                line += "\n" + logging.Formatter().formatException(record.exc_info)
            self.stream.write(redact(line) + "\n")
            self.stream.flush()
        except Exception:   # 로그를 쓰다 난 문제로 프로그램이 죽으면 안 된다
            self.handleError(record)

    def close_stream(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None

    def close(self) -> None:
        self.close_stream()
        super().close()


def setup_logging(base_dir: Path | None = None, clock=None) -> logging.Logger:
    """로그 파일 두 개를 연결한다. 여러 번 불러도 한 번 부른 것과 같다."""
    # 왜: Streamlit 은 화면을 그릴 때마다 스크립트를 다시 돌린다. 부를 때마다 연결이 늘면 같은 줄이 여러 번 적히므로, 예전 연결을 떼고 다시 단다. 어디: 프로그램 시작.
    # 교안: PRD 12-1 서비스 하네스. error.log 에는 ERROR 이상만 — "열어 보면 반드시 봐야 할 것만" 있게 한다.
    logger = logging.getLogger(BASE)
    for old in [h for h in logger.handlers if isinstance(h, DailyFileHandler)]:
        logger.removeHandler(old)
        old.close()
    base_dir, clock = Path(base_dir or ROOT / config.LOG_DIR), clock or datetime.now
    logger.addHandler(DailyFileHandler("debug.log", logging.DEBUG, base_dir, clock))
    logger.addHandler(DailyFileHandler("error.log", logging.ERROR, base_dir, clock))
    logger.setLevel(logging.DEBUG)
    logger.propagate = False   # 다른 곳(터미널 · 라이브러리 설정)으로 한 번 더 나가지 않게
    return logger


def get_logger(name: str) -> logging.Logger:
    """모듈마다 이름을 붙여 쓴다. 예: get_logger("tools.weather")"""
    return logging.getLogger(f"{BASE}.{name}")


if __name__ == "__main__":   # 직접 실행하면 두 파일이 만들어지는지 볼 수 있다:  python -m harness.logs
    setup_logging()
    log = get_logger("harness.logs")
    log.debug("로그 장치 점검: 디버그 한 줄")
    log.info("로그 장치 점검: 정보 한 줄")
    log.warning("로그 장치 점검: 경고 한 줄 (error.log 에는 없어야 한다)")
    log.error("로그 장치 점검: 오류 한 줄 serviceKey=abcd1234efgh")
    try:
        1 / 0
    except ZeroDivisionError:
        log.exception("로그 장치 점검: 예외와 추적")
    print("쓴 곳:", ROOT / config.LOG_DIR / f"{datetime.now():%Y-%m-%d}", file=sys.stderr)
