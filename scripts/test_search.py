# -*- coding: utf-8 -*-
"""
[T2] 벡터DB 테스트 검색
사용법:
    python scripts/test_search.py 연구비
    python scripts/test_search.py "휴학하려면 어떻게 해?"
"""
import os
import sys

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
# ChromaDB 한글 경로 문제로 영문 경로 사용 (build_vectordb.py와 동일)
DB_DIR = os.environ.get("GNU_VECTORDB", r"C:\gnu_vectordb")
MODEL_NAME = "snunlp/KR-SBERT-V40K-klueNLI-augSTS"


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "연구비"
    top_k = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    from sentence_transformers import SentenceTransformer
    import chromadb

    model = SentenceTransformer(MODEL_NAME)
    client = chromadb.PersistentClient(path=DB_DIR)
    col = client.get_collection("regulations")

    emb = model.encode([query], normalize_embeddings=True)
    res = col.query(query_embeddings=emb.tolist(), n_results=top_k)

    print(f"\n검색어: '{query}'  (벡터DB 문서 {col.count():,}개 중 상위 {top_k}건)")
    print("=" * 70)
    for rank, (doc, meta, dist) in enumerate(zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0]), 1):
        sim = 1 - dist
        loc = meta["article"] + (f" {meta['clause']}" if meta["clause"] else "")
        title = f"({meta['article_title']})" if meta.get("article_title") else ""
        print(f"[{rank}] 유사도 {sim:.3f} | {meta['source']}/{meta['category']}")
        print(f"    규정명: {meta['name']}")
        print(f"    조항: {loc} {title}")
        print(f"    담당부서: {meta['department']} ({meta['contact']})")
        print(f"    본문: {doc[:150].replace(chr(10), ' ')}...")
        print("-" * 70)


if __name__ == "__main__":
    main()
