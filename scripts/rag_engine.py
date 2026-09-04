# -*- coding: utf-8 -*-
"""
[T6] RAG(검색 증강 생성) 파이프라인 기반 구축

역할은 순서대로 3단계다.
    ① 검색(Retrieval)   : search_engine.py의 하이브리드 검색(T2 벡터DB + T3 BM25)을 그대로 재사용
    ② 컨텍스트 조립(Context Building) : 검색된 조항을 "[규정명] 제0조(제목): 본문..." 형식으로 정리
    ③ 답변 생성(Generation) : 조립된 컨텍스트만 근거로 삼도록 지시하는 프롬프트를 만들어 LLM에게 전달

이 모듈은 기존 scripts/search_engine.py, scripts/api_server.py, web/ 폴더를 전혀 건드리지 않는다.
(T7 단계에서 /api/ask 엔드포인트가 이 모듈을 불러와 연결할 예정)

실행 방법 (프로젝트 루트에서):
    python scripts/rag_engine.py
"""
import json
import os
import re
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from search_engine import SearchEngine

# --------------------------------------------------------------------------
# 답변 생성에 사용할 검색 결과 개수 (참고자료로 LLM에 전달할 상위 N개 조항)
TOP_N_FOR_CONTEXT = 5

NOT_FOUND_MESSAGE = "해당 내용은 규정에서 찾을 수 없습니다."

# T9 튜닝: search_engine.py의 관련성 최소 기준(MIN_VEC_SIM/MIN_BM25_SCORE)은 검색 결과
# "목록 표시"용으로는 적절하지만("서울"처럼 단어 하나만 일치해도 참고용으로 보여줄 수 있음),
# RAG가 LLM을 호출해 답변을 생성하려면 더 확실한 근거가 필요하다.
# 실측 결과: 실제로 관련 있는 질문의 최상위 결과 점수는 0.74~0.99, 완전히 무관한 질문
# (예: "오늘 서울 날씨가 어때?" — "서울"이라는 단어만 우연히 일치)의 최상위 점수는 0.4로,
# 뚜렷한 격차가 있어 0.5를 기준으로 삼았다.
MIN_TOP_SCORE_FOR_ANSWER = 0.5

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
REGULATIONS_PATH = os.path.join(DATA_DIR, "regulations.json")

SYSTEM_PROMPT = (
    "너는 경상국립대학교 규정 안내원이다. 아래 [참고자료]에 있는 내용만 근거로 답하라.\n"
    "참고자료에 없는 내용은 답하지 말고 '해당 내용은 규정에서 찾을 수 없습니다'라고 답하라.\n"
    "참고자료에 적힌 문장을 그대로 인용하거나 쉽게 풀어 쓰는 것은 되지만, 참고자료에 없는 "
    "숫자·날짜·기간을 스스로 계산하거나 추측해서 덧붙이지 마라 (예: '수업일수 2분의 1 경과 "
    "전'이라고만 적혀 있으면 그렇게만 답하고, 이를 '몇 주 전'처럼 임의로 환산하지 마라).\n"
    "답변 끝에는 근거로 사용한 규정명과 조항을 반드시 표시하라."
)


# ============================================================== ① 검색
def retrieve(query: str, top_k: int = TOP_N_FOR_CONTEXT, sources=None, categories=None):
    """search_engine.py의 하이브리드 검색을 그대로 호출해 관련 조항 상위 N개를 가져온다.

    search_engine.py는 이미 "관련성 최소 기준"(MIN_VEC_SIM, MIN_BM25_SCORE)으로 무관한
    후보를 걸러내므로, 여기서는 그 결과를 그대로 신뢰해 재사용한다(로직 중복 방지).

    [T12] rerank=True로 호출해 cross-encoder 재순위화를 적용한다. AI 질문하기는 어차피
    LLM 답변 생성에 수십 초가 걸리므로, 재순위화가 추가하는 수 초~10여 초는 상대적으로
    부담이 적고, 그 대신 질문형 자연어 질의의 검색 정확도가 크게 개선된다. (반대로 즉시
    응답이 생명인 /api/search의 일반 검색은 재순위화 없이 그대로 빠르게 응답한다)
    """
    engine = SearchEngine.get()
    return engine.search(query, top_k=top_k, sources=sources, categories=categories, rerank=True)


