"""휴무일 문장을 코드가 판정할 수 있는 값으로 바꾼다. LLM 을 쓰지 않는다. (PRD 14번 1단계 중 1-6c)

원칙: 확실할 때만 값을 내고, 애매하면 unknown 으로 둔다.
"쉬는 날인데 연다" 고 판정하는 것이 가장 나쁜 오류이므로, 틀릴 바에는 "확인 필요" 쪽으로 틀린다.
영업시간 해석 · 공휴일 달력 · 실제 코스 검증은 여기 없다.
"""
import re

WEEK = "월화수목금토일"

# 왜: "매월 5번째 월요일" 은 매주가 아니라 특정 주만 쉰다. 요일만 뽑으면 매주 쉰다고 잘못 판정한다. 어디: 맨 먼저 거른다.
# 교안: 2일차 Part3 평가셋의 "경계 · 엣지" 유형 — 규칙이 틀리기 쉬운 경우를 먼저 따로 다룬다.
SOME_WEEKS = re.compile(r"매월|매달|격주|첫째|둘째|셋째|넷째|다섯째|마지막\s*주|\d\s*번째|[1-5]\s*째|[1-5]\s*,\s*[1-5]\s*주")

# 왜: 요일이 문장에 있어도 "쉰다" 는 뜻인지 알 단서가 있어야 한다 ("일요일은 18시까지" 같은 문장을 막는다). 어디: weekly 판정 조건.
# 교안: 2일차 Part3 "규칙 검사: 필수어" — 특정 낱말이 있을 때만 통과시키는 검사.
CLOSED_CUE = re.compile(r"매주|휴무|휴관|휴일|휴점|휴업|쉽니다|쉼")


def _weekdays(text: str) -> list:
    # 왜: "토요일~일요일", "월·화요일", "주말" 처럼 요일을 쓰는 방식이 여러 가지다. 어디: 요일 추출.
    # 교안: 2일차 Part1 "형식은 코드로" — 정규식으로 정해진 모양만 읽는다. 받은 835곳에 실제로 나온 표현만 넣었다.
    # 괄호 안 단서와 ※ 뒤 안내는 "쉬는 요일" 이 아니라 조건이다.
    # 예: "매주 화요일 (단, 월요일이 공휴일인 경우 …)" 의 월요일은 쉬는 날이 아니다.
    main = re.sub(r"\([^)]*\)", " ", text)
    main = re.sub(r"※.*", " ", main, flags=re.S)

    found = set()
    # "/" 나 줄바꿈으로 나뉜 조각 가운데 "매주" 가 있거나 요일만 적힌 조각에서만 읽는다.
    # 예: "매주 월요일 / 일요일을 제외한 공휴일" 의 일요일은 오히려 여는 날이라 읽지 않는다.
    for seg in re.split(r"[/\n]", main):
        seg = seg.strip()
        if not seg or not ("매주" in seg or _only_weekdays(seg)):
            continue
        for a, b in re.findall(rf"([{WEEK}])요일?\s*[~\-]\s*([{WEEK}])요일", seg):
            i, j = WEEK.index(a), WEEK.index(b)
            if i <= j:
                found.update(WEEK[i:j + 1])
        found.update(re.findall(rf"([{WEEK}])요일", seg))
        # "월·화요일" 처럼 앞 요일의 "요일" 이 생략된 경우. "요일" 의 "일" 을 일요일로 읽지 않게 앞 글자를 본다.
        found.update(re.findall(rf"(?<!요)([{WEEK}])\s*[,·]\s*(?=[{WEEK}]요일)", seg))
        if "주말" in seg:
            found.update("토일")
    return [d for d in WEEK if d in found]


def _only_weekdays(text: str) -> bool:
    # 왜: 요일 말고 다른 내용(공휴일 · 명절 · 조건)이 붙어 있으면 사람이 원문을 읽어야 한다. 어디: rest_note 판정.
    # 교안: 팀프로젝트 교안 적용 문서 "기준이 불확실하면 확인 필요" — 통과시키되 확인을 권하는 상태를 따로 둔다.
    rest = re.sub(rf"매주|주말|[{WEEK}]요일|정기\s*휴무|휴무|휴관|휴점|휴일|휴|입니다", "", text)
    rest = re.sub(rf"[{WEEK}](?=\s*[,·/~\-])", "", rest)
    return re.sub(r"[\s,·/~\-.및와과]", "", rest) == ""


