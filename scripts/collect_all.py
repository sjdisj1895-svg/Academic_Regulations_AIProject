# -*- coding: utf-8 -*-
"""
[T1] 규정 데이터 수집 통합 실행기
- 대학(학칙/규정/지침) + 산학협력단 규정을 모두 수집하고
  전체 목록을 data/regulations.json 하나로 합칩니다.

사용법 (프로젝트 폴더에서):
    python scripts/collect_all.py            # 전체 수집 (이미 받은 대학 규정은 건너뜀)
    python scripts/collect_all.py --fresh    # 처음부터 다시 수집 (규정 개정 시)
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))
import collect_university
import collect_foundation

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
FINAL = os.path.join(DATA_DIR, "regulations.json")


def reset_data():
    """--fresh 옵션: 기존 수집 결과를 지우고 처음부터 다시 수집."""
    for sub in ["university", "foundation"]:
        folder = os.path.join(DATA_DIR, sub)
        if os.path.isdir(folder):
            shutil.rmtree(folder)
    for name in ["progress_university.jsonl", "progress_foundation.json",
                 "errors_university.json", "errors_foundation.json"]:
        path = os.path.join(DATA_DIR, name)
        if os.path.exists(path):
            os.remove(path)
    print("[초기화] 기존 수집 데이터를 삭제했습니다. 처음부터 다시 수집합니다.\n")


def main():
    if "--fresh" in sys.argv:
        reset_data()
    os.makedirs(DATA_DIR, exist_ok=True)

    # 1) 대학 규정 수집
    univ_done, univ_errors = collect_university.main()
    print()
    # 2) 산학협력단 규정 수집
    found_results, found_errors = collect_foundation.main()
    print()

    # 3) 통합 목록(regulations.json) 생성
    merged = list(univ_done.values()) + found_results
    with open(FINAL, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    # 4) 결과 요약
    by = {}
    for r in merged:
        key = f"{r['source']}/{r['category'].split(' ')[0]}"
        by[key] = by.get(key, 0) + 1
    print("=" * 50)
    print("[수집 결과 요약]")
    for key, cnt in sorted(by.items()):
        print(f"  {key}: {cnt}건")
    print(f"  합계: {len(merged)}건")
    print(f"  오류: 대학 {len(univ_errors)}건 / 산학협력단 {len(found_errors)}건")
    print(f"[저장 위치] {FINAL}")
    print(f"[텍스트 파일] {os.path.join(DATA_DIR, 'university')} , "
          f"{os.path.join(DATA_DIR, 'foundation')}")


if __name__ == "__main__":
    main()