# ============================================================== ② 컨텍스트 조립
def build_context(search_result: dict) -> str:
    """검색 결과(조항 목록)를 LLM에게 줄 참고자료 텍스트로 정리한다.

    형식: "[규정명] 제0조(제목): 본문..."

    검색 결과 카드에 표시되는 "본문 발췌(snippet)"는 검색어 주변 약 90자만 잘라낸
    미리보기라서, 정작 물어본 답(구체적인 숫자·기준 등)이 그 바깥에 있으면 LLM이
    보지 못하고 "찾을 수 없습니다"라고 잘못 거절하는 경우가 있었다. 그래서 LLM에게는
    스니펫이 아니라 해당 조항(청크)의 전체 원문을 넘긴다. (화면의 검색 결과 카드
    발췌 표시는 기존 그대로 유지 — 이 함수만 참고자료 조립 방식을 바꾼다)
    조항 단위 청크는 원래 짧아서(보통 300~600자) 전체 원문을 써도 입력 길이가
    크게 늘지 않고, 답변 시간을 좌우하는 것은 입력 길이가 아니라 출력(답변) 길이다.
    """
    engine = SearchEngine.get()
    blocks = []
    for r in search_result["results"]:
        title = f"({r['article_title']})" if r.get("article_title") else ""
        location = r["location"]  # "제0조" 또는 "제0조 제0항"
        chunk = engine.get_chunk(r["chunk_id"])
        body = chunk["text"] if chunk else r["snippet"]  # 못 찾으면 스니펫으로 대체(안전장치)
        blocks.append(f"[{r['name']}] {location}{title}: {body}")
    return "\n".join(blocks)


# ============================================================== ③ 답변 생성 - LLM 추상화
class LLMBackend:
    """LLM 연결부 추상 클래스. 로컬 모델/외부 API를 자유롭게 교체할 수 있도록 인터페이스만 정의한다."""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError

    def is_available(self) -> bool:
        raise NotImplementedError


