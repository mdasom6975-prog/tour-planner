"""LLM 호출 한 곳. 노드는 llm(system, user, schema) 함수만 받고, 실제 모델은 여기서 만든다. (PRD 12번 모델 두 개 같은 조건)"""
from langchain.chat_models import init_chat_model

import config


def make_llm(provider: str | None = None, on_usage=None):
    # 왜: 결과를 JSON 스키마로 받고, 특정 도구 강제 호출과 temperature 는 쓰지 않는다(최신 Claude 가 받지 않음). 어디: 모든 LLM 노드.
    # 교안: 3일차 구조화 출력(with_structured_output). 테스트에서는 같은 모양의 가짜 함수로 바꾼다.
    provider = provider or config.LLM_PROVIDER
    model = init_chat_model(config.MODELS[provider], **config.MODEL_OPTIONS.get(provider, {}))

    def llm(system: str, user: str, schema):
        if on_usage is None:
            return model.with_structured_output(schema).invoke([("system", system), ("user", user)])
        # 왜: 평가는 문항마다 토큰 수를 재야 한다(PRD 12-2 속도 · 비용). 원본 응답을 함께 받아 사용량만 바깥에 알린다. 어디: 평가 실행기(8-2).
        # 교안: 2일차 Part3 비교표의 토큰 · 비용 열. 화면 경로(on_usage 없음)는 그대로다.
        got = model.with_structured_output(schema, include_raw=True).invoke([("system", system), ("user", user)])
        usage = getattr(got.get("raw"), "usage_metadata", None) or {}
        on_usage({"schema": schema.__name__, "input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0)})
        if got.get("parsing_error") is not None:
            raise got["parsing_error"]
        return got["parsed"]
    return llm
