# -*- coding: utf-8 -*-
"""
[T1] 대학 규정 수집기
- 학칙: https://www.gnu.ac.kr/main/cm/cntnts/cntntsView.do?mi=1255&cntntsId=1214
        (페이지 안의 국가법령정보센터 iframe에서 전문 추출)
- 규정: 게시판 mi=1436, bbsId=1091 (약 230건)
- 지침: 게시판 mi=1886, bbsId=1153 (약 134건)

각 게시글 상세에서 국가법령정보센터(law.go.kr) 링크를 찾아 규정 전문을 추출합니다.
결과: data/university/<카테고리>/<규정명>.txt + data/progress_university.jsonl

한 번 수집한 규정은 progress 파일에 기록되어, 다시 실행하면 건너뜁니다(이어받기).
"""
import json
import math
import os
import re
import sys
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(__file__))
from common import fetch, strip_tags, clean_text, safe_filename

BASE = "https://www.gnu.ac.kr"
HAKCHIK_URL = f"{BASE}/main/cm/cntnts/cntntsView.do?mi=1255&cntntsId=1214"
BOARDS = {
    "규정": {"mi": "1436", "bbsId": "1091"},
    "지침": {"mi": "1886", "bbsId": "1153"},
}
# 사이트에 게시된 관리부서 연락처 (규정별 부서 전화는 사이트에 미게재)
SITE_CONTACT = "총무과 055-772-0334"

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
PROGRESS = os.path.join(DATA_DIR, "progress_university.jsonl")
ERRORS = os.path.join(DATA_DIR, "errors_university.json")


