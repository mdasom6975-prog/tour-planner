"""이용시간 문장(hours_text)을 코드가 판정할 수 있는 값으로 바꾸고, 어느 시각에 여는지 가려낸다. LLM 을 쓰지 않는다. (코스 품질 T4)

원칙은 휴무일(ingest/rest_days.py)과 같다: 확실히 읽히는 것만 값을 내고, 애매하면 unknown("확인 필요")으로 둔다.
"문을 닫았는데 간다"고 단정하는 오류보다 "모르겠다"가 낫다. 요일 · 계절 조건이 붙었거나 구간이 여러 갈래면 읽지 않는다.
"""
import re

_T = r"(\d{1,2})\s*:\s*(\d{2})"
_SEP = r"\s*[~\-–～]\s*"
_RANGE = re.compile(_T + _SEP + _T)

# 왜: 요일 · 계절 · 월 조건이 붙은 문장은 방문일에 따라 시간이 달라, 한 구간으로 읽으면 틀린다. 어디: 맨 먼저 거른다(※ 뒤 안내문 포함).
# 교안: 2일차 Part3 평가셋의 "경계 · 엣지" — 틀리기 쉬운 경우를 먼저 따로 다룬다. 요일 조건이 붙으면 unknown 으로 둔다(휴무일 파서와 같은 정책).
_CONDITION = re.compile(r"평일|주말|공휴일|휴일|명절|[월화수목금토일]\s*요일|[월화수목금토일]\s*[~\-,·/]\s*[월화수목금토일](?![가-힣])|하절기|동절기|하계|동계|여름|겨울|봄|가을|"
                        r"계절|성수기|비수기|시즌|\d\s*월|매월|격주|첫째|둘째|셋째|넷째|마지막\s*주(?!문)")

# 영업 중간에 쉬는 시간(이 구간에는 닫은 것으로 본다). "준비시간 15:00~17:00" 와 "(15:00~17:00 브레이크 타임)" 두 순서를 읽는다
_BREAK_WORD = r"(?:준비\s*시간|휴게\s*시간|브레이크\s*타임|휴식\s*시간|점심\s*시간|쉬는\s*시간|재정비\s*시간)"
_BREAKS = (re.compile(_BREAK_WORD + r"\s*[:：]?\s*" + _T + _SEP + _T), re.compile(_T + _SEP + _T + r"\s*" + _BREAK_WORD))
# 영업시간 안의 주문 · 입장 마감 안내(문 닫는 시각이 아니라 읽어도 칸 판정에 쓰지 않는다)
_LAST = re.compile(rf"(?:(?:점심|저녁|브런치|런치|디너)\s*)?(?:마지막|라스트)\s*(?:주문|입장|오더)\s*[:：]?\s*{_T}(?:\s*[,/]\s*{_T})*"
                   rf"|{_T}\s*(?:라스트\s*오더|마지막\s*주문|입장\s*마감|주문\s*마감)"
                   rf"|(?:주문|입장|매표|발권|접수)\s*마감(?:\s*시간)?\s*[:：]?\s*{_T}")
_FILLER = re.compile(r"매일|연중\s*무휴|무휴|영업\s*시간|운영\s*시간|이용\s*시간|관람\s*시간|영업|운영|이용|입니다|:")
_ALLDAY_WORD = re.compile(r"상시|24\s*시간|24시|연중\s*무휴|개방|개장|영업|운영|이용|입장|가능|출입|매일|무휴|자유")

UNKNOWN = {"status": "unknown", "ranges": [], "breaks": []}


def _minutes(h: str, m: str) -> int | None:
    h, m = int(h), int(m)
    return h * 60 + m if (0 <= h <= 24 and 0 <= m < 60 and (h < 24 or m == 0)) else None


def _span(h1, m1, h2, m2):
    """(시작분, 종료분). 종료가 시작보다 이르거나 같으면 자정을 넘기는 영업으로 보고 종료에 24시간을 더한다(18:00~02:00 → 1080~1560)."""
    a, b = _minutes(h1, m1), _minutes(h2, m2)
    if a is None or b is None or a >= 24 * 60:
        return None
    if a == b and a != 0:   # 같은 시각~같은 시각은 하루 종일인지 알 수 없다(00:00~00:00 만 하루 종일로 본다)
        return None
    if b <= a:
        b += 24 * 60
    return (a, b) if b - a <= 24 * 60 else None