class LocalHFBackend(LLMBackend):
    """기본값: 허깅페이스 transformers로 로컬에서 무료 실행 가능한 한국어 지원 오픈소스 모델.

    모델: Qwen/Qwen2.5-1.5B-Instruct
    선택 이유 (실측 비교 후 결정):
      - 한국어를 포함한 다국어 instruct 모델로 별도 인증(gated) 없이 누구나 다운로드 가능,
        Apache 2.0 라이선스로 상업/비상업 모두 자유롭게 사용 가능
      - 처음에는 더 가벼운 Qwen2.5-0.5B-Instruct로 검증했으나, 지시(참고자료 밖 내용을
        답하지 말라)를 제대로 따르지 못하고 구체적 수치를 지어내는 환각이 실측 확인되었다.
      - Qwen2.5-1.5B-Instruct는 동일 프롬프트에서 참고자료에 없는 내용은 정확히
        "규정에서 찾을 수 없습니다"로 답하고, 참고자료에 있는 내용은 정확히 인용해 답하는
        것을 실측으로 확인해 최종 채택했다.
      - CPU(GPU 없는 환경)에서도 수십 초 내 응답 가능 (실측: 로딩 약 20~45초,
        200토큰 생성 약 8초, 12코어 CPU 기준)
      - 필요 시 환경변수 GNU_RAG_LOCAL_MODEL로 다른 모델로 손쉽게 교체 가능
    """

    MODEL_NAME = os.environ.get("GNU_RAG_LOCAL_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._load_failed = False
        # T10 버그 수정: 이전 요청이 타임아웃되어도(웹 응답은 이미 나갔어도) 그 요청의
        # model.generate() 스레드는 계속 CPU에서 실행 중일 수 있다(transformers는 생성
        # 중간에 취소하는 기능이 없음). 이 상태에서 새 요청이 같은 모델로 동시에
        # generate()를 또 호출하면 두 연산이 CPU를 나눠 쓰며 서로 훨씬 느려지고,
        # 다음 질문들도 계속 그 여파로 느려지는 "연쇄 지연"이 생긴다.
        # 아래 락으로 generate()는 항상 한 번에 하나만 실행되게 강제하고, 이미 다른
        # 요청이 실행 중이면 새 요청은 기다리지 않고 즉시 "바쁨" 오류로 실패시켜
        # 검색 결과만이라도 빠르게 반환하게 한다 (api_server.py의 기존 예외 처리 재사용).
        self._generate_lock = threading.Lock()

    def _lazy_load(self):
        if self._model is not None or self._load_failed:
            return
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            print(f"[RAG] 로컬 LLM 로딩 중... ({self.MODEL_NAME})")
            self._tokenizer = AutoTokenizer.from_pretrained(self.MODEL_NAME)
            self._model = AutoModelForCausalLM.from_pretrained(self.MODEL_NAME)
            print("[RAG] 로컬 LLM 로딩 완료")
        except Exception as e:
            print(f"[RAG] 경고: 로컬 LLM 로딩 실패 ({e}). 생성 기능을 사용할 수 없습니다.")
            self._load_failed = True

    def is_available(self) -> bool:
        self._lazy_load()
        return self._model is not None

    # 실측 비교로 검증된, 1.5B급 소형 로컬 모델에 최적화한 규칙 문구.
    # (SYSTEM_PROMPT와 의미는 동일하되, 지시 순응도를 높이기 위해 아래 3가지를 조정했다)
    #   1) system 역할 대신 "참고자료 → 질문 → 규칙" 순서로 하나의 user 메시지에 담음
    #      (system 역할 지시는 소형 모델이 무시하거나 과잉 거부하는 경향이 실측 확인됨)
    #   2) "규정에서 찾을 수 없습니다" 문구를 답변 규칙 앞부분에 먼저 두면 모델이 그 문구
    #      자체에 앵커링(anchoring)되어 답이 있는 질문에도 거부하는 경향이 있어,
    #      "답이 있으면 먼저 명확히 답하라"는 지시를 앞에 배치해 완화함
    #   3) 여러 조항이 섞인 컨텍스트에서도 정답 조항 인용이 유지되는지 실측으로 확인함
    _LOCAL_RULES_TEMPLATE = (
        "너는 대학 규정 안내원이다. 위 참고자료에 있는 내용만 근거로 답하라. "
        "참고자료에 답이 있으면 그 내용을 근거로 명확히 답하라. "
        "참고자료에 없는 내용일 때에만 '해당 내용은 규정에서 찾을 수 없습니다'라고 답하라. "
        "참고자료에 적힌 문장을 그대로 쓰거나 쉽게 풀어 설명하는 것은 좋지만, 참고자료에 없는 "
        "숫자·날짜·기간을 스스로 계산하거나 짐작해서 덧붙이지 마라 "
        "(예: 참고자료가 '수업일수 2분의 1 경과 전'이라고만 하면 그대로만 답하고, "
        "이를 '몇 주 전'처럼 임의로 환산해서 말하지 마라). "
        "답변 끝에는 근거로 사용한 규정명과 조항을 반드시 표시하라."
    )

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self._lazy_load()
        if self._model is None:
            raise RuntimeError("로컬 LLM을 사용할 수 없습니다.")

        # 이미 다른 요청이 generate() 중이면 기다리지 않고 즉시 실패시킨다
        # (기다리게 하면 두 생성이 CPU를 나눠 쓰며 둘 다 훨씬 느려지고, 그 뒤로 들어오는
        # 요청까지 계속 밀려서 느려지는 연쇄 지연이 생기기 때문).
        if not self._generate_lock.acquire(blocking=False):
            raise RuntimeError(
                "AI가 이미 다른 질문에 대한 답변을 생성하고 있어, 지금 요청은 처리할 수 "
                "없습니다. 잠시 후 다시 시도해주세요.")
        try:
            combined = f"{user_prompt}\n\n{self._LOCAL_RULES_TEMPLATE}"
            messages = [{"role": "user", "content": combined}]
            text = self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True)
            inputs = self._tokenizer([text], return_tensors="pt")
            # 실측상 실제 답변+근거 표시는 250토큰 이내로 끝나는 경우가 대부분이라,
            # 상한을 400에서 낮춰 불필요하게 긴 생성 시간을 줄인다. 환경변수로 조정 가능.
            max_new_tokens = int(os.environ.get("GNU_RAG_MAX_NEW_TOKENS", "260"))
            output = self._model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
        finally:
            self._generate_lock.release()
        generated = output[0][inputs["input_ids"].shape[1]:]
        return self._tokenizer.decode(generated, skip_special_tokens=True).strip()


