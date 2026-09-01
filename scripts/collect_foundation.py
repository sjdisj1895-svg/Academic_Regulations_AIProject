# -*- coding: utf-8 -*-
"""
[T1] 산학협력단 규정 수집기
- 게시판: https://www.gnu.ac.kr/research/na/ntt/selectNttList.do?mi=7117&bbsId=2456
- 가장 최신 '산학협력단 규정집' 게시글의 첨부파일(HWPX, 통합 규정집)을 내려받아
  목차(규정명/관리부서)를 파싱한 뒤, 본문을 규정별로 분할하여 저장합니다.

결과: data/foundation/<규정명>.txt + data/progress_foundation.json
"""
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from common import fetch, clean_text, safe_filename

BASE = "https://www.gnu.ac.kr"
LIST_URL = f"{BASE}/research/na/ntt/selectNttList.do?mi=7117&bbsId=2456"
# 산학협력단 사이트 하단 게시 연락처 (산학연구과)
DEPT_CONTACTS = {"산학연구과": "055-772-0211", "산학지원과": "055-772-0213",
                 "기술비즈니스센터": "055-772-0255"}

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
OUT_DIR = os.path.join(DATA_DIR, "foundation")
RESULT = os.path.join(DATA_DIR, "progress_foundation.json")
ERRORS = os.path.join(DATA_DIR, "errors_foundation.json")


# ------------------------------------------------- 1) 최신 게시글/첨부 찾기
def find_latest_post():
    """게시판 목록 첫 행(최신 게시글)의 번호와 제목을 반환."""
    html = fetch(LIST_URL)
    m = re.search(r'<a[^>]*data-id="(\d+)"[^>]*class="nttInfoBtn"[^>]*>(.*?)</a>',
                  html, re.S)
    if not m:
        raise RuntimeError("게시판에서 최신 게시글을 찾지 못했습니다")
    ntt_sn = m.group(1)
    title = re.sub(r"<[^>]+>", "", m.group(2))
    title = re.sub(r"\s+", " ", title).strip()
    return ntt_sn, title


def find_attachment(ntt_sn: str):
    """상세 페이지에서 '규정집' HWPX/HWP 첨부의 다운로드 키와 파일명을 찾는다."""
    url = f"{BASE}/research/na/ntt/selectNttInfo.do?mi=7117&bbsId=2456&nttSn={ntt_sn}"
    html = fetch(url)
    files = []
    for m in re.finditer(
            r'href="/common/nttFileDownload\.do\?fileKey=([0-9a-f]+)"[^>]*>(.*?)</a>',
            html, re.S):
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip()
        files.append({"fileKey": m.group(1), "fileName": name})
    if not files:
        raise RuntimeError("상세 페이지에서 첨부파일을 찾지 못했습니다")
    # '규정집'이 이름에 들어간 hwp/hwpx 파일 우선
    for f in files:
        if "규정집" in f["fileName"] and re.search(r"\.hwpx?", f["fileName"]):
            return url, f
    return url, files[0]


# ------------------------------------------------- 2) HWPX 텍스트 추출
def hwpx_paragraphs(path: str):
    """HWPX(ZIP+XML)에서 전체 문단 텍스트 목록을 순서대로 추출."""
    z = zipfile.ZipFile(path)
    sections = sorted(
        [n for n in z.namelist() if re.match(r"Contents/section\d+\.xml", n)],
        key=lambda n: int(re.search(r"(\d+)", n).group(1)))
    if not sections:
        raise RuntimeError("HWPX 안에 본문(section) XML이 없습니다 (HWP 구버전일 수 있음)")
    paras = []
    for name in sections:
        xml = z.read(name).decode("utf-8", errors="replace")
        for pm in re.finditer(r"<hp:p[ >].*?</hp:p>", xml, re.S):
            texts = re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", pm.group(0), re.S)
            t = re.sub(r"<[^>]+>", "", "".join(texts))
            t = t.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
            # 한글 하이퍼링크 내부 코드 제거
            t = re.sub(r"HWPHYPERLINK\S*", "", t)
            paras.append(clean_text(t))
    return paras


# ------------------------------------------------- 3) 목차 파싱
def parse_toc(paras):
    """목차에서 (규정명, 편 제목, 관리부서) 목록과 목차 끝 위치를 얻는다."""
    toc, part = [], ""
    toc_end = 0
    for i, t in enumerate(paras[:800]):  # 목차는 문서 앞부분에 존재
        pm = re.match(r"^제\s*(\d+)\s*편\s*(.+)$", t)
        if pm:
            part = f"제{pm.group(1)}편 {pm.group(2).strip()}"
            toc_end = i
            continue
        # '28.' 또는 '28 ' 처럼 번호 뒤 점이 없는 경우도 허용
        m = re.match(r"^(\d{1,3})[.\s]\s*(.+?)\s*$", t)
        # 제목 끝의 [교육부고시 제...호] 같은 괄호 표기는 빼고 판정
        if m and re.search(r"(정관|규정|지침|예규|세칙|요령|규칙|법|시행령)\s*(\[[^\]]*\])?\s*$",
                           m.group(2)):
            name = re.sub(r"\s+", " ", m.group(2)).strip()
            # 목차 항목 뒤쪽 문단(페이지, ~, 페이지, 관리부서)에서 부서 찾기
            dept = ""
            for j in range(i + 1, min(i + 6, len(paras))):
                if re.match(r"^[가-힣]+(과|실|센터|단)$", paras[j]):
                    dept = paras[j]
                    break
            toc.append({"no": int(m.group(1)), "name": name,
                        "part": part, "department": dept})
            toc_end = i
    return toc, toc_end


