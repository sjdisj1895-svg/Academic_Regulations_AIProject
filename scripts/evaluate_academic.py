# -*- coding: utf-8 -*-
"""
[T18] 학적(學籍) 도메인 전용 품질 평가

실사용 로그(data/rag_logs/)를 보면 "휴학·복학·졸업·수강신청" 같은 학적 질문이 가장 많다.
학생·교직원이 가장 먼저 물어볼 영역이므로, T5(키워드 15문항)·T9(RAG 7문항)와 별도로
학적 핵심 질문만 모아 정기 점검한다.

두 가지 모드:
  (기본)  검색 단계 점검 — rag_engine이 실제로 쓰는 것과 동일한 조건(rerank=True, 상위 5건)으로
          정답 규정/조항이 상위 5건에 들어오는지 확인. LLM 호출이 없어 1~2분 내 끝난다.
  --llm   전체 RAG 점검 — 답변 생성까지 수행해 T9와 같은 기준(거절 여부·숫자 환각)으로 채점.
          외부 API(Claude) 사용 시 수 분, 로컬 Qwen이면 20분 이상 걸릴 수 있다.

추가 지표 — "부설학교 학칙 혼입": 사범대학부설고등학교·부설중학교 학칙이 학부 질문의 1위로
올라오는 사례가 반복 관찰되어(T18 조사), 1위가 부설학교 학칙인 문항 수를 별도로 센다.

사용법:
    python scripts/evaluate_academic.py          # 검색 단계 점검 (빠름)
    python scripts/evaluate_academic.py --llm    # 답변 생성까지 점검
"""
import io
import json
import os
import re
import sys
import time

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from search_engine import SearchEngine  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
REPORT_PATH = os.path.join(DATA_DIR, "academic_quality_report.json")
TOP_K = 5  # rag_engine.TOP_N_FOR_CONTEXT와 동일

# 부설학교 학칙(학부 질문에 끼어들면 안 되는 문서)
ATTACHED_SCHOOL_PAT = re.compile(r"부설(고등|중)학교")

# (질문, 기대유형, 정답 확인 단어) — 확인 단어는 "규정명 또는 조항 제목"에 들어있어야 하는 말.
#   cite        : 정답 조항이 있으므로 상위 5건에 들어오고, LLM도 실제로 답해야 함
#   refuse_soft : 관련 규정은 있으나 묻는 구체 수치가 없어 LLM이 거절해야 함
TEST_QUESTIONS = [
    # ── 휴학·복학·자퇴·재입학·제적 ───────────────────────────────────────────
    ("휴학은 언제까지 신청할 수 있어?",           "cite", ["휴학"]),
    ("휴학 기간은 최대 몇 년까지 가능해?",        "cite", ["휴학"]),
    ("복학은 어떻게 신청해?",                    "cite", ["복학"]),
    # 규정 원문은 "자퇴"가 아니라 "퇴학"(학칙 제55조, 학사관리 규정 제43조)으로 표기 → 둘 다 인정
    ("자퇴하려면 어떤 절차를 거쳐야 해?",         "cite", ["자퇴", "퇴학"]),
    ("재입학은 언제 할 수 있어?",                "cite", ["재입학"]),
    ("제적되는 경우는 어떤 경우야?",              "cite", ["제적"]),
    ("휴학 중에 등록금은 어떻게 처리돼?",          "cite", ["학적변동자", "등록금"]),
    # ── 전공·학점·수강 ────────────────────────────────────────────────────
    ("전과는 언제 신청할 수 있어?",              "cite", ["전과"]),
    ("복수전공은 어떻게 신청해?",                "cite", ["복수전공"]),
    ("부전공 이수 학점은 몇 학점이야?",           "cite", ["부전공"]),
    ("융합전공은 어떻게 이수해?",                "cite", ["융합전공"]),
    ("마이크로디그리는 무엇이고 어떻게 이수해?",   "cite", ["마이크로디그리"]),
    ("학기당 최대 몇 학점까지 신청할 수 있어?",    "cite", ["수강신청 기준학점", "수강신청학점", "학점"]),
    ("수강신청 변경 기간은 언제야?",              "cite", ["수강신청"]),
    ("계절학기는 몇 학점까지 들을 수 있어?",       "cite", ["계절학기"]),
    # ── 성적·시험·출석·경고 ───────────────────────────────────────────────
    ("성적 이의신청은 어떻게 해?",               "cite", ["성적"]),
    ("시험에서 부정행위를 하면 어떻게 돼?",        "cite", ["부정행위", "처벌", "징계"]),
    ("출석이 부족하면 학점을 받을 수 있어?",       "cite", ["출석", "학점"]),
    ("학사경고를 받으면 어떻게 돼?",              "cite", ["학사경고"]),
    # ── 졸업 ────────────────────────────────────────────────────────────
    ("졸업하려면 몇 학점을 이수해야 해?",          "cite", ["졸업", "학점"]),
    ("졸업유예 신청은 어떻게 해?",               "cite", ["유예"]),
    ("조기졸업 요건이 뭐야?",                   "cite", ["조기졸업"]),
    # ── 거절해야 하는 질문(관련 규정은 있으나 수치 없음) ───────────────────
    ("휴학하면 장학금을 얼마나 돌려받아?",         "refuse_soft", []),
]


