# -*- coding: utf-8 -*-
"""
[T20] 규정 메타데이터 보강 — 시행일·공포(개정)일·개정 종류·현행/폐지 상태

규정은 "언제 기준인가"가 핵심인데 지금까지 카드에 날짜가 없었다. 본문(.txt)과 청크는
그대로 두고 regulations.json에만 아래 필드를 덧붙인다 (재수집·벡터DB 재구축 불필요 —
검색 엔진이 결과를 조립할 때 reg_id로 붙여 준다).

  enforce_date   : 시행일           예) 2026-05-29
  revision_date  : 공포(최종 개정)일 예) 2026-05-29
  revision_type  : 제정 / 일부개정 / 전부개정 / 폐지 / 개정(산학협력단은 종류 미표기)
  rule_no        : 규정 번호        예) 경상국립대학교학칙 제529호
  status         : 현행 / 폐지

출처별 방법
  대학(363건)     : law.go.kr 원문 헤더의 "[시행 2026.5.29.] [경상국립대학교학칙 제529호,
                    2026.5.29., 일부개정]" 표기를 파싱 (규정당 요청 1회, 약 3~4분)
  산학협력단(63건) : 규정집(hwpx) 원문 안의 "제정 2004.01.30 / 개정 2025.07.01" 이력 줄에서
                    마지막 날짜를 최종 개정일로 사용 (요청 없음)

사용법:
    python scripts/enrich_dates.py            # 전체
    python scripts/enrich_dates.py --limit 5  # 앞 5건만 (동작 확인용)
"""
import io
import json
import os
import re
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import fetch, strip_tags  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
REGS_PATH = os.path.join(DATA_DIR, "regulations.json")

# "[시행 2026.5.29.] [경상국립대학교학칙 제529호, 2026.5.29., 일부개정]"
HEADER_RE = re.compile(
    r"\[\s*시행\s*(?P<enf>\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2})\s*\.?\s*\]"
    r"\s*\[\s*(?P<no>[^,\]]+?)\s*,\s*(?P<rev>\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2})\s*\.?\s*,\s*(?P<type>[^\]]+?)\s*\]")
# 산학협력단 본문의 이력 줄: "제정 2004.01.30", "개정 2025. 7. 1."
HISTORY_RE = re.compile(r"(제정|개정|전부개정|일부개정|폐지)\s*[:：]?\s*(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})")


def norm_date(s: str) -> str:
    m = re.match(r"\s*(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})", s)
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""


def parse_law_header(seq: str) -> dict:
    html = fetch("https://www.law.go.kr/LSW/schlPubRulInfoR.do",
                 params={"schlPubRulSeq": seq, "joTpYn": "Y",
                         "languageType": "KO", "chrClsCd": "010202"},
                 referer="https://www.law.go.kr/")
    full = strip_tags(html)
    m = HEADER_RE.search(full)
    if not m:
        return {}
    return {
        "enforce_date": norm_date(m.group("enf")),
        "revision_date": norm_date(m.group("rev")),
        "revision_type": re.sub(r"\s+", "", m.group("type")),
        "rule_no": re.sub(r"\s+", " ", m.group("no")).strip(),
    }


def parse_text_history(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    hits = HISTORY_RE.findall(text)
    if not hits:
        return {}
    dates = [(kind, f"{y}-{int(mo):02d}-{int(d):02d}") for kind, y, mo, d in hits]
    first = next((d for k, d in dates if k == "제정"), None)
    last_kind, last_date = dates[-1]
    return {
        "enforce_date": last_date,
        "revision_date": last_date,
        "revision_type": "제정" if last_kind == "제정" and (first == last_date) else ("폐지" if last_kind == "폐지" else "개정"),
        "rule_no": "",
    }


def decide_status(reg: dict, meta: dict) -> str:
    if "폐지" in reg.get("name", "") or "폐지" in meta.get("revision_type", ""):
        return "폐지"
    return "현행"


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    with open(REGS_PATH, encoding="utf-8") as f:
        regs = json.load(f)

    targets = regs[:limit] if limit else regs
    ok = miss = 0
    for i, reg in enumerate(targets, 1):
        meta = {}
        try:
            if reg["source"] == "대학" and reg.get("law_url"):
                seq = re.search(r"schlPubRulSeq=\s*(\d+)", reg["law_url"])
                if seq:
                    meta = parse_law_header(seq.group(1))
            else:
                path = os.path.join(DATA_DIR, *reg["text_file"].replace("\\", "/").split("/"))
                if os.path.exists(path):
                    meta = parse_text_history(path)
        except Exception as e:
            print(f"  [경고] {reg['name']}: {e}")
        if meta.get("enforce_date"):
            ok += 1
        else:
            miss += 1
        reg["enforce_date"] = meta.get("enforce_date", "")
        reg["revision_date"] = meta.get("revision_date", "") or reg.get("date", "").replace(".", "-")
        reg["revision_type"] = meta.get("revision_type", "")
        if meta.get("rule_no"):
            reg["rule_no"] = meta["rule_no"]
        reg["status"] = decide_status(reg, meta)
        if i % 25 == 0 or i == len(targets):
            print(f"  {i}/{len(targets)} 처리 (시행일 확보 {ok}, 미확보 {miss})")

    with open(REGS_PATH, "w", encoding="utf-8") as f:
        json.dump(regs, f, ensure_ascii=False, indent=1)

    repealed = [r["name"] for r in regs if r.get("status") == "폐지"]
    print(f"[완료] 시행일 확보 {ok}/{len(targets)} · 폐지 규정 {len(repealed)}건: {repealed}")
    print(f"[저장] {REGS_PATH}")


if __name__ == "__main__":
    main()
