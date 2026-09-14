# -*- coding: utf-8 -*-
"""
[T3] 통합 검색 엔진 API 서버 (FastAPI)

실행 방법:
    python -m uvicorn scripts.api_server:app --reload --port 8000
    (프로젝트 폴더 루트에서 실행)

API 문서(Swagger UI): http://127.0.0.1:8000/docs
"""
import json
import os
import re
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# T4: 웹 화면(web 폴더)을 API 서버가 함께 서빙한다.
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from search_engine import SearchEngine
import rag_engine

app = FastAPI(
    title="경상국립대학교 규정 통합 검색 API",
    description="대학 규정 + 산학협력단 규정을 조·항 단위로 통합 검색하는 하이브리드(의미+키워드) 검색 API",
    version="1.0.0",
)

# T4(웹 화면)에서 다른 포트/파일에서 호출할 수 있도록 CORS 전체 허용 (내부망 서비스 기준)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

_engine: Optional[SearchEngine] = None


def get_engine() -> SearchEngine:
    global _engine
    if _engine is None:
        _engine = SearchEngine.get()
    return _engine


@app.on_event("startup")
def _startup():
    # 서버 기동 시 모델·인덱스를 미리 로딩해, 첫 검색 요청부터 3초 이내 응답이 가능하게 한다.
    engine = get_engine()

    # [T23] 재순위화 모델(cross-encoder)은 지금까지 첫 AI 질문에서야 로딩돼 첫 사용자만 20~40초를
    # 더 기다렸다. 검색 서비스는 즉시 열어두고(위 get_engine 완료), 재순위화 모델과 외부 LLM
    # 클라이언트는 백그라운드 스레드에서 미리 준비한다. 실패해도 기존 지연 로딩 경로가 그대로 동작.
    def _warm_up():
        try:
            engine._lazy_reranker()
        except Exception as e:  # pragma: no cover
            print(f"[서버] 재순위화 모델 워밍업 실패(지연 로딩으로 대체): {e}")
        try:
            import rag_engine
            backend = rag_engine._get_default_backend()
            if hasattr(backend, "_lazy_client"):
                backend._lazy_client()
            if hasattr(backend, "_lazy_load"):   # 로컬 Qwen(대체 백엔드)도 기동 시 미리 로딩
                backend._lazy_load()
        except Exception as e:  # pragma: no cover
            print(f"[서버] LLM 백엔드 워밍업 실패(지연 로딩으로 대체): {e}")
        print("[서버] 워밍업 완료: 재순위화 모델·LLM 백엔드 준비됨")

    threading.Thread(target=_warm_up, name="warmup", daemon=True).start()


class SearchResultItem(BaseModel):
    chunk_id: str
    reg_id: str
    source: str            # 대학 / 산학협력단
    category: str          # 학칙 / 규정 / 지침 / 제N편 …
    name: str               # 규정명
    article: str            # 제0조
    article_title: str = ""
    clause: str = ""         # 제0항
    location: str            # "제0조 제0항" 조합 표시
    snippet: str             # 본문 발췌
    department: str
    contact: str
    source_url: str
    law_url: str = ""
    # [T20] 시행일·개정 정보·현행/폐지 상태
    enforce_date: str = ""
    revision_date: str = ""
    revision_type: str = ""
    rule_no: str = ""
    status: str = "현행"
    also_sources: list[str] = []  # [T24] 다른 출처에도 같은 규정이 있을 때 (예: ["산학협력단"])
    score: float


class SearchResponse(BaseModel):
    query: str
    took_ms: float
    total: int
    results: list[SearchResultItem]
    related_regulations: list[str]
    cached: bool = False  # [T23] 질의 결과 캐시에서 응답했는지 (운영 진단용)


class ChunkDetailResponse(BaseModel):
    chunk_id: str
    reg_id: str
    source: str
    category: str
    name: str
    article: str
    article_title: str = ""
    clause: str = ""
    location: str
    text: str
    department: str
    contact: str
    source_url: str
    law_url: str = ""
    enforce_date: str = ""
    revision_date: str = ""
    revision_type: str = ""
    rule_no: str = ""
    status: str = "현행"


