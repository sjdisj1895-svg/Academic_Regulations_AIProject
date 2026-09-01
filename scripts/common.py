# -*- coding: utf-8 -*-
"""
[T1] 공통 유틸리티
- 웹 페이지 요청(fetch), HTML 태그 제거, 텍스트 정리, 파일명 안전화 등
- 외부 라이브러리 없이 Python 표준 라이브러리만 사용합니다.
"""
import html
import re
import time
import urllib.parse
import urllib.request

# 사이트가 차단하지 않도록 일반 브라우저처럼 보이는 User-Agent 사용
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# 서버에 부담을 주지 않도록 요청 사이에 잠깐 쉬는 시간(초)
REQUEST_DELAY = 0.3


def fetch(url: str, params: dict | None = None, referer: str | None = None,
          decode: bool = True, retries: int = 3):
    """URL 내용을 가져온다. 실패하면 retries번까지 재시도한다."""
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as res:
                raw = res.read()
            time.sleep(REQUEST_DELAY)
            return raw.decode("utf-8", errors="replace") if decode else raw
        except Exception as e:  # 네트워크 오류 시 재시도
            last_err = e
            print(f"    [재시도 {attempt}/{retries}] 요청 실패: {url[:80]} ({e})")
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"요청 실패(재시도 초과): {url} / 마지막 오류: {last_err}")


# 태그 속성 안의 따옴표('>' 포함 가능)까지 올바르게 인식하는 태그 패턴
_TAG = r"""<[!/]?[a-zA-Z][^>"']*(?:"[^"]*"[^>"']*|'[^']*'[^>"']*)*/?>"""


def strip_tags(fragment: str) -> str:
    """HTML 조각에서 태그를 제거하고 사람이 읽는 텍스트만 남긴다."""
    # script/style 통째로 제거
    fragment = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", fragment,
                      flags=re.S | re.I)
    # HTML 주석 제거
    fragment = re.sub(r"<!--.*?-->", " ", fragment, flags=re.S)
    # 줄바꿈 성격의 태그는 개행으로 변환 (조문 구분 유지)
    fragment = re.sub(r"<(br|/p|/div|/li|/tr|/h\d)[^>]*>", "\n", fragment, flags=re.I)
    # 속성값에 '>' 가 들어간 태그도 안전하게 제거
    fragment = re.sub(_TAG, " ", fragment, flags=re.S)
    # 남은 잔여 태그 제거 (형식이 깨진 태그 대비)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html.unescape(fragment)
    # law.go.kr 화면 조각(onclick 잔여물 등) 제거
    fragment = re.sub(r"'\);return false;\"[^>\n]*>", " ", fragment)
    fragment = re.sub(r'[\w가-힣 ]*"\s+(?:src|value|alt|title)="[^"]*"\s*/?>?', " ",
                      fragment)
    return clean_text(fragment)


def clean_text(text: str) -> str:
    """깨진 문자·불필요한 공백을 정리한다."""
    # 제어문자 제거 (개행/탭 제외)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufeff]", "", text)
    # 각 줄의 앞뒤 공백 정리, 연속 공백 축소
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t\u00a0\u3000]+", " ", line).strip()
        lines.append(line)
    text = "\n".join(lines)
    # 3줄 이상 연속 빈 줄은 1줄로
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def safe_filename(name: str, max_len: int = 80) -> str:
    """규정명을 파일명으로 쓸 수 있게 특수문자를 제거한다."""
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:max_len].strip(" ._")
