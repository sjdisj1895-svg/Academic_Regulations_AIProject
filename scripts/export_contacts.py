# -*- coding: utf-8 -*-
"""
[T5] 담당부서·연락처 검수용 목록 추출

검색 결과에 표시되는 모든 담당부서·연락처를 규정 개수와 함께 뽑아서
data/contacts_for_review.csv (엑셀에서 바로 열림) / .md (문서 첨부용) 로 저장한다.
→ 총무과(대학)·산학연구과(산학협력단)에 실제 연락처와 일치하는지 검수를 요청할 때 사용.

사용법:
    python scripts/export_contacts.py
"""
import csv
import json
import os
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
REGS_PATH = os.path.join(DATA_DIR, "regulations.json")
CSV_OUT = os.path.join(DATA_DIR, "contacts_for_review.csv")
MD_OUT = os.path.join(DATA_DIR, "contacts_for_review.md")


def main():
    with open(REGS_PATH, encoding="utf-8") as f:
        regs = json.load(f)

    # (출처, 담당부서, 연락처) 조합별로 집계
    groups = defaultdict(lambda: {"count": 0, "regulations": []})
    for r in regs:
        key = (r["source"], r["department"], r["contact"])
        groups[key]["count"] += 1
        groups[key]["regulations"].append(r["name"])

    rows = []
    for (source, dept, contact), info in groups.items():
        rows.append({
            "출처": source, "담당부서": dept, "연락처": contact,
            "해당규정수": info["count"],
            "규정명예시": ", ".join(info["regulations"][:3])
                      + (" 외" if info["count"] > 3 else ""),
            "검수결과(O/X)": "", "수정할연락처": "", "비고": "",
        })
    rows.sort(key=lambda x: (x["출처"], x["담당부서"]))

    # CSV 저장 (엑셀에서 바로 열어 검수 가능하도록 BOM 포함 utf-8-sig)
    with open(CSV_OUT, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # Markdown 표 저장 (공문/메일 첨부용)
    with open(MD_OUT, "w", encoding="utf-8") as f:
        f.write("# 담당부서·연락처 검수 요청 목록\n\n")
        f.write("아래는 AI 통합 검색 시스템에 표시되는 담당부서·연락처 목록입니다. "
                "실제와 다른 항목이 있으면 '검수결과' 칸에 X, '수정할 연락처' 칸에 "
                "올바른 정보를 적어 회신 부탁드립니다.\n\n")
        f.write("| 출처 | 담당부서 | 현재 연락처 | 해당 규정 수 | 규정명(예시) | 검수결과(O/X) | 수정할 연락처 |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for row in rows:
            f.write(f"| {row['출처']} | {row['담당부서']} | {row['연락처']} | "
                    f"{row['해당규정수']} | {row['규정명예시']} |  |  |\n")

    print(f"[완료] 담당부서·연락처 조합 {len(rows)}건 추출")
    print(f"  CSV(엑셀용): {CSV_OUT}")
    print(f"  MD(문서용) : {MD_OUT}")

    by_source = defaultdict(int)
    for row in rows:
        by_source[row["출처"]] += 1
    for src, cnt in by_source.items():
        print(f"  - {src}: 부서/연락처 조합 {cnt}개")


if __name__ == "__main__":
    main()