class OpenAICompatibleBackend(LLMBackend):
    """옵션: 환경변수(API 키)가 설정되어 있으면 OpenAI 호환 방식의 외부 API를 대신 사용한다.

    환경변수:
      - GNU_RAG_API_KEY   : API 키 (필수, 없으면 이 백엔드는 비활성화되어 로컬 모델로 대체됨)
      - GNU_RAG_API_BASE  : API Base URL (기본값: https://api.openai.com/v1, OpenAI 호환
                             엔드포인트라면 다른 서비스로도 교체 가능)
      - GNU_RAG_API_MODEL : 모델명 (기본값: gpt-4o-mini)
    """

    def __init__(self):
        self.api_key = os.environ.get("GNU_RAG_API_KEY", "")
        self.api_base = os.environ.get("GNU_RAG_API_BASE", "https://api.openai.com/v1")
        self.model_name = os.environ.get("GNU_RAG_API_MODEL", "gpt-4o-mini")
        self._client = None
        self._init_failed = False

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _lazy_client(self):
        if self._client is not None or self._init_failed:
            return
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key, base_url=self.api_base)
        except Exception as e:
            print(f"[RAG] 경고: 외부 API 클라이언트 초기화 실패 ({e}).")
            self._init_failed = True

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self._lazy_client()
        if self._client is None:
            raise RuntimeError("외부 API를 사용할 수 없습니다.")
        resp = self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()


def get_llm_backend() -> LLMBackend:
    """환경변수(GNU_RAG_API_KEY)가 있으면 외부 API를, 없으면 로컬 모델을 우선 사용한다.
    (교체 가능 구조: 이 함수만 바꾸면 다른 조합으로도 쉽게 전환 가능)
    """
    api_backend = OpenAICompatibleBackend()
    if api_backend.is_available():
        print(f"[RAG] 외부 API 백엔드 사용: {api_backend.api_base} ({api_backend.model_name})")
        return api_backend
    return LocalHFBackend()


_default_backend = None


def _get_default_backend() -> LLMBackend:
    global _default_backend
    if _default_backend is None:
        _default_backend = get_llm_backend()
    return _default_backend


def _format_sources(search_result: dict) -> str:
    """답변 끝에 붙일 근거 출처(규정명 + 조항) 목록을 만든다."""
    lines = []
    for r in search_result["results"]:
        lines.append(f"- {r['name']} {r['location']}")
    return "\n".join(lines)


# ============================================================== T9: 환각 방지 가드레일
_all_reg_names_cache = None


def _all_regulation_names():
    """전체 규정명 목록을 1회만 로딩해 캐시한다 (길이 내림차순으로 정렬).

    길이 내림차순으로 매칭해야, 짧은 규정명이 더 긴 규정명의 부분 문자열이라서
    오탐(중복 매칭)되는 것을 방지할 수 있다 (아래 _find_uncited_regulation_mentions 참고).
    """
    global _all_reg_names_cache
    if _all_reg_names_cache is None:
        with open(REGULATIONS_PATH, encoding="utf-8") as f:
            regs = json.load(f)
        _all_reg_names_cache = sorted({r["name"] for r in regs}, key=len, reverse=True)
    return _all_reg_names_cache


