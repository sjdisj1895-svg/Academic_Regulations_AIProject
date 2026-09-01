# -*- coding: utf-8 -*-
"""
[T3] 외부 라이브러리 없이 동작하는 경량 BM25 키워드 검색기
- 하이브리드 검색의 '키워드 검색' 절반을 담당한다.
- 한글 조문 텍스트는 공백 기준 토큰만으로도 "연구비" 같은 단어 검색에 충분하므로
  정규식으로 한글·영문·숫자 토큰을 추출해 사용한다.
"""
import math
import re
from collections import Counter

TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")

# 한글 1글자 토큰(조사·지시어의 일부인 "해", "그", "이" 등)은 형태소 분석 없이
# 통짜로 잘라내는 이 방식에서 노이즈가 되기 쉬워 제외한다.
# (T5 튜닝: "휴학하려면 어떻게 해?"의 '해'가 "그 해 3월 1일부터"(회계연도 조항)와
#  우연히 일치해 무관한 결과가 상위로 올라오는 문제를 발견하여 적용)
_MIN_TOKEN_LEN = 2


def tokenize(text: str):
    tokens = TOKEN_RE.findall(text.lower())
    return [t for t in tokens if len(t) >= _MIN_TOKEN_LEN or t.isdigit()]


class BM25Lite:
    """BM25Okapi 알고리즘의 순수 파이썬 구현 (rank_bm25 알고리즘과 동일한 수식 사용)."""

    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.doc_tokens = [tokenize(d) for d in documents]
        self.doc_len = [len(t) for t in self.doc_tokens]
        self.avgdl = sum(self.doc_len) / max(1, len(self.doc_len))
        self.n_docs = len(documents)

        df = Counter()
        self.term_freqs = []
        for tokens in self.doc_tokens:
            tf = Counter(tokens)
            self.term_freqs.append(tf)
            for term in tf:
                df[term] += 1
        # IDF 계산 (BM25 표준식)
        self.idf = {
            term: math.log(1 + (self.n_docs - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def scores(self, query: str):
        """전체 문서에 대한 BM25 점수 리스트(문서 순서 그대로)를 반환."""
        q_tokens = tokenize(query)
        scores = [0.0] * self.n_docs
        if not q_tokens:
            return scores
        for term in q_tokens:
            idf = self.idf.get(term)
            if not idf:
                continue
            for i, tf_map in enumerate(self.term_freqs):
                f = tf_map.get(term)
                if not f:
                    continue
                dl = self.doc_len[i]
                denom = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                scores[i] += idf * (f * (self.k1 + 1)) / denom
        return scores