# ------------------------------------------------- 4) 본문 분할
def normalize(s: str) -> str:
    return re.sub(r"[\s·ㆍ・「」『』()\[\]〔〕<>,.'\"‘’“”]+", "", s)


def loose(s: str) -> str:
    """대괄호 표기·'산학협력단' 등 가변 표현을 제거한 비교용 문자열."""
    s = re.sub(r"\[[^\]]*\]", "", s)
    s = normalize(s)
    return s.replace("산학협력단", "")


def split_rules(paras, toc, toc_end):
    """목차의 각 규정명이 본문에서 처음 나타나는 위치를 찾아 규정별로 나눈다."""
    positions, missing = [], []
    for item in toc:
        target = normalize(item["name"])
        target_loose = loose(item["name"])
        pos = -1
        # 1차: 정확히 일치하는 제목 찾기
        for i in range(toc_end + 1, len(paras)):
            t = paras[i]
            if not t or len(t) > len(item["name"]) + 30:
                continue
            if normalize(t) == target:
                pos = i
                break
        # 2차: 표기가 조금 다른 제목(예: '산학협력단' 유무) 유연하게 찾기
        if pos == -1:
            for i in range(toc_end + 1, len(paras)):
                t = paras[i]
                if not t or len(t) > len(item["name"]) + 40:
                    continue
                if loose(t) == target_loose:
                    pos = i
                    break
        # 3차: 조사('의') 등 한두 글자 차이까지 유사도로 찾기
        if pos == -1:
            import difflib
            best_ratio = 0.0
            for i in range(toc_end + 1, len(paras)):
                t = paras[i]
                if not t or abs(len(t) - len(item["name"])) > 15 or "제" == t[:1]:
                    continue
                if not re.search(r"(정관|규정|지침|예규|세칙|요령|규칙|법|시행령)\s*$", t):
                    continue
                ratio = difflib.SequenceMatcher(None, loose(t), target_loose).ratio()
                if ratio > best_ratio:
                    best_ratio, pos = ratio, i
            if best_ratio < 0.9:
                pos = -1
        if pos == -1:
            missing.append(item["name"])
        else:
            positions.append((pos, item))
    positions.sort(key=lambda x: x[0])

    rules = []
    for idx, (pos, item) in enumerate(positions):
        end = positions[idx + 1][0] if idx + 1 < len(positions) else len(paras)
        body = "\n".join(t for t in paras[pos:end] if t)
        rules.append({**item, "body": clean_text(body)})
    return rules, missing


# ------------------------------------------------- 5) 저장 및 메인
def save_rule(rule: dict, meta: dict) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, safe_filename(rule["name"]) + ".txt")
    contact = DEPT_CONTACTS.get(rule["department"], "")
    header = [
        f"규정명: {rule['name']}",
        f"출처: 산학협력단",
        f"카테고리: {rule['part'] or '산학협력단 규정'}",
        f"소관부서: {rule['department'] or '산학연구과'}",
        f"연락처: {contact or DEPT_CONTACTS['산학연구과']}",
        f"규정집 기준: {meta['post_title']}",
        f"원본 URL: {meta['post_url']}",
        "=" * 40, "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(header) + rule["body"] + "\n")
    return path


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    errors = []
    print("[산학협력단 규정 수집 시작]")
    try:
        ntt_sn, title = find_latest_post()
        print(f"  최신 게시글: {title} (nttSn={ntt_sn})")
        post_url, att = find_attachment(ntt_sn)
        print(f"  첨부파일: {att['fileName']}")

        # 첨부파일 다운로드
        raw = fetch(f"{BASE}/common/nttFileDownload.do?fileKey={att['fileKey']}",
                    decode=False)
        ext = ".hwpx" if ".hwpx" in att["fileName"] else ".hwp"
        hwp_path = os.path.join(DATA_DIR, "foundation_rulebook" + ext)
        with open(hwp_path, "wb") as f:
            f.write(raw)
        print(f"  다운로드 완료: {hwp_path} ({len(raw):,} 바이트)")

        # 텍스트 추출 → 목차 → 규정별 분할
        paras = hwpx_paragraphs(hwp_path)
        toc, toc_end = parse_toc(paras)
        print(f"  목차에서 {len(toc)}개 규정 발견")
        rules, missing = split_rules(paras, toc, toc_end)
        for name in missing:
            errors.append({"name": name, "error": "본문에서 규정 시작 위치를 찾지 못함"})

        meta = {"post_title": title, "post_url": post_url}
        results = []
        for rule in rules:
            path = save_rule(rule, meta)
            results.append({
                "id": f"산학:{rule['no']}", "source": "산학협력단",
                "category": rule["part"] or "산학협력단 규정", "name": rule["name"],
                "department": rule["department"] or "산학연구과",
                "contact": DEPT_CONTACTS.get(rule["department"],
                                             DEPT_CONTACTS["산학연구과"]),
                "rule_no": "", "date": "", "source_url": post_url,
                "law_url": "",
                "text_file": os.path.relpath(path, DATA_DIR),
            })
            print(f"  [완료] {rule['no']}. {rule['name']} ({len(rule['body']):,}자)")

        with open(RESULT, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    except Exception as e:
        errors.append({"name": "(전체)", "error": str(e)})
        print(f"  [오류] {e}")
        results = []

    with open(ERRORS, "w", encoding="utf-8") as f:
        json.dump(errors, f, ensure_ascii=False, indent=2)
    print(f"[산학협력단 규정 수집 종료] 성공 {len(results)}건 / 오류 {len(errors)}건"
          f" (오류 목록: data/errors_foundation.json)")
    return results, errors


if __name__ == "__main__":
    main()