def _find_uncited_regulation_mentions(answer_text: str, allowed_names) -> list:
    """답변 텍스트에 등장하는 규정명 중, 이번 검색의 근거 조항(allowed_names)에는
    없는 것을 찾아낸다 — LLM이 참고자료 밖의 규정명을 지어내 인용했는지 탐지한다.

    긴 규정명부터 매칭 후 그 부분을 공백으로 치환하면서 검사하므로, 짧은 규정명이
    긴 규정명 문자열 안에 포함되어 있어 중복으로 잘못 잡히는 것을 방지한다.
    """
    remaining = answer_text
    mentioned = []
    for name in _all_regulation_names():
        if name in remaining:
            mentioned.append(name)
            remaining = remaining.replace(name, " " * len(name))
    allowed = set(allowed_names)
    return [n for n in mentioned if n not in allowed]


GUARDRAIL_WARNING_TEMPLATE = (
    "\n\n⚠️ [자동 검증 경고] 이 답변에는 근거 조항 목록에 없는 규정명({names})이 "
    "포함되어 있습니다. 실제 근거 조항을 기준으로 다시 확인해주세요."
)


def apply_citation_guardrail(final_answer: str, search_result: dict) -> str:
    """LLM이 검색 근거(related_regulations)에 없는 규정명을 인용하면 경고를 덧붙인다.

    (환각 방지: 답변 내용을 함부로 삭제/수정하지 않고, 검증이 필요함을 명시적으로
    경고해 사용자가 원본 규정을 다시 확인하도록 유도하는 방식을 택했다.)
    """
    uncited = _find_uncited_regulation_mentions(final_answer, search_result["related_regulations"])
    if not uncited:
        return final_answer
    return final_answer + GUARDRAIL_WARNING_TEMPLATE.format(names=", ".join(uncited))


NUMBER_GUARDRAIL_WARNING_TEMPLATE = (
    "\n\n⚠️ [자동 검증 경고] 이 답변에 참고자료 원문에는 없는 숫자({numbers})가 "
    "포함되어 있습니다. AI가 스스로 계산했거나 지어냈을 수 있으니, 위 근거 조항의 "
    "원문을 직접 확인해주세요."
)


def _answer_body_before_sources(answer_text: str) -> str:
    """[근거 조항] 목록이나 가드레일 경고가 붙기 전, LLM이 실제로 생성한 문장 부분만 추출."""
    for marker in ("[근거 조항]", "⚠️"):
        idx = answer_text.find(marker)
        if idx >= 0:
            answer_text = answer_text[:idx]
    return answer_text


def apply_number_guardrail(final_answer: str, context: str) -> str:
    """답변 문장에 등장하는 숫자 중 참고자료(컨텍스트) 원문에는 없는 숫자가 있으면 경고를
    붙인다. LLM이 "수업일수 2분의 1 경과 전"처럼 서술된 조건을 "약 2주 전"과 같이 스스로
    환산·추정해 지어내는 환각 패턴을 잡아내기 위한 안전장치다.
    """
    body = _answer_body_before_sources(final_answer)
    answer_numbers = set(re.findall(r"\d+", body))
    context_numbers = set(re.findall(r"\d+", context))
    hallucinated = sorted(answer_numbers - context_numbers, key=int)
    if not hallucinated:
        return final_answer
    return final_answer + NUMBER_GUARDRAIL_WARNING_TEMPLATE.format(numbers=", ".join(hallucinated))


