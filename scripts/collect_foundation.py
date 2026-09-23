# -*- coding: utf-8 -*-
"""
[T1] 산학협력단 규정 수집기
- 게시판: https://www.gnu.ac.kr/research/na/ntt/selectNttList.do?mi=7117&bbsId=2456
- 가장 최신 '산학협력단 규정집' 게시글의 첨부파일(HWPX, 통합 규정집)을 내려받아
  목차(규정명/관리부서)를 파싱한 뒤, 본문을 규정별로 분할하여 저장합니다.

결과: data/foundation/<규정명>.txt + data/progress_foundation.json
"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from common import fetch, clean_text, safe_filename, USER_AGENT

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
            # (표 형태라 이름 바로 다음 문단은 "시작쪽수"이지만, 이건 문서 자체가 "인쇄한"
            # 페이지 번호일 뿐이다 — 표지·목차 분량 때문에 실제 뷰어가 넘기는 물리적 페이지와는
            # 다르고, 그 차이도 문서 전체에서 일정하지 않다(뒤쪽 첨부법령은 오히려 반대 방향으로
            # 어긋남). 그래서 여기서는 쓰지 않고, get_viewer_page_map()이 실제 뷰어를 통해 직접
            # 확인한 물리적 페이지를 rulebook_page로 쓴다.
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


# ------------------------------------------------- 3-1) 실제 뷰어 쪽수 확인
VIEWER_BASE = "https://viewer.gnu.ac.kr/SynapDocViewServer"


def get_viewer_page_map(att: dict, toc: list) -> dict:
    """'규정집 원문 파일로 이동' 버튼이 실제로 여는 문서뷰어(Synap)에 이 HWPX를 변환 요청해,
    각 규정명이 실제로 시작되는 물리적 쪽수를 알아낸다.

    문서 자체의 목차에 인쇄된 쪽수는 표지·목차 분량만큼 뷰어의 실제 페이지 번호와 어긋나 있고,
    그 어긋남조차 일정하지 않다(뒤쪽에 원문 그대로 첨부된 법령들은 반대 방향으로 어긋남).
    그래서 뷰어가 쪽별로 내려주는 HTML(.files/N.html)을 하나씩 읽어, 각 규정명이 문단 맨 앞에
    나오는 첫 페이지를 그대로 쓴다 — 사용자가 버튼을 눌러 실제로 보게 되는 페이지 번호와
    반드시 일치하도록.
    """
    file_path = f"{BASE}/common/nttFileDownload.do?fileKey={att['fileKey']}"
    body = urllib.parse.urlencode({
        "fileType": "URL", "convertType": "0",
        "filePath": file_path, "fid": att["fileKey"],
    }).encode()
    req = urllib.request.Request(f"{VIEWER_BASE}/jobJson", data=body,
                                  headers={"User-Agent": USER_AGENT})
    job = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace"))
    result_name = job["fileName"]

    # 이미 변환된 파일이면 즉시 완료 상태로 나오지만, 새 파일이면 변환이 끝날 때까지 기다려야 한다.
    for _ in range(40):
        status = json.loads(fetch(f"{VIEWER_BASE}/status/{job['key']}?"))
        if status.get("htmlDone"):
            result_name = status.get("resultFileName") or result_name
            break
        time.sleep(3)
    else:
        raise RuntimeError("문서뷰어 변환이 시간 내에 끝나지 않았습니다")

    files_base = f"{VIEWER_BASE}/result/{result_name}/{result_name}.files/"

    remaining = [(item["name"], normalize(item["name"]), loose(item["name"])) for item in toc]
    page_map = {}
    page_heads = []  # 2차(유사도) 매칭용으로 지나온 쪽의 머리글을 보관
    n = 0
    while remaining:
        n += 1
        try:
            raw = fetch(files_base + f"{n}.html")
        except Exception:
            break  # 문서 끝(더 이상 쪽이 없음)
        text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
        head = re.sub(r"\s+", " ", text).strip()[:150]
        head_norm, head_loose = normalize(head), loose(head)
        page_heads.append((n, head, head_loose))
        for item in remaining:
            name, tgt_norm, tgt_loose = item
            if head_norm.startswith(tgt_norm) or head_loose.startswith(tgt_loose):
                page_map[name] = n
                remaining.remove(item)
                break
        if n > 2000:  # 이상 상황 대비 안전장치
            break

    # 2차: 조사('의') 등 한두 글자 표기 차이는 유사도로 찾는다(split_rules()의 3차 판정과 동일한
    # 기준: 앞부분 유사도 0.85 이상). 대상이 몇 건뿐이라 지나온 쪽 전체를 다시 훑어도 비용이 작다.
    if remaining:
        import difflib
        for name, tgt_norm, tgt_loose in list(remaining):
            best_ratio, best_page = 0.0, None
            for n2, head, head_loose in page_heads:
                ratio = difflib.SequenceMatcher(None, head_loose[:len(tgt_loose)],
                                                 tgt_loose).ratio()
                if ratio > best_ratio:
                    best_ratio, best_page = ratio, n2
            if best_ratio >= 0.85:
                page_map[name] = best_page
                remaining.remove((name, tgt_norm, tgt_loose))

    if remaining:
        print(f"    [경고] 뷰어에서 쪽수를 못 찾은 규정 {len(remaining)}건: "
              f"{[r[0] for r in remaining]}")
    return page_map


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

        # [T41] 실제 뷰어에서 각 규정이 몇 쪽에 있는지 확인 ('원문 파일로 이동' 버튼이 여는
        # 문서와 항상 일치하도록). 뷰어 접속이 실패해도 전체 수집을 막지는 않는다 — 이 경우
        # rulebook_page 없이(페이지 안내만 빠진 채) 계속 진행한다.
        try:
            page_map = get_viewer_page_map(att, toc)
            print(f"  뷰어에서 쪽수 확인: {len(page_map)}/{len(toc)}건")
        except Exception as e:
            page_map = {}
            errors.append({"name": "(전체)", "error": f"뷰어 쪽수 확인 실패: {e}"})
            print(f"  [오류] 뷰어 쪽수 확인 실패: {e}")

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
                "law_url": "", "rulebook_page": page_map.get(rule["name"]),
                # "/"로 저장 (리눅스 호환) — os.path.relpath가 Windows에서 "\\"를 반환하면
                # 리눅스에서 경로 구분자로 인식되지 않아 파일을 못 찾는 문제가 생긴다.
                "text_file": os.path.relpath(path, DATA_DIR).replace("\\", "/"),
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