class AskRequest(BaseModel):
    question: str
    top_k: int = 5
    source: Optional[list[str]] = None
    category: Optional[list[str]] = None
    # [T26] 직전 대화 (멀티턴). [{"question": "...", "answer": "..."}] 최근 것부터 최대 3개만 사용
    history: list[dict] = []


class AskResponse(BaseModel):
    query: str
    found: bool
    answer: str
    used_llm: bool
    results: list[SearchResultItem]
    related_regulations: list[str]
    took_ms: float
    suggestions: list[str] = []
    followups: list[str] = []  # [T25] 이어서 물어볼 만한 질문 제안 (근거 조항의 같은 장(章)에서 생성)


class FeedbackRequest(BaseModel):
    """[T25] AI 답변 👍/👎 피드백. 질문자 식별 정보는 받지 않는다."""
    question: str
    vote: str                 # "up" | "down"
    answer_preview: str = ""
    chunk_ids: list[str] = []
    comment: str = ""


class RegulationDetailResponse(BaseModel):
    id: str
    source: str
    category: str
    name: str
    department: str
    contact: str
    source_url: str
    law_url: str = ""
    enforce_date: str = ""
    revision_date: str = ""
    revision_type: str = ""
    rule_no: str = ""
    status: str = "현행"
    full_text: str


# ---------------------------------------------------------------- 엔드포인트
@app.get("/api", tags=["기본"])
def api_info():
    return {
        "name": "경상국립대학교 규정 통합 검색 API",
        "docs": "/docs",
        "endpoints": ["/api/search", "/api/ask", "/api/chunks/{chunk_id}",
                     "/api/regulations/{reg_id}", "/api/filters"],
    }


_UNIV_CATEGORY_ORDER = {"학칙": 0, "규정": 1, "지침": 2}


def _category_sort_key(cat: str):
    """대학은 학칙→규정→지침, 산학협력단은 '제N편' 번호순으로 정렬한다."""
    if cat in _UNIV_CATEGORY_ORDER:
        return (0, _UNIV_CATEGORY_ORDER[cat], cat)
    m = re.match(r"제\s*(\d+)\s*편", cat)
    if m:
        return (1, int(m.group(1)), cat)
    return (2, 0, cat)