# ============================================================== 통합 파이프라인
def answer(query: str, top_k: int = TOP_N_FOR_CONTEXT, sources=None, categories=None,
           llm=None) -> dict:
    """①검색 → ②컨텍스트 조립 → ③답변 생성을 순서대로 수행해 최종 결과를 반환한다.

    반환값:
        {
            "query": 질문,
            "search_result": search_engine.search()의 원본 결과,
            "context": 조립된 참고자료 텍스트,
            "answer": 최종 답변 (근거 출처 포함),
            "used_llm": LLM을 실제로 호출했는지 여부,
        }
    """
    # ① 검색
    search_result = retrieve(query, top_k=top_k, sources=sources, categories=categories)

    # 관련 조항이 없거나(search_engine 기준 0건), 최상위 결과 점수가 너무 낮으면
    # (예: 흔한 단어 하나만 우연히 일치) LLM 호출 없이 즉시 반환한다.
    # → 불필요한 LLM 호출 방지 + 환각 예방 (T9: 관련성 기준 미달 시 답변 생성 자체를 차단)
    top_score = search_result["results"][0]["score"] if search_result["results"] else 0.0
    if search_result["total"] == 0 or top_score < MIN_TOP_SCORE_FOR_ANSWER:
        return {
            "query": query,
            "search_result": search_result,
            "context": "",
            "answer": NOT_FOUND_MESSAGE,
            "used_llm": False,
            "found": False,
        }

    # ② 컨텍스트 조립
    context = build_context(search_result)

    # ③ 답변 생성
    backend = llm or _get_default_backend()
    if not backend.is_available():
        # 로컬/외부 LLM 어느 쪽도 사용할 수 없는 환경 → 에러 대신 검색 결과만 안전하게 반환
        fallback = ("[생성 불가: 사용 가능한 LLM이 없어 검색 결과만 반환합니다]\n\n"
                    + _format_sources(search_result))
        return {
            "query": query,
            "search_result": search_result,
            "context": context,
            "answer": fallback,
            "used_llm": False,
            "found": True,
        }

    user_prompt = f"[참고자료]\n{context}\n\n[질문]\n{query}"
    try:
        generated = backend.generate(SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        # LLM 호출 자체가 실패한 경우에도 에러를 내지 않고 검색 결과만 안전하게 반환
        print(f"[RAG] 경고: LLM 답변 생성 실패 ({e}). 검색 결과만 반환합니다.")
        fallback = (f"[생성 불가: {e}]\n\n" + _format_sources(search_result))
        return {
            "query": query,
            "search_result": search_result,
            "context": context,
            "answer": fallback,
            "used_llm": False,
            "found": True,
        }

    # 모델이 근거 출처를 빠뜨렸을 수 있으니, 항상 검색 기반 출처 목록을 답변 끝에 덧붙여 보장한다.
    final_answer = generated.strip()
    sources_block = _format_sources(search_result)
    if sources_block not in final_answer:
        final_answer = f"{final_answer}\n\n[근거 조항]\n{sources_block}"

    # T9: 근거 조항 목록에 없는 규정명을 인용했는지 검사해 경고를 덧붙인다 (환각 방지 가드레일)
    final_answer = apply_citation_guardrail(final_answer, search_result)
    # 참고자료 원문에 없는 숫자(스스로 계산/추정한 숫자)를 인용했는지도 함께 검사한다
    final_answer = apply_number_guardrail(final_answer, context)

    return {
        "query": query,
        "search_result": search_result,
        "context": context,
        "answer": final_answer,
        "used_llm": True,
        "found": True,
    }


# ============================================================== 직접 실행 시 테스트
if __name__ == "__main__":
    TEST_QUERY = "연구비 지원 한도가 얼마야?"

    print("=" * 70)
    print(f"[질문] {TEST_QUERY}")
    print("=" * 70)

    result = answer(TEST_QUERY)

    print("\n" + "-" * 70)
    print(f"① 검색된 조항 목록 (총 {result['search_result']['total']}건)")
    print("-" * 70)
    for i, r in enumerate(result["search_result"]["results"], 1):
        print(f"{i}. [{r['name']}] {r['location']} (score={r['score']}) - {r['snippet']}")

    print("\n" + "-" * 70)
    print("② 조립된 컨텍스트 (LLM에 전달되는 참고자료)")
    print("-" * 70)
    print(result["context"] if result["context"] else "(참고자료 없음)")

    print("\n" + "-" * 70)
    print(f"③ 최종 답변 (LLM 사용 여부: {result['used_llm']})")
    print("-" * 70)
    print(result["answer"])

    # 관련 조항이 없을 때의 동작도 함께 확인 (환각 예방 검증)
    print("\n" + "=" * 70)
    NO_MATCH_QUERY = "오늘 서울 날씨가 어때?"
    print(f"[관련 없는 질문 테스트] {NO_MATCH_QUERY}")
    print("=" * 70)
    result2 = answer(NO_MATCH_QUERY)
    print(f"검색 결과 건수: {result2['search_result']['total']}")
    print(f"최종 답변: {result2['answer']}")