# 왜: "매월 둘째, 넷째 월요일" 처럼 몇째 주의 무슨 요일이 쉬는지 적은 문장은 요일만 뽑으면 틀리므로 몇째 주 값을 따로 뽑는다(저장 데이터 87곳). 어디: parse_rest 맨 앞.
# 교안: 2일차 Part1 "형식은 코드로" — 정규식으로 읽을 수 있는 모양만 읽고, 한 문장에 요일이 둘 이상이거나 격주처럼 모호하면 읽지 않는다(unknown 유지).
WEEK_WORDS = {"첫": 1, "둘": 2, "두": 2, "셋": 3, "세": 3, "넷": 4, "네": 4, "다섯": 5}
NTH_SEGMENT = re.compile(r"매월|매달|첫째|둘째|셋째|넷째|다섯째|첫\s*번째|\d\s*번째|[1-5]\s*째|마지막\s*주")


def _nth_rules(text: str):
    """(규칙 목록, 나머지 조각) 또는 읽을 수 없으면 None. 규칙: {"weeks": [1, 3] (-1 = 마지막), "weekday": "월"}"""
    if "격주" in text:
        return None
    main = re.sub(r"\([^)]*\)", " ", text)
    main = re.sub(r"※.*", " ", main, flags=re.S)
    rules, other = [], []
    for seg in re.split(r"[/\n]", main):
        seg = seg.strip()
        if not seg:
            continue
        if not NTH_SEGMENT.search(seg):
            other.append(seg)
            continue
        days = set(re.findall(rf"([{WEEK}])요일", seg))
        if len(days) != 1:
            return None   # 요일이 없거나 둘 이상이면 어느 주가 어느 요일인지 알 수 없다
        day = days.pop()
        prefix = seg[:seg.index(day + "요일")]
        weeks = {WEEK_WORDS[w] for w in re.findall(r"(첫|둘|두|셋|세|넷|네|다섯)\s*(?:번)?\s*째", prefix)}
        weeks |= {int(n) for n in re.findall(r"(?<!\d)([1-5])(?![\d일월])", prefix)}
        if "마지막" in prefix:
            weeks.add(-1)
        if not weeks:
            return None
        rules.append({"weeks": sorted(weeks), "weekday": day})
    return (rules, other) if rules else None


def parse_rest(text: str) -> dict:
    """결과: {"rest_status": always_open | weekly | nth | unknown, "rest_weekdays": [...], "rest_nth": [...], "rest_note": bool}"""
    t = (text or "").strip()
    parsed = _nth_rules(t) if t else None
    if parsed:
        rules, other = parsed
        weekly = _weekdays("/".join(other))
        # 공휴일 · 임시휴관 같은 다른 조건이나 괄호 · ※ 안내가 있으면 원문 확인을 권한다(확정하지 않는다).
        note = bool(re.search(r"[(※]", t)) or any(not _only_weekdays(seg) for seg in other)
        return {"rest_status": "nth", "rest_weekdays": weekly, "rest_nth": rules, "rest_note": note}
    return {**_parse_basic(t), "rest_nth": []}


def _parse_basic(t: str) -> dict:

    # 왜: 정보가 없으면 "연다" 고 가정하지 않는다. 어디: 빈 문장.
    # 교안: 3일차 03 가이드북 "없으면 '찾을 수 없음'" — 모르는 것을 아는 척하지 않는다.
    if not t:
        return {"rest_status": "unknown", "rest_weekdays": [], "rest_note": False}

    if SOME_WEEKS.search(t):
        return {"rest_status": "unknown", "rest_weekdays": [], "rest_note": True}

    days = _weekdays(t)

    # 왜: "연중무휴" 뿐이면 확실하다. 다른 말이 붙으면 통과시키되 원문 확인을 권한다. 어디: 연중무휴 처리.
    # 교안: "숫자와 사실 판정은 코드가" — 확실한 경우만 코드가 확정한다.
    if re.search(r"연중\s*무휴", t):
        if re.fullmatch(r"연중\s*무휴\.?", t):
            return {"rest_status": "always_open", "rest_weekdays": [], "rest_note": False}
        # "연중무휴" 와 요일이 함께 있으면(시설 일부만 쉼, "~ 제외" 등) 어느 쪽으로도 확정하지 않는다.
        if days:
            return {"rest_status": "unknown", "rest_weekdays": [], "rest_note": True}
        return {"rest_status": "always_open", "rest_weekdays": [], "rest_note": True}

    # 왜: 요일이 있고 "쉰다" 는 단서가 있거나 요일만 적힌 문장일 때만 매주 휴무로 확정한다. 어디: weekly 판정.
    # 교안: 2일차 Part3 — 놓치면 안 되는 오류(거짓 통과)는 0건이 합격선이므로 조건을 좁게 잡는다.
    if days and (CLOSED_CUE.search(t) or _only_weekdays(t)):
        return {"rest_status": "weekly", "rest_weekdays": days, "rest_note": not _only_weekdays(t)}

    # 요일이 없거나("설·추석 당일", "공연별 상이") 쉰다는 단서가 없으면 확정하지 않는다.
    return {"rest_status": "unknown", "rest_weekdays": [], "rest_note": True}
