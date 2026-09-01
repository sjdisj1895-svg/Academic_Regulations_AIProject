# -*- coding: utf-8 -*-
"""
[T5] 규정 데이터 원클릭 갱신 스크립트

규정이 제·개정되었을 때, 관리자가 명령 한 번으로
  [수집(T1) → 청킹(T2) → 임베딩·벡터DB 적재(T2)]
전체 파이프라인을 다시 실행할 수 있게 한다. (DR-05, NFR-05)

사용법 (프로젝트 폴더에서):
    python scripts/refresh_all.py               # 전체 갱신(이어받기: 이미 받은 대학 규정은 건너뜀)
    python scripts/refresh_all.py --fresh        # 대학/산학협력단 원문부터 처음부터 다시 수집
    python scripts/refresh_all.py --skip-collect # 수집은 건너뛰고 청킹·임베딩만 다시 실행
    python scripts/refresh_all.py --name 인권센터 # 특정 규정만 청킹·임베딩 갱신 (수집은 항상 전체 대상)
    python scripts/refresh_all.py --skip-eval     # 마지막 품질 평가 단계 생략(속도 우선)

실행이 끝나면 각 단계 결과와 소요 시간, 마지막에 검색 품질 평가 결과까지 요약해서 보여준다.
"""
import io
import os
import subprocess
import sys
import time

# Windows 콘솔(cp949)에서도 한글/이모지가 깨지지 않도록 표준출력을 UTF-8로 고정
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PYTHON = sys.executable
# 하위 단계(collect_all.py 등) 프로세스도 UTF-8로 출력하도록 강제
CHILD_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def run_step(title, args):
    print(f"\n{'=' * 70}\n[단계] {title}\n{'=' * 70}")
    t0 = time.time()
    result = subprocess.run([PYTHON] + args, cwd=".", env=CHILD_ENV)
    elapsed = time.time() - t0
    ok = result.returncode == 0
    print(f"[{'완료' if ok else '실패'}] {title} — {elapsed:.1f}초 소요")
    return ok, elapsed


def main():
    args = sys.argv[1:]
    fresh = "--fresh" in args
    skip_collect = "--skip-collect" in args
    skip_eval = "--skip-eval" in args
    name_filter = None
    if "--name" in args:
        idx = args.index("--name")
        if idx + 1 < len(args):
            name_filter = args[idx + 1]

    print("경상국립대학교 규정 데이터 갱신을 시작합니다.")
    print(f"옵션: fresh={fresh}, skip_collect={skip_collect}, "
          f"name_filter={name_filter}, skip_eval={skip_eval}")

    steps = []

    # 1) 수집 (T1)
    if not skip_collect:
        collect_args = ["scripts/collect_all.py"] + (["--fresh"] if fresh else [])
        ok, el = run_step("① 규정 원문 수집 (대학 + 산학협력단)", collect_args)
        steps.append(("수집", ok, el))
    else:
        print("\n[건너뜀] ① 규정 원문 수집 (--skip-collect)")
        steps.append(("수집", None, 0))

    # 2) 청킹 (T2)
    chunk_args = ["scripts/chunk_rules.py"] + (["--name", name_filter] if name_filter else [])
    ok, el = run_step("② 조·항 단위 청킹", chunk_args)
    steps.append(("청킹", ok, el))

    # 3) 임베딩·벡터DB 적재 (T2)
    build_args = ["scripts/build_vectordb.py"] + (["--name", name_filter] if name_filter else [])
    ok, el = run_step("③ 임베딩 생성 및 벡터DB 적재", build_args)
    steps.append(("임베딩·벡터DB", ok, el))

    # 4) 품질 평가 (T5, 선택)
    if not skip_eval:
        ok, el = run_step("④ 검색 품질 평가 (--direct: 서버 기동 없이 검증)",
                          ["scripts/evaluate_search.py", "--direct"])
        steps.append(("품질평가", ok, el))
    else:
        print("\n[건너뜀] ④ 검색 품질 평가 (--skip-eval)")

    # 요약
    print(f"\n{'#' * 70}\n[전체 갱신 요약]\n{'#' * 70}")
    total_time = 0
    for name, ok, el in steps:
        mark = "-" if ok is None else ("성공" if ok else "실패")
        print(f"  {name:<14}: {mark:<6} ({el:.1f}초)")
        total_time += el
    print(f"  총 소요 시간   : {total_time:.1f}초 ({total_time/60:.1f}분)")

    failed = [n for n, ok, _ in steps if ok is False]
    if failed:
        print(f"\n⚠️ 다음 단계에서 오류가 발생했습니다: {', '.join(failed)}")
        print("   각 단계의 오류 메시지를 확인하고, data/errors_*.json 을 점검하세요.")
        sys.exit(1)
    print("\n✅ 모든 단계가 정상적으로 완료되었습니다. "
          "웹 화면(http://127.0.0.1:8000/)에서 최신 데이터로 검색해보세요.")


if __name__ == "__main__":
    main()
