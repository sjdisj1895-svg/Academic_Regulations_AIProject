# -*- coding: utf-8 -*-
"""
[T3] 통합 검색 엔진 API 서버 (FastAPI)

실행 방법:
    python -m uvicorn scripts.api_server:app --reload --port 8000
    (프로젝트 폴더 루트에서 실행)

API 문서(Swagger UI): http://127.0.0.1:8000/docs
"""
import os
import sys
import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# T4: 웹 화면(web 폴더)을 API 서버가 함께 서빙한다.
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from search_engine import SearchEngine

app = FastAPI(
    title="경상국립대학교 규정 통합 검색 API",
    description="대학 규정 + 산학협력단 규정을 조·항 단위로 통합 검색하는 하이브리드(의미+키워드) 검색 API",
    version="1.0.0",
)

# T4(웹 화면)에서 다른 포트/파일에서 호출할 수 있도록 CORS 전체 허용 (내부망 서비스 기준)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

_engine: SearchEngine | None = None


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


class RegulationDetailResponse(BaseModel):
    id: str
    source: str
    category: str
    name: str
    department: str
    contact: str
    source_url: str
    law_url: str = ""
    full_text: str


# ---------------------------------------------------------------- 엔드포인트
@app.get("/api", tags=["기본"])
def api_info():
    return {
        "name": "경상국립대학교 규정 통합 검색 API",
        "docs": "/docs",
        "endpoints": ["/api/search", "/api/chunks/{chunk_id}",
                     "/api/regulations/{reg_id}", "/api/filters"],
    }


@app.get("/api/filters", tags=["검색"], summary="사용 가능한 필터 목록(출처/카테고리) 조회")
def get_filters():
    engine = get_engine()
    sources = sorted({c["source"] for c in engine.chunks})
    categories = sorted({c["category"] for c in engine.chunks})
    return {"sources": sources, "categories": categories}


@app.get("/api/search", response_model=SearchResponse, tags=["검색"],
         summary="규정 통합 검색 (하이브리드: 의미 검색 + 키워드 검색)")
def search(
    q: str = Query(..., min_length=1, description="검색어 (단어 또는 자연어 문장)"),
    top_k: int = Query(10, ge=1, le=50, description="반환할 결과 개수"),
    source: list[str] | None = Query(
        None, description="출처 필터: 대학, 산학협력단 (복수 선택 가능)"),
    category: list[str] | None = Query(
        None, description="카테고리 필터: 학칙, 규정, 지침, 제N편… (복수 선택 가능)"),
):
    engine = get_engine()
    t0 = time.time()
    try:
        result = engine.search(q, top_k=top_k, sources=source, categories=category)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 중 오류가 발생했습니다: {e}")

    elapsed = time.time() - t0
    if elapsed > 3.0:
        # NFR-01(3초 이내 응답) 위반 시 로그로 남겨 운영 단계(T5)에서 확인할 수 있게 함
        print(f"[경고] 검색 응답이 3초를 초과했습니다: {elapsed:.2f}초 (query='{q}')")

    if result["total"] == 0:
        return {**result, "results": [], "related_regulations": []}
    return result


@app.get("/api/chunks/{chunk_id:path}", response_model=ChunkDetailResponse,
         tags=["미리보기"], summary="특정 조항(청크) 상세 조회 - 미리보기용")
def get_chunk_detail(chunk_id: str):
    engine = get_engine()
    c = engine.get_chunk(chunk_id)
    if not c:
        raise HTTPException(status_code=404, detail="해당 조항을 찾을 수 없습니다.")
    loc = c["article"] + (f" {c['clause']}" if c.get("clause") else "")
    return {
        "chunk_id": c["chunk_id"], "reg_id": c["reg_id"], "source": c["source"],
        "category": c["category"], "name": c["name"], "article": c["article"],
        "article_title": c.get("article_title", ""), "clause": c.get("clause", ""),
        "location": loc.strip(), "text": c["text"], "department": c["department"],
        "contact": c["contact"], "source_url": c["source_url"],
        "law_url": c.get("law_url", ""),
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