def parse_hours(text) -> dict:
    """결과: {"status": "open_close" | "all_day" | "unknown", "ranges": [(시작분, 종료분)], "breaks": [(시작분, 종료분)]}"""
    # 왜: 판정에 쓸 수 있는 모양(하나의 시간대 또는 이어지지 않는 몇 개의 시간대 · 상시 개방 · 쉬는 시간)만 읽는다. 어디: 코스 칸 시각 판정(graph/validate.py hours_closed)과 평가 지표(eval/quality.py).
    # 교안: 2일차 Part1 "형식은 코드로" — 정규식으로 읽을 수 있는 모양만 읽고 나머지는 unknown. 한계: 마지막 주문 · 입장 마감은 읽지 않는다(닫는 시각만 쓴다).
    t = text.strip() if isinstance(text, str) else ""
    if not t or _CONDITION.search(t):
        return dict(UNKNOWN)
    main = t.split("※")[0]   # ※ 뒤는 안내문이라 시간으로 읽지 않는다(요일 · 계절 조건은 위에서 이미 걸렀다)
    breaks = []
    for pattern in _BREAKS:
        for m in pattern.finditer(main):
            span = _span(*m.groups())
            if span is None:
                return dict(UNKNOWN)
            breaks.append(span)
        main = pattern.sub(" ", main)
    main = _LAST.sub(" ", main)
    main = re.sub(r"\(\s*(?:전화\s*)?(?:문의|예약)\s*(?:필수|요망)?\s*\)", " ", main)   # 시간과 무관한 괄호 안내만 버린다. "(단체만 가능)" 같은 조건은 남겨 아래에서 걸러진다
    found = list(_RANGE.finditer(main))
    rest = _RANGE.sub(" ", main)
    if not found:
        # 시간 구간이 없고 "상시 개방" · "24시간" 뿐이면 하루 종일 연다. 그 밖의 문장("공연 별로 상이함" 등)은 읽지 않는다
        word = re.sub(r"[\s\-·/,.()]", "", _ALLDAY_WORD.sub("", rest))
        if re.search(r"상시|24\s*시간|24시", rest) and not word and not breaks:
            return {"status": "all_day", "ranges": [], "breaks": []}
        return dict(UNKNOWN)
    if re.sub(r"[\s\-·/,.()•]", "", _FILLER.sub("", rest)):   # 구간 말고 읽지 못한 말이 남았다(구역별 · 괄호 속 다른 시설 등)
        return dict(UNKNOWN)
    ranges = []
    for m in found:
        span = _span(*m.groups())
        if span is None:
            return dict(UNKNOWN)
        ranges.append(span)
    if len(ranges) == 1 and ranges[0] == (0, 24 * 60):
        return {"status": "all_day", "ranges": [], "breaks": []} if not breaks else dict(UNKNOWN)
    ranges.sort()
    if any(a[1] > b[0] for a, b in zip(ranges, ranges[1:])):   # 구간이 겹치면 갈래(평일 · 주말 등)일 수 있어 읽지 않는다
        return dict(UNKNOWN)
    return {"status": "open_close", "ranges": ranges, "breaks": sorted(breaks)}


def _inside(spans: list, minute: int) -> bool:
    """자정을 넘기는 구간(종료 > 1440)은 이른 새벽 시각(minute + 1440)도 본다."""
    return any(a <= minute < b or a <= minute + 24 * 60 < b for a, b in spans)


def open_at(text, minute: int) -> str:
    """'open' · 'closed' · 'check'(문장을 읽을 수 없어 알 수 없음). 하루 중 minute(0~1439) 시각에 문을 여는가."""
    # 왜: 칸의 대표 시각(config.SLOT_MINUTES)이 개장 · 폐장 · 쉬는 시간 밖이면 닫았다고 판정한다. 읽지 못하면 위반이 아니라 "확인 필요"다. 어디: validate_course 의 hours_closed 규칙.
    # 교안: "숫자와 사실 판정은 코드가". 휴무일(rest_on)의 open · closed · check 와 같은 모양. 한계: 쉬는 시간이 평일 · 주말 따로면 문장 전체를 unknown 으로 둔다.
    got = text if isinstance(text, dict) else parse_hours(text)
    if got["status"] == "all_day":
        return "open"
    if got["status"] != "open_close":
        return "check"
    if not _inside(got["ranges"], minute) or _inside(got["breaks"], minute):
        return "closed"
    return "open"


def hhmm(minute: int) -> str:
    return f"{minute // 60 % 24:02d}:{minute % 60:02d}"


def describe(parsed: dict) -> str:
    """위반 사유 문장에 옮기는 읽은 값. 예: '11:00~20:00, 쉬는 시간 15:00~17:00'. 원문을 그대로 옮기지 않는다."""
    if parsed["status"] == "all_day":
        return "24시간"
    text = ", ".join(f"{hhmm(a)}~{hhmm(b)}" for a, b in parsed["ranges"])
    return text + "".join(f", 쉬는 시간 {hhmm(a)}~{hhmm(b)}" for a, b in parsed["breaks"])
