# -*- coding: utf-8 -*-
"""
[T2] 조·항 단위 청킹 프로그램
- data/regulations.json 의 각 규정 텍스트를 읽어
  '제0조(제목)' 단위로 자르고, 조문이 길면 '제0항(①②③...)' 단위로 더 자릅니다.
- 부칙·별표처럼 조문 구조가 아닌 부분도 별도 청크로 보존합니다.
- [T12] 각 조문이 속한 '제0장(장 제목)'을 함께 추출해 "chapter" 메타데이터로 붙입니다.
  (예: "제7장 휴학, 복학, 재입학, 편입학, 유급, 퇴학 및 제적"). 짧은 조문 하나만 봐서는
  주제를 알기 어려운 경우(예: 위임 조항)에도, 소속된 장 제목이 임베딩에 함께 들어가면
  검색 엔진이 문맥을 더 잘 파악해 질문형 질의의 정확도가 올라간다 (build_vectordb.py에서 사용).
- 결과: data/chunks.json  (청크 목록 + 메타데이터)

사용법:
    python scripts/chunk_rules.py              # 전체 규정 청킹
    python scripts/chunk_rules.py --name 인권센터  # 이름에 '인권센터'가 들어간 규정만 다시 청킹
"""
import json
import os
import re
import sys

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
REGS = os.path.join(DATA_DIR, "regulations.json")
OUT = os.path.join(DATA_DIR, "chunks.json")

# 청크 하나의 적정 글자 수 (임베딩 모델 입력 한계 고려)
MAX_CHARS = 900
# 항 기호 (한글 문서에서 쓰는 원문자)
HANG_MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

# 조문 시작 패턴: 줄 시작의 '제12조(목적)' / '제12조의2(…)'
JO_PAT = re.compile(r"(?m)^(제\s*\d+\s*조(?:의\s*\d+)?)\s*(\([^)]{1,60}\))?")
# 부칙/별표/별지 시작 패턴
BUCHIK_PAT = re.compile(r"(?m)^(부\s*칙|별\s*표|별\s*지|\[별표|\〔별표|\[별지)")
# [T12] 장(章) 제목 시작 패턴: 줄 시작의 '제7장 휴학, 복학...' (한 줄 전체를 장 제목으로 사용)
CHAPTER_PAT = re.compile(r"(?m)^(제\s*\d+\s*장[^\n]{0,60})")


def _build_chapter_lookup(text: str):
    """본문에서 장(章) 제목들의 위치를 찾아, 문서 내 임의 위치가 어느 장에 속하는지
    알려주는 조회 함수를 만든다. (장 구분이 없는 규정은 항상 빈 문자열 반환)
    """
    marks = [(m.start(), re.sub(r"\s+", " ", m.group(1)).strip())
             for m in CHAPTER_PAT.finditer(text)]
    if not marks:
        return lambda pos: ""

    def lookup(pos: int) -> str:
        current = ""
        for start, title in marks:
            if start <= pos:
                current = title
            else:
                break
        return current

    return lookup


def read_body(text_file: str) -> str:
    """저장된 규정 텍스트에서 머리말(======= 위)을 떼고 본문만 반환."""
    path = os.path.join(DATA_DIR, text_file)
    with open(path, encoding="utf-8") as f:
        content = f.read()
    sep = content.find("=" * 40)
    return content[sep + 40:].strip() if sep >= 0 else content.strip()


def split_by_hang(jo_text: str):
    """긴 조문을 '항(①②…)' 단위로 나눈다. 항이 없으면 글자 수로 나눈다."""
    marks = [m.start() for m in re.finditer(f"[{HANG_MARKS}]", jo_text)]
    if len(marks) >= 2:
        pieces, starts = [], [0] + marks[1:]
        for i, s in enumerate(starts):
            e = starts[i + 1] if i + 1 < len(starts) else len(jo_text)
            piece = jo_text[s:e].strip()
            if piece:
                # 항 번호 추출 (①=제1항)
                hang_no = ""
                m = re.match(f"[{HANG_MARKS}]", piece)
                if m:
                    hang_no = f"제{HANG_MARKS.index(m.group(0)) + 1}항"
                elif i == 0:
                    hang_no = "제1항"
                pieces.append((hang_no, piece))
        return pieces
    # 항이 없으면 문단/글자수 기준 분할
    pieces = []
    buf = ""
    for para in jo_text.split("\n"):
        if len(buf) + len(para) > MAX_CHARS and buf:
            pieces.append(("", buf.strip()))
            buf = para
        else:
            buf += ("\n" if buf else "") + para
    if buf.strip():
        pieces.append(("", buf.strip()))
    return pieces


