# -*- coding: utf-8 -*-
"""
[T3] 하이브리드 검색 엔진 (의미 검색 + 키워드 검색) + [T12] 재순위화(reranker)
- 의미 검색: T2에서 만든 ChromaDB 벡터DB (KR-SBERT 임베딩, 코사인 유사도)
  (T11 BGE-M3, T13 multilingual-e5-large 교체를 각각 시도했으나 둘 다 무관한 질의의
   유사도가 비정상적으로 높게 나오는 문제로 롤백 — 아래 MODEL_NAME 주석 참고)
- 키워드 검색: 순수 파이썬 BM25 (bm25_lite.py)
- 두 점수를 0~1로 정규화한 뒤 가중합하여 1차 후보 순위를 매긴다.
- 재순위화: 1차 후보 상위 N개를 cross-encoder로 질문-조문을 직접 비교해 다시 정렬한다
  (질문형 자연어 질의의 정확도를 높이기 위한 T12 개선. bge_m3_notes.md 참고)

이 모듈은 FastAPI 서버(api_server.py)와 테스트 스크립트에서 공용으로 사용한다.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bm25_lite import BM25Lite

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CHUNKS_PATH = os.path.join(DATA_DIR, "chunks.json")
REGS_PATH = os.path.join(DATA_DIR, "regulations.json")
# GNU_VECTORDB를 안 정해주면 OS에 맞는 기본 경로로 떨어진다 (환경변수를 깜빡해도
# 리눅스에서 Windows 전용 경로(C:\...)로 잘못 떨어지는 것을 방지)
_DEFAULT_DB_DIR = r"C:\gnu_vectordb" if os.name == "nt" else "/var/lib/gnu_vectordb"
DB_DIR = os.environ.get("GNU_VECTORDB", _DEFAULT_DB_DIR)


def _patch_sqlite3_for_chromadb():
    """리눅스 배포판(특히 CentOS/RHEL 계열)의 시스템 sqlite3가 오래된 경우
    (ChromaDB는 3.35.0 이상 필요), `pip install pysqlite3-binary`로 설치한 최신
    버전으로 표준 sqlite3 모듈을 바꿔치기한다. (ChromaDB 공식 문서 권장 우회법)
    pysqlite3-binary가 없거나 이미 sqlite3가 충분히 최신이면 조용히 넘어간다.
    """
    try:
        import pysqlite3
        sys.modules["sqlite3"] = pysqlite3
    except ImportError:
        pass
# T11에서 BGE-M3로, T13에서 multilingual-e5-large로 교체를 시도했으나 둘 다 실측 결과
# 완전히 무관한 질문에도 코사인 유사도가 관련 질의와 겹칠 만큼 높게 나오는 문제가 있었고
# (T13에서는 특히 "연구비 지원 한도가 얼마야?" 같은 애매한 질문에 전혀 다른 주제인
# "우수연구센터 지정 기준" 조항을 근거로 끌어와 오답을 만드는 사례까지 실측 확인되어)
# 두 번 다 롤백했다. KR-SBERT가 이 좁은 도메인(대학 규정)에서는 오히려 무관한 문장을
# 확실히 낮게 매겨 더 안전하다고 최종 판단. 정확도 개선은 T12의 재순위화(reranker)로 대응.
MODEL_NAME = "snunlp/KR-SBERT-V40K-klueNLI-augSTS"
COLLECTION = "regulations"

# 하이브리드 가중치: 의미 검색 0.6 + 키워드 검색 0.4
# (문장형 자연어 질의는 의미 검색이, 정확한 단어는 키워드 검색이 강점이므로 절충)
VEC_WEIGHT = 0.6
BM25_WEIGHT = 0.4
# 벡터DB에서 미리 가져올 후보 수 (필터링 후 재정렬하기 위한 여유분)
CANDIDATE_POOL = 200
# 최소 관련성 기준: 아래 둘 다 미달이면 "관련 없음"으로 판단해 결과에서 제외한다.
# (완전 무관한 질의의 코사인 유사도는 실측 0.27~0.40 수준, 관련 질의는 0.46 이상으로 확인됨)
MIN_VEC_SIM = 0.44
MIN_BM25_SCORE = 0.0  # BM25는 실제 단어가 하나라도 일치하면 0보다 크므로 그대로 사용

# ---------------------------------------------------------- T12: 재순위화(reranker)
# cross-encoder는 "질문"과 "조문"을 한 쌍으로 같이 넣어 직접 관련도를 계산하므로
# (임베딩을 각각 따로 벡터로 만들어 비교하는 방식보다) 질문형 질의에서 훨씬 정확하다.
# 다만 느려서 전체 문서에는 못 쓰고, 1차 하이브리드 검색으로 추린 상위 후보에만 적용한다.
RERANK_MODEL_NAME = os.environ.get("GNU_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RERANK_POOL = 20            # 1차 후보 중 재순위화 대상으로 삼을 상위 개수
RERANK_ENABLED = os.environ.get("GNU_RERANK_ENABLED", "1") != "0"


class SearchEngine:
    """모델·인덱스를 한 번만 로딩해 재사용하는 검색 엔진 (지연 초기화)."""

    _instance = None

    def __init__(self):
        print("[검색엔진] 데이터 로딩 중...")
        with open(CHUNKS_PATH, encoding="utf-8") as f:
            self.chunks = json.load(f)
        self.chunk_by_id = {c["chunk_id"]: c for c in self.chunks}
        self.index_by_id = {c["chunk_id"]: i for i, c in enumerate(self.chunks)}

        with open(REGS_PATH, encoding="utf-8") as f:
            regs = json.load(f)
        self.reg_by_id = {r["id"]: r for r in regs}

        # BM25는 임베딩과 같은 형식(규정명+조항+본문)으로 색인해 규정명 검색도 지원
        corpus = [
            f"{c['name']} {c['article']} {c.get('article_title','')} {c['text']}"
            for c in self.chunks
        ]
        self.bm25 = BM25Lite(corpus)

        print(f"[검색엔진] 임베딩 모델 로딩 중... ({MODEL_NAME})")
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(MODEL_NAME)

        print(f"[검색엔진] 벡터DB 연결 중... ({DB_DIR})")
        _patch_sqlite3_for_chromadb()
        import chromadb
        client = chromadb.PersistentClient(path=DB_DIR)
        self.collection = client.get_collection(COLLECTION)
        print(f"[검색엔진] 준비 완료: 청크 {len(self.chunks):,}개, "
              f"벡터DB 문서 {self.collection.count():,}개")

        self._reranker = None
        self._reranker_failed = False

    def _lazy_reranker(self):
        """[T12] 재순위화 모델을 최초 사용 시점에만 로딩한다 (필요 없으면 안 씀)."""
        if not RERANK_ENABLED or self._reranker_failed:
            return None
        if self._reranker is None:
            try:
                from sentence_transformers import CrossEncoder
                print(f"[검색엔진] 재순위화 모델 로딩 중... ({RERANK_MODEL_NAME})")
                self._reranker = CrossEncoder(RERANK_MODEL_NAME, max_length=512)
                print("[검색엔진] 재순위화 모델 로딩 완료")
            except Exception as e:
                print(f"[검색엔진] 경고: 재순위화 모델을 사용할 수 없습니다 ({e}). "
                      f"재순위화 없이 하이브리드 검색 결과만 사용합니다.")
                self._reranker_failed = True
                return None
        return self._reranker

    @classmethod
    def get(cls) -> "SearchEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ---------------------------------------------------------- 필터 도우미
    @staticmethod
    def _build_where(sources, categories):
        """ChromaDB 'where' 필터 절 생성 (source/category 다중 선택 지원)."""
        clauses = []
        if sources:
            clauses.append({"source": {"$in": sources}} if len(sources) > 1
                           else {"source": sources[0]})
        if categories:
            clauses.append({"category": {"$in": categories}} if len(categories) > 1
                           else {"category": categories[0]})
        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    @staticmethod
    def _minmax_norm(values):
        if not values:
            return {}
        lo, hi = min(values.values()), max(values.values())
        if hi - lo < 1e-9:
            return {k: (1.0 if hi > 0 else 0.0) for k in values}
        return {k: (v - lo) / (hi - lo) for k, v in values.items()}

    @staticmethod
    def _make_snippet(text: str, query: str, width: int = 90) -> str:
        """검색어가 등장하는 위치 주변을 발췌 (본문 발췌 표시용)."""
        terms = re.findall(r"[0-9A-Za-z가-힣]+", query)
        pos = -1
        for t in sorted(terms, key=len, reverse=True):
            idx = text.find(t)
            if idx >= 0:
                pos = idx
                break
        if pos < 0:
            snippet = text[:width * 2]
        else:
            start = max(0, pos - width // 2)
            snippet = text[start:start + width * 2]
        snippet = snippet.replace("\n", " ").strip()
        return (snippet[:width * 2] + "…") if len(snippet) >= width * 2 else snippet

    # ---------------------------------------------------------------- 검색
    def search(self, query: str, top_k: int = 10, sources=None, categories=None, rerank: bool = False):
        """rerank=True면 상위 후보를 cross-encoder로 재순위화한다 (정확하지만 10초 안팎
        추가로 걸림). 즉시 응답이 필요한 일반 검색(/api/search)은 기본값 False로 빠르게
        응답하고, 어차피 LLM 답변 생성에 수십 초가 걸리는 AI 질문하기(RAG)만 True로 호출해
        검색 정확도를 높인다 (rag_engine.py의 retrieve() 참고).
        """
        t0 = time.time()
        where = self._build_where(sources, categories)

        # 1) 의미 검색 (벡터 유사도)
        emb = self.model.encode([query], normalize_embeddings=True)
        vec_res = self.collection.query(
            query_embeddings=emb.tolist(), n_results=CANDIDATE_POOL, where=where)
        vec_scores = {}
        if vec_res["ids"] and vec_res["ids"][0]:
            for cid, dist in zip(vec_res["ids"][0], vec_res["distances"][0]):
                vec_scores[cid] = 1 - dist  # 코사인 거리 → 유사도

        # 2) 키워드 검색 (BM25, 전체 문서 대상 후 필터 적용)
        all_bm25 = self.bm25.scores(query)
        bm25_scores = {}
        for cid, idx in self.index_by_id.items():
            score = all_bm25[idx]
            if score <= 0:
                continue
            chunk = self.chunk_by_id[cid]
            if sources and chunk["source"] not in sources:
                continue
            if categories and chunk["category"] not in categories:
                continue
            bm25_scores[cid] = score

        # 3) 관련성 최소 기준 미달 후보 제외 ("결과 없음" 오탐 방지)
        #    - 의미 유사도가 낮고, 키워드도 전혀 일치하지 않으면 무관한 질의로 간주
        candidate_ids = {
            cid for cid in (set(vec_scores) | set(bm25_scores))
            if vec_scores.get(cid, 0.0) >= MIN_VEC_SIM
            or bm25_scores.get(cid, 0.0) > MIN_BM25_SCORE
        }

        # 4) 후보 통합 및 정규화
        vec_norm = self._minmax_norm({cid: vec_scores.get(cid, 0.0) for cid in candidate_ids})
        bm25_norm = self._minmax_norm({cid: bm25_scores.get(cid, 0.0) for cid in candidate_ids})

        combined = []
        for cid in candidate_ids:
            score = (VEC_WEIGHT * vec_norm.get(cid, 0.0)
                    + BM25_WEIGHT * bm25_norm.get(cid, 0.0))
            combined.append((cid, score))
        combined.sort(key=lambda x: -x[1])

        # 5) [T12] 재순위화: 1차 후보 상위 RERANK_POOL개만 cross-encoder로 "순서만" 다시
        #    매긴다. 중요: 여기서 나오는 cross-encoder 점수는 하이브리드 점수와 완전히
        #    다른 척도라서, 그대로 최종 score로 덮어쓰면 MIN_TOP_SCORE_FOR_ANSWER 같은
        #    기존 관련성 임계값이 전혀 다른 기준에 적용되어 무의미해진다(T11과 같은 실수를
        #    반복하게 됨). 그래서 cross-encoder는 순위(정렬 순서)를 정하는 데만 쓰고,
        #    화면에 보여주고 임계값 판단에 쓰이는 score는 원래 하이브리드 점수를 그대로
        #    유지한다 — "관련 있다고 판단된 후보들 사이의 순서"만 더 정확하게 다듬는 것.
        reranker = self._lazy_reranker() if rerank else None
        rerank_candidates = combined[:max(RERANK_POOL, top_k)]
        if reranker and rerank_candidates:
            pairs = [(query, self.chunk_by_id[cid]["text"]) for cid, _ in rerank_candidates]
            try:
                raw_scores = reranker.predict(pairs)
                # [T14] 순수 cross-encoder 순서를 그대로 쓰면, 하이브리드 점수가 확연히
                # 낮은(주제가 다른) 후보가 "숫자가 구체적으로 들어있다"는 이유만으로
                # 최상위 후보보다 앞으로 튀어오르는 사례가 발견됐다(예: "연구비 지원
                # 한도" 질문에서 무관한 "간접비 관리·운영 지침"이 1위로 승격). 단순 가중
                # 평균은 cross-encoder가 자신 있게 틀린 답을 낼 때 여전히 뚫린다는 것을
                # 확인했다. 그래서 "하이브리드 최상위 점수 대비 크게 뒤처지는(GATE_MARGIN
                # 이상 차이나는) 후보는애초에 승격 대상에서 제외"하는 게이트를 둔다 —
                # cross-encoder는 하이브리드 점수가 비슷한(=주제 적합성이 비슷한) 후보들
                # 사이에서만 순서를 다듬을 수 있고, 명백히 점수가 낮은 후보를 1등으로
                # 끌어올릴 수는 없다.
                RERANK_GATE_MARGIN = 0.05
                top_hybrid = rerank_candidates[0][1]
                ce_by_cid = dict(zip([cid for cid, _ in rerank_candidates], raw_scores))
                eligible = [(cid, hybrid) for cid, hybrid in rerank_candidates
                            if hybrid >= top_hybrid - RERANK_GATE_MARGIN]
                rest = [(cid, hybrid) for cid, hybrid in rerank_candidates
                        if hybrid < top_hybrid - RERANK_GATE_MARGIN]
                eligible.sort(key=lambda x: -ce_by_cid.get(x[0], 0.0))
                top = (eligible + rest)[:top_k]  # (cid, 원래 하이브리드 점수) 유지
            except Exception as e:
                print(f"[검색엔진] 경고: 재순위화 실행 실패({e}). 하이브리드 순위를 그대로 사용합니다.")
                top = combined[:top_k]
        else:
            top = combined[:top_k]

        results = []
        for cid, score in top:
            c = self.chunk_by_id[cid]
            loc = c["article"] + (f" {c['clause']}" if c.get("clause") else "")
            results.append({
                "chunk_id": cid,
                "reg_id": c["reg_id"],
                "source": c["source"],
                "category": c["category"],
                "name": c["name"],
                "article": c["article"],
                "article_title": c.get("article_title", ""),
                "clause": c.get("clause", ""),
                "location": loc.strip(),
                "snippet": self._make_snippet(c["text"], query),
                "department": c["department"],
                "contact": c["contact"],
                "source_url": c["source_url"],
                "law_url": c.get("law_url", ""),
                "score": round(score, 4),
            })

        related_regulations = list(dict.fromkeys(r["name"] for r in results))  # 순서 보존 중복 제거
        took_ms = round((time.time() - t0) * 1000, 1)
        return {
            "query": query,
            "took_ms": took_ms,
            "total": len(results),
            "results": results,
            "related_regulations": related_regulations,
        }

    # ------------------------------------------------------------ 미리보기
    def get_chunk(self, chunk_id: str):
        return self.chunk_by_id.get(chunk_id)

    def get_regulation_fulltext(self, reg_id: str):
        reg = self.reg_by_id.get(reg_id)
        if not reg:
            return None
        # text_file 값이 Windows에서 저장되어 "\\" 구분자를 포함할 수 있으므로
        # "/"로 정규화한 뒤 조립한다 (리눅스에서 "\\"는 경로 구분자로 인식되지 않음).
        path = os.path.join(DATA_DIR, *reg["text_file"].replace("\\", "/").split("/"))
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            content = f.read()
        sep = content.find("=" * 40)
        body = content[sep + 40:].strip() if sep >= 0 else content.strip()
        return {**reg, "full_text": body}