# ---------------------------------------------------------------- 진행 기록
def load_progress() -> dict:
    done = {}
    if os.path.exists(PROGRESS):
        with open(PROGRESS, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    done[rec["id"]] = rec
    return done


def append_progress(rec: dict):
    with open(PROGRESS, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- 목록 파싱
def parse_list_page(html: str):
    """게시판 목록 HTML에서 행(규정) 정보를 뽑는다."""
    rows = []
    tbody = re.search(r"<tbody.*?</tbody>", html, re.S)
    if not tbody:
        return rows
    for tr in re.findall(r"<tr.*?</tr>", tbody.group(0), re.S):
        m = re.search(r'data-id="(\d+)"', tr)
        if not m:
            continue
        ntt_sn = m.group(1)
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        cells = [strip_tags(td).replace("\n", " ").strip() for td in tds]
        # 열 구조: 번호 | 소관부서 | 규정번호 | 규정명 | 공포일자 | 조회수
        if len(cells) >= 6:
            rows.append({
                "nttSn": ntt_sn, "department": cells[1], "rule_no": cells[2],
                "name": cells[3], "date": cells[4],
            })
        elif len(cells) >= 4:  # 예외적 구조 대비
            rows.append({
                "nttSn": ntt_sn, "department": cells[1], "rule_no": "",
                "name": cells[-3], "date": cells[-2],
            })
    return rows


def total_count(html: str) -> int:
    m = re.search(r"전체[^\d]{0,40}([\d,]+)", re.sub(r"<[^>]+>", " ", html))
    return int(m.group(1).replace(",", "")) if m else 0


# law.go.kr 페이지는 조문이 시작되기 직전에
# "경상국립대학교 OO처(OO과), 000-000-0000" 형식으로 실제 담당부서·연락처를 표시한다.
# (예: "경상국립대학교 교무처(교무과), 055-772-0102")
CONTACT_LINE_RE = re.compile(r"^(.{2,40}),\s*(\d[\d\-]{6,17})\s*$", re.M)


def _extract_contact(header_text: str) -> Optional[str]:
    """본문 시작 전 헤더 영역에서 '담당부서, 전화번호' 줄을 찾아 '부서 전화번호' 형태로 반환한다.
    여러 줄 중 본문(조문)에 가장 가까운(마지막) 매치를 사용한다.
    """
    matches = list(CONTACT_LINE_RE.finditer(header_text))
    if not matches:
        return None
    dept, phone = matches[-1].group(1).strip(), matches[-1].group(2).strip()
    dept = re.sub(r"^(경상국립대학교|경남과학기술대학교)\s*", "", dept)  # 대학명 접두사 제거
    return f"{dept} {phone}"


# ------------------------------------------------------- law.go.kr 전문 추출
def law_fulltext(seq: str) -> Tuple[str, Optional[str]]:
    """국가법령정보센터에서 규정 전문 텍스트와 실제 담당부서·연락처를 가져온다.

    반환값: (본문 텍스트, "담당부서 전화번호" 문자열 또는 못 찾으면 None)

    이전에는 본문을 "제1장/제1조"부터만 잘라 쓰면서, 그 바로 위에 있던 실제
    담당부서·연락처 줄을 화면 메뉴 텍스트로 오인해 함께 버리고 있었다. 그 결과
    모든 규정에 사이트 대표번호(SITE_CONTACT)만 고정으로 채워지고 있었다.
    """
    html = fetch("https://www.law.go.kr/LSW/schlPubRulInfoR.do",
                 params={"schlPubRulSeq": seq, "joTpYn": "Y",
                         "languageType": "KO", "chrClsCd": "010202"},
                 referer="https://www.law.go.kr/")
    full = strip_tags(html)
    # 본문 시작(첫 조문/장) 이전의 화면 메뉴 텍스트 제거
    m = re.search(r"(제\s*1\s*장|제\s*1\s*조)", full)
    if m:
        header, text = full[:m.start()], full[m.start():]
        if re.search(r"제\s*\d+\s*조", text):
            return clean_text(text), _extract_contact(header)
    # 조문 구조가 없는 규정(윤리강령·폐지 규정 등): '[시행 ...]' 표기부터 본문 추출
    m = re.search(r"\[\s*시행\s*[\d.\s]+\]", full)
    if m:
        # 규정명이 [시행] 바로 앞 줄에 있으므로 그 줄부터 시작
        start = full.rfind("\n", 0, m.start())
        header = full[:start + 1 if start >= 0 else 0]
        body = clean_text(full[start + 1 if start >= 0 else 0:])
        if len(body) > 50:
            return body, _extract_contact(header)
    raise RuntimeError(f"law.go.kr 전문에서 본문을 찾지 못함 (seq={seq})")


def find_law_seq(html: str) -> Optional[str]:
    m = re.search(r"schlPubRulInfoP\.do\?schlPubRulSeq=(\d+)", html)
    return m.group(1) if m else None


# ---------------------------------------------------------------- 저장
def save_text(category: str, name: str, meta: dict, body: str) -> str:
    folder = os.path.join(DATA_DIR, "university", category)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, safe_filename(name) + ".txt")
    header = [
        f"규정명: {meta['name']}",
        f"출처: 대학",
        f"카테고리: {category}",
        f"소관부서: {meta.get('department', '')}",
        f"규정번호: {meta.get('rule_no', '')}",
        f"공포일자: {meta.get('date', '')}",
        f"원본 URL: {meta.get('source_url', '')}",
        f"전문 URL: {meta.get('law_url', '')}",
        "=" * 40, "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(header) + body + "\n")
    return path


# ---------------------------------------------------------------- 수집 본체
def collect_hakchik(done: dict, errors: list):
    """'학칙' 카테고리: 콘텐츠 페이지의 law.go.kr iframe에서 전문 추출."""
    key = "학칙:main"
    if key in done:
        print("  [건너뜀] 학칙 (이미 수집됨)")
        return
    try:
        html = fetch(HAKCHIK_URL)
        seq = find_law_seq(html)
        if not seq:
            raise RuntimeError("학칙 페이지에서 law.go.kr 링크를 찾지 못함")
        info_p = fetch("https://www.law.go.kr/LSW/schlPubRulInfoP.do",
                       params={"schlPubRulSeq": seq})
        m = (re.search(r'id="schlPubRulNm"[^>]*value="([^"]+)"', info_p)
             or re.search(r'name="schlPubRulNm"[^>]*value="([^"]+)"', info_p))
        name = m.group(1).strip() if m else "경상국립대학교 학칙"
        body, law_contact = law_fulltext(seq)
        meta = {
            "id": key, "source": "대학", "category": "학칙", "name": name,
            "department": "총무과", "contact": law_contact or SITE_CONTACT, "rule_no": "",
            "date": "", "source_url": HAKCHIK_URL,
            "law_url": f"https://www.law.go.kr/LSW/schlPubRulInfoP.do?schlPubRulSeq={seq}",
        }
        # "/"로 저장해 리눅스에서도 그대로 열 수 있게 한다 (os.path.relpath는
        # Windows에서 "\\" 구분자를 반환하는데, 리눅스는 이를 경로 구분자로 인식하지 않음)
        meta["text_file"] = os.path.relpath(
            save_text("학칙", name, meta, body), DATA_DIR).replace("\\", "/")
        append_progress(meta)
        print(f"  [완료] 학칙: {name} ({len(body):,}자)")
    except Exception as e:
        errors.append({"category": "학칙", "name": "경상국립대학교 학칙", "error": str(e)})
        print(f"  [오류] 학칙: {e}")


def collect_board(category: str, cfg: dict, done: dict, errors: list):
    """'규정'/'지침' 게시판 전체 페이지를 순회하며 수집."""
    list_url = f"{BASE}/main/na/ntt/selectNttList.do"
    first = fetch(list_url, params={"mi": cfg["mi"], "bbsId": cfg["bbsId"], "currPage": 1})
    total = total_count(first)
    pages = max(1, math.ceil(total / 10))
    print(f"  [{category}] 전체 {total}건 / {pages}페이지")

    count = 0
    for page in range(1, pages + 1):
        html = first if page == 1 else fetch(
            list_url, params={"mi": cfg["mi"], "bbsId": cfg["bbsId"], "currPage": page})
        rows = parse_list_page(html)
        if not rows:
            print(f"  [{category}] {page}페이지: 행 없음, 중단")
            break
        for row in rows:
            count += 1
            key = f"{category}:{row['nttSn']}"
            if key in done:
                continue
            detail_url = (f"{BASE}/main/na/ntt/selectNttInfo.do"
                          f"?mi={cfg['mi']}&bbsId={cfg['bbsId']}&nttSn={row['nttSn']}")
            try:
                detail = fetch(detail_url)
                seq = find_law_seq(detail)
                if not seq:
                    raise RuntimeError("상세 페이지에 law.go.kr 전문 링크 없음")
                body, law_contact = law_fulltext(seq)
                meta = {
                    "id": key, "source": "대학", "category": category,
                    "name": row["name"], "department": row["department"],
                    "contact": law_contact or SITE_CONTACT, "rule_no": row["rule_no"],
                    "date": row["date"], "source_url": detail_url,
                    "law_url": f"https://www.law.go.kr/LSW/schlPubRulInfoP.do?schlPubRulSeq={seq}",
                }
                meta["text_file"] = os.path.relpath(
                    save_text(category, row["name"], meta, body), DATA_DIR).replace("\\", "/")
                append_progress(meta)
                done[key] = meta
                print(f"  [완료] {category} {count}/{total}: {row['name']}")
            except Exception as e:
                errors.append({"category": category, "name": row["name"],
                               "url": detail_url, "error": str(e)})
                print(f"  [오류] {category}: {row['name']} - {e}")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    done = load_progress()
    errors = []
    print("[대학 규정 수집 시작]")
    collect_hakchik(done, errors)
    for category, cfg in BOARDS.items():
        collect_board(category, cfg, done, errors)
    with open(ERRORS, "w", encoding="utf-8") as f:
        json.dump(errors, f, ensure_ascii=False, indent=2)
    done = load_progress()
    print(f"[대학 규정 수집 종료] 성공 {len(done)}건 / 오류 {len(errors)}건"
          f" (오류 목록: data/errors_university.json)")
    return done, errors


if __name__ == "__main__":
    main()
