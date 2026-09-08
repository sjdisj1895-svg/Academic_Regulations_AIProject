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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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
    get_engine()


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
    score: float


class SearchResponse(BaseModel):
    query: str
    took_ms: float
    total: int
    results: list[SearchResultItem]
    related_regulations: list[str]


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


class AskResponse(BaseModel):
    query: str
    found: bool
    answer: str
    used_llm: bool
    results: list[SearchResultItem]
    related_regulations: list[str]
    took_ms: float
    suggestions: list[str] = []


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
):
    engine = get_engine()
    t0 = time.time()
    try:
        result = engine.search(q, top_k=top_k, sources=source, categories=category,
                               include_repealed=include_repealed)
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
        sources=req.source, categories=req.category,
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
    }


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