@app.get("/api/filters", tags=["검색"], summary="사용 가능한 필터 목록(출처/카테고리) 조회")
def get_filters():
    """[T17] 카테고리는 출처별로 체계가 다르다(대학: 학칙/규정/지침, 산학협력단: 제1편~제7편).
    한 줄에 섞어 보여주면 사용자가 구분하기 어려우므로 출처별로 나눠서 함께 내려준다.
    (`categories`는 기존 호환용으로 그대로 유지) 데이터 기준일도 함께 내려 푸터에 표시한다."""
    engine = get_engine()
    sources = sorted({c["source"] for c in engine.chunks})
    categories = sorted({c["category"] for c in engine.chunks}, key=_category_sort_key)
    by_source = {}
    for c in engine.chunks:
        by_source.setdefault(c["source"], set()).add(c["category"])
    categories_by_source = {s: sorted(v, key=_category_sort_key) for s, v in by_source.items()}

    meta = {}
    meta_path = os.path.join(DATA_DIR, "dataset_meta.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            meta = {}
    return {
        "sources": sources,
        "categories": categories,
        "categories_by_source": categories_by_source,
        "data_date": meta.get("data_date", ""),
        "total_regulations": meta.get("total_regulations", len({c["reg_id"] for c in engine.chunks})),
    }


@app.get("/api/search", response_model=SearchResponse, tags=["검색"],
         summary="규정 통합 검색 (하이브리드: 의미 검색 + 키워드 검색)")
def search(
    q: str = Query(..., min_length=1, description="검색어 (단어 또는 자연어 문장)"),
    top_k: int = Query(10, ge=1, le=50, description="반환할 결과 개수"),
    source: Optional[list[str]] = Query(
        None, description="출처 필터: 대학, 산학협력단 (복수 선택 가능)"),
    category: Optional[list[str]] = Query(
        None, description="카테고리 필터: 학칙, 규정, 지침, 제N편… (복수 선택 가능)"),
    include_repealed: bool = Query(
        False, description="[T20] 폐지된 규정도 결과에 포함할지 (기본: 제외)"),
    since: str = Query("", description="[T27] 이 날짜(YYYY-MM-DD) 이후 시행·개정된 규정만"),
    sort: str = Query("relevance", description="[T27] relevance(관련도) | date(시행일 최신순)"),
):
    engine = get_engine()
    t0 = time.time()
    if sort not in ("relevance", "date"):
        raise HTTPException(status_code=400, detail="sort는 relevance 또는 date 이어야 합니다.")
    if since and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", since):
        raise HTTPException(status_code=400, detail="since는 YYYY-MM-DD 형식이어야 합니다.")
    try:
        result = engine.search(q, top_k=top_k, sources=source, categories=category,
                               include_repealed=include_repealed, since=since, sort=sort)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 중 오류가 발생했습니다: {e}")

    elapsed = time.time() - t0
    if elapsed > 3.0:
        # NFR-01(3초 이내 응답) 위반 시 로그로 남겨 운영 단계(T5)에서 확인할 수 있게 함
        print(f"[경고] 검색 응답이 3초를 초과했습니다: {elapsed:.2f}초 (query='{q}')")

    if result["total"] == 0:
        return {**result, "results": [], "related_regulations": []}
    return result


# /api/ask 전용: 관련 조항이 없을 때 안내할 추천 검색어 (기존 웹 화면의 "결과 없음" 추천 칩과 동일)
ASK_SUGGESTIONS = ["연구비", "휴학", "장학", "등록금", "성적", "수강신청"]

# LLM 답변 생성은 로컬 모델 기준 수십 초가 걸릴 수 있어, 별도 스레드에서 실행 후
# 타임아웃이 지나면 "생성 지연" 안내와 함께 검색 결과만이라도 반환한다.
ASK_TIMEOUT_SEC = float(os.environ.get("GNU_RAG_ASK_TIMEOUT", "60"))
_ask_executor = ThreadPoolExecutor(max_workers=2)

# T10: 질문·답변 로그 (data/rag_logs/YYYY-MM-DD.jsonl, 하루 1개 파일)
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "rag_logs")


def _log_ask_interaction(question: str, chunk_ids: list, answer: str, took_ms: float,
                          found: bool, used_llm: bool, status: str):
    """/api/ask 호출마다 [질문, 근거 조항 id, 답변, 응답시간, 성공/거절 여부]를 로그 파일에 남긴다.

    질문자를 식별할 수 있는 정보(IP, 세션, 계정 등)는 이 API 자체가 받지도 않으므로 저장하지 않는다.
    로그 기록이 실패해도 API 응답 자체에는 영향을 주지 않는다 (안내만 남기고 계속 진행).
    """
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        day = datetime.now().strftime("%Y-%m-%d")
        path = os.path.join(LOGS_DIR, f"{day}.jsonl")
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "question": question,
            "chunk_ids": chunk_ids,
            "answer": answer,
            "took_ms": took_ms,
            "found": found,
            "used_llm": used_llm,
            "status": status,  # answered | refused | fallback_no_llm | timeout | error
            "backend": "external_api" if os.environ.get("GNU_RAG_API_KEY") else "local",
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[RAG] 경고: 질문·답변 로그 기록 실패 ({e})")


def _search_only_fallback(req: "AskRequest", took_ms: float, message: str, status: str):
    """T10: LLM 호출이 실패하거나 시간이 너무 오래 걸릴 때, 에러 대신 검색 결과만이라도
    보여주는 안전장치. 검색 자체는 하이브리드 검색이라 보통 0.1초 내외로 매우 빠르다.
    """
    search_result = get_engine().search(req.question, top_k=req.top_k,
                                         sources=req.source, categories=req.category)
    found = search_result["total"] > 0
    _log_ask_interaction(
        req.question, [r["chunk_id"] for r in search_result["results"]], message,
        took_ms, found, False, status)
    return {
        "query": req.question,
        "found": found,
        "answer": message,
        "used_llm": False,
        "results": search_result["results"],
        "related_regulations": search_result["related_regulations"],
        "took_ms": took_ms,
        "suggestions": [] if found else ASK_SUGGESTIONS,
    }


