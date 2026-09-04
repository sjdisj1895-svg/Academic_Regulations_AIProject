# -*- coding: utf-8 -*-
"""
[T9] RAG 답변 품질 자동 평가 및 환각(hallucination) 방지 검증

scripts/evaluate_search.py(T5)의 "확인 단어 자동 채점" 방식을 답변 생성(RAG)에도
그대로 적용한다. 아래 4가지를 점검한다.

  1. 답변이 실제로 관련 조항을 근거로 인용하는지 (검색이 정답 후보를 가져왔고,
     LLM이 그것을 근거로 실제 답변했는지 — 잘못 거절하지 않는지)
  2. 답변 문장에 등장하는 숫자가 근거 조항(컨텍스트)에도 실제로 등장하는지
     (컨텍스트 밖의 숫자를 지어냈다면 환각으로 간주)
  3. 규정과 무관한 질문에는 LLM을 호출하지 않고 즉시 거절하는지
  4. 답변 생성까지 걸리는 시간

또한 rag_engine.py에 새로 추가한 "근거에 없는 규정명 인용 경고" 가드레일이
실제로 동작하는지 LLM 호출 없이 별도로 단위 검증한다.

사용법:
    python scripts/evaluate_rag.py
"""
import io
import json
import os
import re
import sys
import time

# Windows 콘솔(cp949)에서도 이모지/한글이 깨지지 않도록 표준출력을 UTF-8로 고정
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag_engine
from rag_engine import NOT_FOUND_MESSAGE, apply_citation_guardrail

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# ---------------------------------------------------------------- 테스트 질문 세트
# expect_type:
#   "cite"        - 관련 조항이 있으므로 LLM이 실제로 근거를 들어 답해야 함
#   "refuse_soft" - 검색은 되지만(관련 조항은 있음) 구체적 답이 없어 거절해야 함
#   "refuse_hard" - 검색 결과 자체가 없어(규정과 무관) LLM 호출 없이 즉시 거절해야 함
TEST_QUESTIONS = [
    ("연구비 감사 관련 행정사무는 어느 부서가 지원해?", "cite", ["산학감사실", "연구비"]),
    ("휴학 신청은 언제까지 해야 해?", "cite", ["휴학"]),
    ("장학금은 어떻게 신청해?", "cite", ["장학"]),
    ("졸업 요건이 뭐야?", "cite", ["졸업"]),
    ("연구비 지원 한도가 얼마야?", "refuse_soft", []),
    ("오늘 서울 날씨가 어때?", "refuse_hard", []),
    ("다음주 로또 번호 알려줘", "refuse_hard", []),
]


def _hit(results, expects):
    """T5 evaluate_search.py의 hit()과 동일한 방식: 검색 결과 규정명+본문에
    확인 단어가 하나라도 있으면 '정답 후보를 실제로 가져왔다'로 판단한다."""
    if not expects:
        return True
    for r in results:
        haystack = (r["name"] + " " + r["snippet"]).lower()
        if any(e.lower() in haystack for e in expects):
            return True
    return False


def _split_before_sources(answer_text: str) -> str:
    """근거 조항 목록/가드레일 경고 앞부분(모델이 실제로 생성한 문장)만 추출한다."""
    for marker in ("[근거 조항]", "⚠️"):
        idx = answer_text.find(marker)
        if idx >= 0:
            answer_text = answer_text[:idx]
    return answer_text


def _hallucinated_numbers(answer_text: str, context_text: str) -> list:
    """답변 문장에 등장하는 숫자 중, 근거 컨텍스트(참고자료)에 없는 숫자를 찾아낸다."""
    body = _split_before_sources(answer_text)
    ans_nums = set(re.findall(r"\d+", body))
    ctx_nums = set(re.findall(r"\d+", context_text))
    return sorted(ans_nums - ctx_nums)


def evaluate_one(question, expect_type, expect_keywords):
    t0 = time.time()
    result = rag_engine.answer(question)
    elapsed = time.time() - t0

    search_result = result["search_result"]
    answer_text = result["answer"]
    # rag_engine.answer()의 found는 검색 결과 유무뿐 아니라 T9에서 추가한
    # 최소 점수 기준(MIN_TOP_SCORE_FOR_ANSWER)까지 반영하므로 이를 그대로 사용한다.
    found = result["found"]

    retrieval_ok = _hit(search_result["results"], expect_keywords)
    refused = NOT_FOUND_MESSAGE in answer_text
    guard_triggered = "[자동 검증 경고]" in answer_text
    hallucinated_nums = _hallucinated_numbers(answer_text, result["context"])

    if expect_type == "cite":
        success = retrieval_ok and not refused and result["used_llm"]
        note = "" if success else (
            "검색이 근거를 못 찾음" if not retrieval_ok else
            "답이 있는데 잘못 거절함" if refused else "LLM을 사용하지 않음")
    elif expect_type == "refuse_soft":
        success = refused
        note = "" if success else "거절해야 하는데 답을 지어냄(환각 의심)"
    else:  # refuse_hard
        success = (not found) and (answer_text == NOT_FOUND_MESSAGE) and (not result["used_llm"])
        note = "" if success else "규정과 무관한데 검색결과/LLM이 응답함"

    if hallucinated_nums:
        note = (note + "; " if note else "") + f"컨텍스트에 없는 숫자 발견: {hallucinated_nums}"

    return {
        "question": question,
        "expect_type": expect_type,
        "success": success,
        "found": found,
        "used_llm": result["used_llm"],
        "elapsed": round(elapsed, 2),
        "hallucinated_numbers": hallucinated_nums,
        "guard_triggered": guard_triggered,
        "note": note,
        "answer_preview": answer_text[:80].replace("\n", " "),
    }


