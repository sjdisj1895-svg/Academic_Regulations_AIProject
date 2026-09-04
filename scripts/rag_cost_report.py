# -*- coding: utf-8 -*-
"""
[T10] RAG 호출 횟수·비용 요약 스크립트

scripts/api_server.py의 /api/ask가 남기는 로그(data/rag_logs/*.jsonl)를 읽어
호출 횟수, 성공/거절 비율, 백엔드(로컬/외부 API)별 통계를 집계한다.

로컬 모델(LocalHFBackend)만 사용하는 경우 API 비용이 전혀 발생하지 않으므로,
비용 추정은 로그에 외부 API(external_api) 호출이 하나라도 있을 때만 출력한다.

사용법:
    python scripts/rag_cost_report.py                 # 전체 로그 집계
    python scripts/rag_cost_report.py --days 7         # 최근 7일만 집계

비용 추정 방법:
    로그에는 실제 토큰 수를 남기지 않으므로(질문·답변 텍스트 길이로 대략 추정),
    환경변수 GNU_RAG_COST_PER_CALL(호출 1건당 예상 비용, 기본값 $0.001 — gpt-4o-mini
    수준의 소규모 질의 기준 대략치)을 곱한 "대략적인" 추정치임을 명시한다.
    정확한 비용은 사용 중인 API 제공사의 대시보드를 반드시 함께 확인해야 한다.
"""
import glob
import io
import json
import os
import sys
from datetime import datetime, timedelta

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "rag_logs")
COST_PER_CALL_USD = float(os.environ.get("GNU_RAG_COST_PER_CALL", "0.001"))


def load_entries(days=None):
    paths = sorted(glob.glob(os.path.join(LOGS_DIR, "*.jsonl")))
    if days:
        cutoff = datetime.now() - timedelta(days=days)
        paths = [p for p in paths
                 if _parse_day(os.path.basename(p)) is None
                 or _parse_day(os.path.basename(p)) >= cutoff]

    entries = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def _parse_day(filename):
    try:
        return datetime.strptime(os.path.splitext(filename)[0], "%Y-%m-%d")
    except ValueError:
        return None


def summarize(entries):
    total = len(entries)
    by_backend = {}
    by_status = {}
    took_ms_values = []
    for e in entries:
        backend = e.get("backend", "unknown")
        status = e.get("status", "unknown")
        by_backend[backend] = by_backend.get(backend, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        if isinstance(e.get("took_ms"), (int, float)):
            took_ms_values.append(e["took_ms"])

    avg_took_ms = sum(took_ms_values) / len(took_ms_values) if took_ms_values else 0
    return {
        "total": total,
        "by_backend": by_backend,
        "by_status": by_status,
        "avg_took_ms": round(avg_took_ms, 1),
    }


def print_report(summary):
    print("=" * 70)
    print("RAG 호출 횟수·비용 요약 (T10)")
    print("=" * 70)
    print(f"전체 /api/ask 호출 수: {summary['total']}건")
    print(f"평균 응답 시간: {summary['avg_took_ms']}ms")

    print("\n[백엔드별 호출 수]")
    if not summary["by_backend"]:
        print("  로그가 없습니다. /api/ask를 한 번이라도 호출한 뒤 다시 실행해주세요.")
    for backend, n in summary["by_backend"].items():
        label = {"local": "로컬 모델(무료)", "external_api": "외부 API(유료)"}.get(backend, backend)
        print(f"  {label}: {n}건")

    print("\n[처리 결과별 호출 수]")
    status_label = {
        "answered": "AI가 실제로 답변함", "refused": "관련 근거 없어 거절",
        "fallback_no_llm": "근거는 있으나 LLM 미사용(장애 대응)",
        "timeout": "시간 초과", "error": "오류 발생",
    }
    for status, n in summary["by_status"].items():
        print(f"  {status_label.get(status, status)}: {n}건")

    external_n = summary["by_backend"].get("external_api", 0)
    if external_n == 0:
        print("\n[비용] 외부 API 호출 기록이 없습니다 — 로컬 모델만 사용 중이라면 이 항목은")
        print("       생략해도 됩니다 (API 비용이 전혀 발생하지 않습니다).")
    else:
        estimated = external_n * COST_PER_CALL_USD
        print(f"\n[비용 추정] 외부 API 호출 {external_n}건 x 건당 예상 ${COST_PER_CALL_USD} "
              f"(환경변수 GNU_RAG_COST_PER_CALL로 조정 가능)")
        print(f"           ≈ 약 ${estimated:.4f} (대략치이며, 정확한 금액은 사용 중인")
        print(f"             API 제공사(OpenAI 등)의 대시보드에서 반드시 확인하세요)")
    print("=" * 70)


def main():
    days = None
    if "--days" in sys.argv:
        idx = sys.argv.index("--days")
        days = int(sys.argv[idx + 1])
    entries = load_entries(days=days)
    summary = summarize(entries)
    print_report(summary)
    return summary


if __name__ == "__main__":
    main()