@app.post("/api/ask", response_model=AskResponse, tags=["AI 질의응답"],
          summary="RAG 기반 AI 답변 생성 (질문 → 관련 조항 검색 → AI 답변)")
def ask(req: AskRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="질문(question)을 입력해주세요.")

    t0 = time.time()
    future = _ask_executor.submit(
        rag_engine.answer, req.question, top_k=req.top_k,
        sources=req.source, categories=req.category, history=req.history[-3:],
    )
    try:
        result = future.result(timeout=ASK_TIMEOUT_SEC)
    except FutureTimeoutError:
        took_ms = round((time.time() - t0) * 1000, 1)
        # 타임아웃이어도 검색 자체는 빠르므로(기존 /api/search 실측 0.1초 내외),
        # 별도로 검색만 재수행해 결과는 보여주고 답변만 "생성 지연"으로 안내한다.
        message = (f"[AI 답변 생성이 {ASK_TIMEOUT_SEC:.0f}초를 초과해 시간 초과되었습니다. "
                   f"아래 검색 결과를 참고해주세요.]")
        return _search_only_fallback(req, took_ms, message, status="timeout")
    except Exception as e:
        # LLM/검색 파이프라인에서 예상 못한 오류가 나도 500 에러로 화면을 막지 않고,
        # 검색 결과만이라도 안전하게 보여주는 "검색 전용 모드"로 전환한다.
        took_ms = round((time.time() - t0) * 1000, 1)
        print(f"[RAG] 경고: /api/ask 처리 중 오류 발생 ({e}). 검색 결과만 반환합니다.")
        message = "[AI 답변 생성 중 오류가 발생해 검색 결과만 반환합니다. 잠시 후 다시 시도해주세요.]"
        try:
            return _search_only_fallback(req, took_ms, message, status="error")
        except Exception as inner_e:
            # 검색 엔진 자체도 응답할 수 없는 극단적인 경우에만 최종적으로 500을 반환한다.
            raise HTTPException(status_code=500, detail=f"답변 생성 중 오류가 발생했습니다: {inner_e}")

    took_ms = round((time.time() - t0) * 1000, 1)
    search_result = result["search_result"]
    found = result["found"]
    used_llm = result["used_llm"]
    status = "answered" if used_llm else ("refused" if not found else "fallback_no_llm")

    _log_ask_interaction(
        req.question, [r["chunk_id"] for r in search_result["results"]], result["answer"],
        took_ms, found, used_llm, status)

    return {
        "query": req.question,
        "found": found,
        "answer": result["answer"],
        "used_llm": used_llm,
        "results": search_result["results"],
        "related_regulations": search_result["related_regulations"],
        "took_ms": took_ms,
        "suggestions": [] if found else ASK_SUGGESTIONS,
        "followups": _followup_questions(search_result["results"], req.question) if found else [],
    }


# ---------------------------------------------------------- [T26] 스트리밍 답변 (SSE)
def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/ask/stream", tags=["AI 질의응답"],
          summary="[T26] RAG 답변 스트리밍 (SSE: meta → token… → done)")
