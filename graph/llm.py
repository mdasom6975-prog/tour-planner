"""LLM 호출 한 곳. 노드는 llm(system, user, schema) 함수만 받고, 실제 모델은 여기서 만든다. (PRD 12번 모델 두 개 같은 조건)"""
from langchain.chat_models import init_chat_model

import config


def make_llm(provider: str | None = None):
    # 왜: 결과를 JSON 스키마로 받고, 특정 도구 강제 호출과 temperature 는 쓰지 않는다(최신 Claude 가 받지 않음). 어디: 모든 LLM 노드.
    # 교안: 3일차 구조화 출력(with_structured_output). 테스트에서는 같은 모양의 가짜 함수로 바꾼다.
    model = init_chat_model(config.MODELS[provider or config.LLM_PROVIDER])

    def llm(system: str, user: str, schema):
        return model.with_structured_output(schema).invoke([("system", system), ("user", user)])
    return llm