def print_report(rows):
    print(f"\n{'=' * 100}\nRAG 답변 품질 평가 결과 (T9)\n{'=' * 100}")
    print(f"{'질문':<32}{'유형':<12}{'결과':<6}{'시간(초)':<9}{'비고'}")
    print("-" * 100)
    for r in rows:
        mark = "✅" if r["success"] else "❌"
        print(f"{r['question'][:30]:<32}{r['expect_type']:<12}{mark:<6}{r['elapsed']:<9}{r['note']}")
    print("-" * 100)

    total_n = len(rows)
    success_n = sum(1 for r in rows if r["success"])
    hallucination_n = sum(1 for r in rows if r["hallucinated_numbers"])
    guard_n = sum(1 for r in rows if r["guard_triggered"])
    times = [r["elapsed"] for r in rows]
    avg_time = sum(times) / len(times) if times else 0

    print(f"\n[요약] 전체 성공: {success_n}/{total_n} ({success_n/total_n*100:.1f}%)")
    print(f"[요약] 숫자 환각(컨텍스트 밖 숫자) 발견: {hallucination_n}건")
    print(f"[요약] 규정명 인용 가드레일 발동: {guard_n}건 (이번 세트는 실제 환각이 없다면 0건이 정상)")
    print(f"[요약] 평균 응답 시간: {avg_time:.2f}초")
    return {
        "total_n": total_n, "success_n": success_n,
        "success_rate": round(success_n / total_n * 100, 1) if total_n else 0,
        "hallucination_n": hallucination_n, "guard_triggered_n": guard_n,
        "avg_time": round(avg_time, 2),
    }


# ---------------------------------------------------------------- 가드레일 단위 검증
def guardrail_unit_test():
    """LLM 호출 없이, 가드레일 함수 자체가 '근거에 없는 규정명 인용'을 실제로
    잡아내는지 검증한다 (환각 상황을 문자열로 직접 재현).
    """
    fake_search_result = {"related_regulations": ["경상국립대학교 학사관리 규정"]}
    hallucinated_answer = (
        "휴학은 경상국립대학교 학사관리 규정 제31조에 따라 신청할 수 있으며, "
        "장학금은 경상국립대학교 장학금 규정 제5조에 따라 지원됩니다."
    )
    before = hallucinated_answer
    after = apply_citation_guardrail(hallucinated_answer, fake_search_result)
    triggered = after != before

    print(f"\n{'=' * 100}\n가드레일(근거 없는 규정명 인용 경고) 단위 검증\n{'=' * 100}")
    print(f"[적용 전] {before}")
    print(f"[적용 후] {after}")
    print(f"[판정] 가드레일 정상 동작: {'PASS' if triggered else 'FAIL'}")
    return {"triggered": triggered, "before": before, "after": after}


# ---------------------------------------------------------------- T5 검색 품질 회귀 확인
def rerun_search_quality_check():
    import evaluate_search
    print(f"\n{'=' * 100}\nT5 검색 품질 회귀 확인 (evaluate_search.py --direct 재실행)\n{'=' * 100}")
    rows = evaluate_search.run_evaluation(direct=True)
    summary = evaluate_search.print_report(rows, title="검색 품질 재확인 (T9 시점)")
    return summary


def main():
    rows = []
    for i, (q, t, kws) in enumerate(TEST_QUESTIONS, 1):
        print(f"[{i}/{len(TEST_QUESTIONS)}] 질문 처리 중: {q}", flush=True)
        row = evaluate_one(q, t, kws)
        print(f"  -> {'성공' if row['success'] else '실패'} ({row['elapsed']}초) {row['note']}", flush=True)
        rows.append(row)
    rag_summary = print_report(rows)
    guard_summary = guardrail_unit_test()
    search_summary = rerun_search_quality_check()

    report = {
        "rag_rows": rows,
        "rag_summary": rag_summary,
        "guardrail_unit_test": guard_summary,
        "search_quality_regression_check": {
            "success_rate": search_summary["success_rate"],
            "avg_time": search_summary["avg_time"],
        },
    }
    out_path = os.path.join(DATA_DIR, "rag_quality_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n[저장] RAG 품질 평가 결과: {out_path}")
    return report


if __name__ == "__main__":
    main()