def ask_stream(req: AskRequest):
    """검색이 끝나는 즉시 근거 조항(meta)을 보내고, 답변은 토큰 단위(token)로 흘려보낸 뒤,
    가드레일이 적용된 최종본(done)으로 마무리한다. 화면은 done의 answer로 교체해 표시한다.
    로컬 모델처럼 스트리밍이 안 되는 백엔드는 token 1개(완성문)만 온다."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="질문(question)을 입력해주세요.")

    def gen():
        t0 = time.time()
        try:
            for ev in rag_engine.answer_stream(req.question, top_k=req.top_k, sources=req.source,
                                               categories=req.category, history=req.history[-3:]):
                if ev["type"] == "meta":
                    sr = ev["search_result"]
                    yield _sse("meta", {
                        "found": ev["found"],
                        "results": sr["results"],
                        "related_regulations": sr["related_regulations"],
                    })
                elif ev["type"] == "token":
                    yield _sse("token", {"text": ev["text"]})
                elif ev["type"] == "done":
                    result = ev["result"]
                    took_ms = round((time.time() - t0) * 1000, 1)
                    sr = result["search_result"]
                    found, used_llm = result["found"], result["used_llm"]
                    status = "answered" if used_llm else ("refused" if not found else "fallback_no_llm")
                    _log_ask_interaction(req.question, [r["chunk_id"] for r in sr["results"]],
                                         result["answer"], took_ms, found, used_llm, status)
                    yield _sse("done", {
                        "query": req.question, "found": found, "answer": result["answer"],
                        "used_llm": used_llm, "results": sr["results"],
                        "related_regulations": sr["related_regulations"], "took_ms": took_ms,
                        "suggestions": [] if found else ASK_SUGGESTIONS,
                        "followups": _followup_questions(sr["results"], req.question) if found else [],
                    })
        except Exception as e:
            print(f"[RAG] 경고: /api/ask/stream 처리 중 오류 ({e})")
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------- [T25] 후속 질문 제안 · 피드백 · 인기 검색어
_FOLLOWUP_SKIP_TITLES = {"목적", "정의", "적용범위", "적용 범위", "다른 규정과의 관계", "시행일", "위임"}


def _followup_questions(results: list, question: str, limit: int = 3) -> list:
    """근거 조항과 같은 규정·같은 장(章)에 속한 이웃 조항의 제목으로 이어서 물어볼 질문을 만든다.
    LLM 호출 없이 청크 메타데이터만 사용하므로 비용·지연이 없다. (예: 근거가 '학사관리 규정
    제31조(휴학)'이면 같은 장의 '복학시기', '재입학' → "복학시기은(는) 어떻게 되나요?")"""
    engine = get_engine()
    used_titles = set()
    for r in results:
        if r.get("article_title"):
            used_titles.add(r["article_title"])
    out, seen = [], set()
    for r in results[:2]:  # 상위 2개 근거 조항의 이웃만
        base = engine.get_chunk(r["chunk_id"])
        if not base or not base.get("chapter"):
            continue
        for c in engine.chunks:
            if c["reg_id"] != base["reg_id"] or c.get("chapter") != base.get("chapter"):
                continue
            t = (c.get("article_title") or "").strip()
            if not t or t in used_titles or t in seen or t in _FOLLOWUP_SKIP_TITLES or t in question:
                continue
            if not c["article"].startswith("제"):
                continue
            seen.add(t)
            out.append(f"{t}{_topic_particle(t)} 어떻게 되나요?")
            if len(out) >= limit:
                return out
    return out


def _topic_particle(word: str) -> str:
    """한글 마지막 글자의 받침 유무로 '은'/'는'을 고른다 (복학→복학은, 복학시기→복학시기는)."""
    if not word:
        return "은"
    ch = word.strip()[-1]
    code = ord(ch)
    if 0xAC00 <= code <= 0xD7A3:
        return "은" if (code - 0xAC00) % 28 else "는"
    return "은"


FEEDBACK_DIR = LOGS_DIR


@app.post("/api/feedback", tags=["AI 질의응답"], summary="[T25] AI 답변 👍/👎 피드백 저장")
def feedback(req: FeedbackRequest):
    if req.vote not in ("up", "down"):
        raise HTTPException(status_code=400, detail="vote는 up 또는 down 이어야 합니다.")
    try:
        os.makedirs(FEEDBACK_DIR, exist_ok=True)
        day = datetime.now().strftime("%Y-%m-%d")
        path = os.path.join(FEEDBACK_DIR, f"feedback-{day}.jsonl")
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "question": req.question[:500],
            "vote": req.vote,
            "answer_preview": req.answer_preview[:300],
            "chunk_ids": req.chunk_ids[:10],
            "comment": req.comment[:500],
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[RAG] 경고: 피드백 기록 실패 ({e})")
        raise HTTPException(status_code=500, detail="피드백 저장에 실패했습니다.")
    return {"ok": True}


# 로그가 아직 적을 때를 위한 기본 인기 검색어 (실사용 로그가 쌓이면 자동으로 로그 기반으로 대체됨)
POPULAR_DEFAULTS = ["휴학", "복학", "장학금", "등록금", "수강신청", "졸업 요건", "연구비", "전과", "성적 이의신청", "마이크로디그리"]
_popular_cache = {"at": 0.0, "items": []}


@app.get("/api/popular", tags=["검색"], summary="[T25] 많이 찾는 검색어·질문 (로그 기반, 5분 캐시)")
def popular(limit: int = Query(8, ge=1, le=20)):
    """data/rag_logs/*.jsonl의 질문을 정규화해 빈도순으로 집계한다. 거절(refused)·오류 로그는 제외.
    로그가 적으면 기본 목록으로 채운다. 5분간 캐시."""
    now = time.time()
    if now - _popular_cache["at"] < 300 and _popular_cache["items"]:
        return {"queries": _popular_cache["items"][:limit]}
    counts = {}
    try:
        if os.path.isdir(LOGS_DIR):
            for fn in sorted(os.listdir(LOGS_DIR)):
                if not fn.endswith(".jsonl") or fn.startswith("feedback-"):
                    continue
                with open(os.path.join(LOGS_DIR, fn), encoding="utf-8") as f:
                    for line in f:
                        try:
                            e = json.loads(line)
                        except Exception:
                            continue
                        if e.get("status") not in ("answered",):
                            continue
                        q = re.sub(r"\s+", " ", (e.get("question") or "").strip()).rstrip("?？.!")
                        if 2 <= len(q) <= 40:
                            counts[q] = counts.get(q, 0) + 1
    except Exception as e:
        print(f"[서버] 인기 검색어 집계 실패 ({e})")
    # 2회 이상 물어본 질문만 (1회짜리 시험용·오타 질문 제외), 명백한 테스트 문구 제외
    stop = ("테스트", "test", "asdf", "ㅁㄴㅇ")
    items = [q for q, n in sorted(counts.items(), key=lambda x: -x[1])
             if n >= 2 and not any(s in q.lower() for s in stop)]
    for d in POPULAR_DEFAULTS:
        if d not in items:
            items.append(d)
    _popular_cache.update(at=now, items=items)
    return {"queries": items[:limit]}


@app.get("/api/chunks/{chunk_id:path}", response_model=ChunkDetailResponse,
         tags=["미리보기"], summary="특정 조항(청크) 상세 조회 - 미리보기용")
def get_chunk_detail(chunk_id: str):
    engine = get_engine()
    c = engine.get_chunk(chunk_id)
    if not c:
        raise HTTPException(status_code=404, detail="해당 조항을 찾을 수 없습니다.")
    loc = c["article"] + (f" {c['clause']}" if c.get("clause") else "")
    reg_meta = engine.reg_by_id.get(c["reg_id"], {})
    return {
        "chunk_id": c["chunk_id"], "reg_id": c["reg_id"], "source": c["source"],
        "category": c["category"], "name": c["name"], "article": c["article"],
        "article_title": c.get("article_title", ""), "clause": c.get("clause", ""),
        "location": loc.strip(), "text": c["text"], "department": c["department"],
        "contact": c["contact"], "source_url": c["source_url"],
        "law_url": c.get("law_url", ""),
        "enforce_date": reg_meta.get("enforce_date", ""),
        "revision_date": reg_meta.get("revision_date", ""),
        "revision_type": reg_meta.get("revision_type", ""),
        "rule_no": reg_meta.get("rule_no", ""),
        "status": reg_meta.get("status", "현행"),
    }


@app.get("/api/regulations/{reg_id:path}", response_model=RegulationDetailResponse,
         tags=["미리보기"], summary="규정 전문 조회 - 미리보기(규정 전체) / 사이트 이동용")
def get_regulation_detail(reg_id: str):
    engine = get_engine()
    reg = engine.get_regulation_fulltext(reg_id)
    if not reg:
        raise HTTPException(status_code=404, detail="해당 규정을 찾을 수 없습니다.")
    return reg


# ---------------------------------------------------------- 웹 화면(T4) 서빙
# 반드시 위의 /api/... 라우트들 뒤에 마운트해야 API 경로가 우선 처리된다.
if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="127.0.0.1", port=8000, reload=False)