def _hit(results, expects):
    """규정명 또는 조항 제목에 확인 단어가 하나라도 있으면 정답 후보를 가져온 것으로 본다.
    (T5·T9는 본문 발췌까지 봤지만, 학적 질문은 '어느 조항인가'가 중요해 제목 기준으로 더 엄격히 본다)"""
    if not expects:
        return True
    for r in results:
        haystack = (r["name"] + " " + (r.get("article_title") or "") + " " + r.get("location", "")).lower()
        if any(e.lower() in haystack for e in expects):
            return True
    return False


def _fmt_top(r):
    name = r["name"].replace("경상국립대학교", "").strip()
    title = f"({r['article_title']})" if r.get("article_title") else ""
    return f"{name} {r['location']}{title}"


def evaluate_retrieval(engine):
    rows = []
    for q, expect_type, expects in TEST_QUESTIONS:
        t0 = time.time()
        res = engine.search(q, top_k=TOP_K, rerank=True)
        elapsed = time.time() - t0
        results = res["results"]
        top1 = results[0] if results else None
        attached_top1 = bool(top1 and ATTACHED_SCHOOL_PAT.search(top1["name"]))
        ok = _hit(results, expects)
        rows.append({
            "question": q, "expect_type": expect_type, "expects": expects,
            "retrieval_ok": ok, "attached_school_top1": attached_top1,
            "top1": _fmt_top(top1) if top1 else "", "top1_score": top1["score"] if top1 else 0.0,
            "top5": [_fmt_top(r) for r in results], "elapsed": round(elapsed, 2),
        })
        mark = "✅" if ok else "❌"
        warn = " ⚠️부설학교 1위" if attached_top1 else ""
        print(f"{mark} {q}\n      1위: {rows[-1]['top1']} ({rows[-1]['top1_score']}){warn}")
    return rows


def evaluate_llm(rows):
    """검색 점검 결과 위에 답변 생성 채점(T9 기준)을 덧붙인다."""
    import rag_engine
    from rag_engine import NOT_FOUND_MESSAGE
    for row in rows:
        t0 = time.time()
        result = rag_engine.answer(row["question"])
        elapsed = time.time() - t0
        answer = result["answer"]
        refused = NOT_FOUND_MESSAGE in answer
        body = answer.split("[근거 조항]")[0].split("⚠️")[0]
        halluc = sorted(set(re.findall(r"\d+", body)) - set(re.findall(r"\d+", result["context"])))
        if row["expect_type"] == "cite":
            success = row["retrieval_ok"] and not refused and result["used_llm"]
        else:
            success = refused
        row.update({
            "llm_success": success, "refused": refused, "used_llm": result["used_llm"],
            "hallucinated_numbers": halluc, "llm_elapsed": round(elapsed, 2),
            "answer_preview": body.strip()[:160],
        })
        mark = "✅" if success else "❌"
        extra = f" 숫자환각:{halluc}" if halluc else ""
        print(f"{mark} [LLM] {row['question']} ({elapsed:.1f}초){extra}")
    return rows


def main():
    use_llm = "--llm" in sys.argv
    print("=" * 78)
    print(f"학적 도메인 품질 평가 — {'검색 + 답변 생성' if use_llm else '검색 단계'} ({len(TEST_QUESTIONS)}문항)")
    print("=" * 78)
    engine = SearchEngine.get()
    rows = evaluate_retrieval(engine)

    n = len(rows)
    ok_n = sum(r["retrieval_ok"] for r in rows)
    attached_n = sum(r["attached_school_top1"] for r in rows)
    summary = {
        "mode": "llm" if use_llm else "retrieval",
        "total_n": n, "retrieval_ok_n": ok_n, "retrieval_ok_rate": round(ok_n * 100 / n, 1),
        "attached_school_top1_n": attached_n,
        "avg_search_time": round(sum(r["elapsed"] for r in rows) / n, 3),
    }
    print("-" * 78)
    print(f"[요약] 검색 단계: 정답 조항 상위 {TOP_K}건 내 포함 {ok_n}/{n} ({summary['retrieval_ok_rate']}%)")
    print(f"[요약] 부설학교 학칙이 1위인 문항: {attached_n}건 (0건이 이상적)")
    print(f"[요약] 평균 검색(재순위 포함) 시간: {summary['avg_search_time']}초")

    if use_llm:
        print("-" * 78)
        rows = evaluate_llm(rows)
        llm_ok = sum(r["llm_success"] for r in rows)
        halluc_n = sum(1 for r in rows if r["hallucinated_numbers"])
        summary.update({
            "llm_success_n": llm_ok, "llm_success_rate": round(llm_ok * 100 / n, 1),
            "hallucination_n": halluc_n,
            "avg_llm_time": round(sum(r["llm_elapsed"] for r in rows) / n, 2),
        })
        print("-" * 78)
        print(f"[요약] 답변 생성: {llm_ok}/{n} ({summary['llm_success_rate']}%) · 숫자 환각 {halluc_n}건 · "
              f"평균 {summary['avg_llm_time']}초")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "rows": rows}, f, ensure_ascii=False, indent=1)
    print(f"[저장] {REPORT_PATH}")


if __name__ == "__main__":
    main()
