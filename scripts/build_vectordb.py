# -*- coding: utf-8 -*-
"""
[T2] 임베딩 생성 + 벡터DB(ChromaDB) 적재 프로그램

■ 선택한 도구와 이유 (무료·로컬 실행)
- 임베딩 모델: snunlp/KR-SBERT-V40K-klueNLI-augSTS (Hugging Face 공개 모델)
  · 서울대 NLP 연구실이 공개한 한국어 특화 SBERT — 한국어 문장 의미 비교에 강함
  · 무료이며 최초 1회 다운로드 후 로컬에서 오프라인 실행 가능
- 벡터DB: ChromaDB (오픈소스, 무료)
  · 서버 설치 없이 파일 폴더(data/vectordb)로 저장되는 임베디드 방식
  · 메타데이터 필터(출처/카테고리)와 코사인 유사도 검색 기본 지원

사용법:
    python scripts/build_vectordb.py                # 전체 적재 (기존 DB 재구축)
    python scripts/build_vectordb.py --name 인권센터  # 해당 규정 청크만 다시 적재
"""
import json
import os
import sys
import time

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CHUNKS = os.path.join(DATA_DIR, "chunks.json")
# ※ ChromaDB는 한글이 포함된 경로에서 인덱스 로딩 오류가 발생하므로
#    영문 경로(C:\gnu_vectordb)에 저장한다. (환경변수 GNU_VECTORDB로 변경 가능)
DB_DIR = os.environ.get("GNU_VECTORDB", r"C:\gnu_vectordb")
MODEL_NAME = "snunlp/KR-SBERT-V40K-klueNLI-augSTS"
COLLECTION = "regulations"
BATCH = 128


def get_collection():
    import chromadb
    client = chromadb.PersistentClient(path=DB_DIR)
    return client, client.get_or_create_collection(
        COLLECTION, metadata={"hnsw:space": "cosine"})


def main():
    name_filter = None
    if "--name" in sys.argv:
        idx = sys.argv.index("--name")
        if idx + 1 < len(sys.argv):
            name_filter = sys.argv[idx + 1]

    with open(CHUNKS, encoding="utf-8") as f:
        chunks = json.load(f)
    targets = [c for c in chunks if not name_filter or name_filter in c["name"]]
    print(f"[벡터DB 적재 시작] 청크 {len(targets):,}개"
          + (f" (필터: '{name_filter}')" if name_filter else ""))

    print(f"[임베딩 모델 로딩] {MODEL_NAME} (최초 1회는 다운로드에 수 분 소요)")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME)

    client, col = get_collection()

    if name_filter:
        # 부분 갱신: 해당 규정의 기존 청크 삭제 후 재적재
        reg_ids = sorted({c["reg_id"] for c in targets})
        for rid in reg_ids:
            col.delete(where={"reg_id": rid})
        print(f"  기존 청크 삭제: 규정 {len(reg_ids)}건")
    else:
        # 전체 재구축: 컬렉션 초기화
        try:
            client.delete_collection(COLLECTION)
        except Exception:
            pass
        client, col = get_collection()

    t0 = time.time()
    for i in range(0, len(targets), BATCH):
        batch = targets[i:i + BATCH]
        # 검색 품질을 위해 '규정명 + 조항'을 본문 앞에 붙여 임베딩
        texts = [f"{c['name']} {c['article']} {c.get('article_title','')}\n{c['text']}"
                 for c in batch]
        embs = model.encode(texts, batch_size=32, show_progress_bar=False,
                            normalize_embeddings=True)
        col.add(
            ids=[c["chunk_id"] for c in batch],
            embeddings=embs.tolist(),
            documents=[c["text"] for c in batch],
            metadatas=[{
                "reg_id": c["reg_id"], "source": c["source"],
                "category": c["category"], "name": c["name"],
                "article": c["article"], "article_title": c.get("article_title", ""),
                "clause": c.get("clause", ""), "department": c["department"],
                "contact": c["contact"], "source_url": c["source_url"],
                "law_url": c.get("law_url", ""),
            } for c in batch],
        )
        done = min(i + BATCH, len(targets))
        if done % (BATCH * 8) < BATCH or done == len(targets):
            el = time.time() - t0
            print(f"  {done:,}/{len(targets):,} ({done*100//len(targets)}%) "
                  f"경과 {el:,.0f}초")

    print(f"[적재 완료] 벡터DB 문서 수: {col.count():,}개")
    print(f"[저장 위치] {DB_DIR}")


if __name__ == "__main__":
    main()