def chunk_one(reg: dict):
    """규정 1건을 조·항 단위 청크 목록으로 변환."""
    body = read_body(reg["text_file"])
    chunks = []

    # 1) 부칙/별표 위치에서 본칙과 분리
    bm = BUCHIK_PAT.search(body)
    main_part = body[:bm.start()] if bm else body
    extra_part = body[bm.start():] if bm else ""

    # 2) 본칙: 조 단위 분할
    jo_matches = list(JO_PAT.finditer(main_part))
    chapter_of = _build_chapter_lookup(main_part)  # [T12] 위치 → 소속 장(章) 제목
    if jo_matches:
        # 첫 조문 앞의 머리글(제정·시행 정보)은 첫 청크로
        head = main_part[:jo_matches[0].start()].strip()
        if len(head) > 30:
            chunks.append({"article": "머리말", "clause": "", "text": head})
        for i, m in enumerate(jo_matches):
            end = jo_matches[i + 1].start() if i + 1 < len(jo_matches) else len(main_part)
            jo_no = re.sub(r"\s+", "", m.group(1))          # 제12조
            jo_title = (m.group(2) or "").strip("() ")      # 목적
            jo_text = main_part[m.start():end].strip()
            chapter = chapter_of(m.start())                 # [T12] 이 조문이 속한 장 제목
            if len(jo_text) <= MAX_CHARS:
                chunks.append({"article": jo_no, "article_title": jo_title,
                               "clause": "", "text": jo_text, "chapter": chapter})
            else:
                for hang_no, piece in split_by_hang(jo_text):
                    chunks.append({"article": jo_no, "article_title": jo_title,
                                   "clause": hang_no, "text": piece, "chapter": chapter})
    elif main_part.strip():
        # 조문 구조가 없는 규정(윤리강령 등): 문단 묶음으로 분할
        for _, piece in split_by_hang(main_part.strip()):
            chunks.append({"article": "전문", "clause": "", "text": piece})

    # 3) 부칙/별표: 구획 단위로 분할
    if extra_part.strip():
        parts = list(BUCHIK_PAT.finditer(extra_part))
        for i, m in enumerate(parts):
            end = parts[i + 1].start() if i + 1 < len(parts) else len(extra_part)
            seg = extra_part[m.start():end].strip()
            label = re.sub(r"\s+", "", m.group(1)).strip("[〔")
            for _, piece in ([("", seg)] if len(seg) <= MAX_CHARS
                             else split_by_hang(seg)):
                chunks.append({"article": label, "clause": "", "text": piece})

    # 4) 메타데이터 부착
    results = []
    for i, c in enumerate(chunks):
        text = c["text"].strip()
        if len(text) < 15:  # 의미 없는 짧은 조각 제외
            continue
        results.append({
            "chunk_id": f"{reg['id']}#{i}",
            "reg_id": reg["id"],
            "source": reg["source"],              # 대학 / 산학협력단
            "category": reg["category"],          # 학칙/규정/지침/제N편…
            "name": reg["name"],                  # 규정명
            "article": c.get("article", ""),      # 제0조 / 부칙 / 별표
            "article_title": c.get("article_title", ""),
            "chapter": c.get("chapter", ""),       # [T12] 소속 장(章) 제목 (검색 문맥 보강용)
            "clause": c.get("clause", ""),        # 제0항
            "department": reg["department"],
            "contact": reg["contact"],
            "source_url": reg["source_url"],
            "law_url": reg.get("law_url", ""),
            "text": text,
        })
    return results


def main():
    # --name 옵션: 특정 규정만 다시 청킹 (개정 대응)
    name_filter = None
    if "--name" in sys.argv:
        idx = sys.argv.index("--name")
        if idx + 1 < len(sys.argv):
            name_filter = sys.argv[idx + 1]

    with open(REGS, encoding="utf-8") as f:
        regs = json.load(f)

    # 기존 청크 불러오기 (부분 갱신 시 유지)
    old_chunks = []
    if name_filter and os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            old_chunks = json.load(f)

    targets = [r for r in regs
               if not name_filter or name_filter in r["name"]]
    print(f"[청킹 시작] 대상 규정 {len(targets)}건"
          + (f" (필터: '{name_filter}')" if name_filter else ""))

    all_chunks, failed, per_reg = [], [], {}
    for reg in targets:
        try:
            chunks = chunk_one(reg)
            if not chunks:
                failed.append({"name": reg["name"], "reason": "청크 0개 생성"})
                continue
            all_chunks.extend(chunks)
            per_reg[reg["name"]] = len(chunks)
        except Exception as e:
            failed.append({"name": reg["name"], "reason": str(e)})

    # 부분 갱신: 대상 규정의 기존 청크를 제거하고 새 청크로 교체
    if name_filter:
        target_ids = {r["id"] for r in targets}
        kept = [c for c in old_chunks if c["reg_id"] not in target_ids]
        all_chunks = kept + all_chunks

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=1)

    # 요약 출력
    print(f"\n[청킹 결과 요약]")
    print(f"  전체 청크 수: {len(all_chunks):,}개")
    print(f"  규정 수: {len(per_reg)}건 / 실패 {len(failed)}건")
    if per_reg:
        top = sorted(per_reg.items(), key=lambda x: -x[1])[:10]
        print("  청크 많은 규정 TOP10:")
        for name, cnt in top:
            print(f"    {cnt:4d}개  {name}")
        avg = sum(per_reg.values()) / len(per_reg)
        print(f"  규정당 평균 청크: {avg:.1f}개")
    if failed:
        print("  [실패 목록]")
        for f_ in failed:
            print(f"    - {f_['name']}: {f_['reason']}")
    with open(os.path.join(DATA_DIR, "chunk_report.json"), "w", encoding="utf-8") as f:
        json.dump({"total_chunks": len(all_chunks), "per_regulation": per_reg,
                   "failed": failed}, f, ensure_ascii=False, indent=1)
    print(f"[저장] {OUT}")


if __name__ == "__main__":
    main()
