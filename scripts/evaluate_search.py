# -*- coding: utf-8 -*-
"""
[T5] 검색 품질 자동 평가 스크립트

PRD 6.2 성공 지표를 기준으로 평가한다.
  - 검색 성공률: 주요 키워드 검색 시 관련 조항이 상위 5건 내 노출
  - 검색 응답 시간: 평균 3초 이내

평가 방식:
  각 테스트 키워드마다 "이 키워드가 들어간 검색이라면 결과 규정명/본문에
  반드시 등장해야 하는 확인 단어(expect)"를 정의해 두고,
  상위 5건의 결과 중 하나라도 확인 단어를 포함하면 '성공'으로 판정한다.
  (사람이 직접 정답을 일일이 라벨링하지 않고도 반복 실행 가능한 자동 평가 방식)

사용법:
    python scripts/evaluate_search.py                 # 기본 서버(http://127.0.0.1:8000) 대상
    python scripts/evaluate_search.py --direct         # 서버 없이 검색엔진을 직접 호출(서버 기동 불필요)
"""
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

# Windows 콘솔(cp949)에서도 이모지/한글이 깨지지 않도록 표준출력을 UTF-8로 고정
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

API_BASE = os.environ.get("GNU_API_BASE", "http://127.0.0.1:8000")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
TOP_N = 5          # PRD 6.2: 상위 5건 내 노출
TIME_LIMIT = 3.0   # PRD 6.2 / NFR-01: 평균 3초 이내

# 테스트 키워드 목록: (검색어, [결과에 하나라도 포함되어야 하는 확인 단어들])
TEST_CASES = [
    ("연구비", ["연구비"]),
    ("휴학", ["휴학"]),
    ("장학", ["장학"]),
    ("등록금", ["등록금"]),
    ("성적", ["성적"]),
    ("수강신청", ["수강", "수강신청"]),
    ("연구윤리", ["연구윤리"]),
    ("졸업", ["졸업"]),
    ("논문 표절", ["표절", "연구부정"]),
    ("산학협력단 인사", ["인사"]),
    ("연구노트 작성", ["연구노트"]),
    ("장애학생 지원", ["장애"]),
    ("휴학하려면 어떻게 해?", ["휴학"]),           # 자연어 질의
    ("연구비 어떻게 신청하나요", ["연구비"]),        # 자연어 질의
    ("등록금 나눠서 낼 수 있나요", ["등록금", "분할"]),  # 자연어 질의
]


def call_api(query, top_k=TOP_N):
    """서버(API)를 통해 검색."""
    url = (API_BASE + "/api/search?"
          + urllib.parse.urlencode({"q": query, "top_k": top_k}))
    t0 = time.time()
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["results"], time.time() - t0


_engine = None


def call_direct(query, top_k=TOP_N):
    """서버 없이 SearchEngine을 직접 호출 (서버 기동 없이 빠르게 튜닝 반복할 때 사용)."""
    global _engine
    if _engine is None:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from search_engine import SearchEngine
        _engine = SearchEngine.get()
    t0 = time.time()
    result = _engine.search(query, top_k=top_k)
    return result["results"], time.time() - t0


def hit(results, expects):
    """상위 결과의 규정명+본문 중 확인 단어가 하나라도 있으면 성공."""
    for r in results:
        haystack = (r["name"] + " " + r["snippet"]).lower()
        if any(e.lower() in haystack for e in expects):
            return True
    return False


def run_evaluation(direct=False, top_n=TOP_N):
    caller = call_direct if direct else call_api
    rows = []
    for query, expects in TEST_CASES:
        try:
            results, elapsed = caller(query, top_n)
            ok = hit(results, expects)
            rows.append({
                "query": query, "success": ok, "elapsed": elapsed,
                "top1_name": results[0]["name"] if results else "(결과 없음)",
                "total": len(results),
            })
        except Exception as e:
            rows.append({"query": query, "success": False, "elapsed": None,
                        "top1_name": f"오류: {e}", "total": 0})
    return rows


def print_report(rows, title="검색 품질 평가 결과"):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")
    print(f"{'검색어':<26}{'성공':<6}{'응답(초)':<10}{'1위 결과 규정명'}")
    print("-" * 78)
    for r in rows:
        mark = "✅" if r["success"] else "❌"
        elapsed = f"{r['elapsed']:.3f}" if r["elapsed"] is not None else "-"
        print(f"{r['query']:<26}{mark:<6}{elapsed:<10}{r['top1_name'][:36]}")
    print("-" * 78)

    success_n = sum(1 for r in rows if r["success"])
    total_n = len(rows)
    times = [r["elapsed"] for r in rows if r["elapsed"] is not None]
    avg_time = sum(times) / len(times) if times else 0
    max_time = max(times) if times else 0
    success_rate = success_n / total_n * 100 if total_n else 0

    print(f"\n[요약] 성공률: {success_n}/{total_n} ({success_rate:.1f}%) "
          f"— PRD 6.2 목표: 상위 {TOP_N}건 내 노출")
    print(f"[요약] 평균 응답시간: {avg_time:.3f}초 / 최대: {max_time:.3f}초 "
          f"— PRD 6.2 목표: 평균 {TIME_LIMIT}초 이내")
    print(f"[판정] 성공률 100%: {'PASS' if success_rate == 100 else 'FAIL'} / "
          f"응답속도 목표: {'PASS' if avg_time <= TIME_LIMIT else 'FAIL'}")
    return {
        "success_n": success_n, "total_n": total_n, "success_rate": success_rate,
        "avg_time": avg_time, "max_time": max_time, "rows": rows,
    }


def main():
    direct = "--direct" in sys.argv
    rows = run_evaluation(direct=direct)
    summary = print_report(rows)

    out_path = os.path.join(DATA_DIR, "search_quality_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n[저장] 평가 결과: {out_path}")
    return summary


if __name__ == "__main__":
    main()
