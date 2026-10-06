# -*- coding: utf-8 -*-
"""
[GitLab 연동] Merge Request 자동 리뷰 봇

GitLab이 MR 생성/업데이트 시 보내는 Webhook을 api_server.py가 받으면, 이 모듈이:
  1. GitLab API로 MR의 변경 내용(diff)을 가져오고
  2. 코드가 아닌 파일(데이터·이미지 등)은 리뷰 대상에서 제외하고
  3. 이미 리뷰한 커밋이면 건너뛰고(중복 방지)
  4. 변경량이 너무 크면 생략하고
  5. Claude(학교 FactChat API, rag_engine의 OpenAICompatibleBackend 재사용)에게 리뷰를 요청해
  6. 그 결과를 GitLab API로 MR에 댓글로 등록한다.

필요한 환경변수:
  - GITLAB_API_TOKEN    : GitLab Project Access Token (scope: api)
  - GITLAB_BASE_URL     : 예) https://gapps.gnu.ac.kr/gitlab/api/v4
  - GITLAB_WEBHOOK_SECRET : Webhook 등록 시 설정한 Secret Token (api_server.py에서 검증)

Claude 호출은 이미 AI 질문하기(RAG) 기능에서 쓰던 GNU_RAG_API_KEY/BASE/MODEL을 그대로
재사용한다 — 별도 API 키를 새로 발급받을 필요가 없다.
"""
import json
import os
import sys
import threading
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 리뷰 대상에서 제외할 파일(코드가 아니거나 자동 생성되는 파일)
SKIP_EXTENSIONS = (
    ".json", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2",
    ".ttf", ".pdf", ".docx", ".pptx", ".jsonl", ".log",
)
SKIP_PATH_PREFIXES = ("data/", "docs_screenshots/", "node_modules/")

# 변경량이 이보다 크면(총 줄 수) Claude 호출을 생략하고 안내 댓글만 남긴다
MAX_DIFF_LINES = 500

# 프로젝트당·MR당 "마지막으로 리뷰한 커밋"을 기억해 같은 내용을 중복 리뷰하지 않는다.
# (서버 재시작하면 초기화됨 — 운영상 큰 문제는 아니라 단순하게 메모리로 처리)
_reviewed_sha = {}

SYSTEM_PROMPT = (
    "당신은 '경상국립대학교 규정 통합 검색 시스템' 프로젝트의 코드 리뷰어입니다. "
    "아래 Merge Request의 변경 내용(diff)을 검토하고, 버그·보안 문제·이 프로젝트의 "
    "기존 관례(주석은 WHY 위주로 간결하게, 불필요한 예외처리 지양 등)에 어긋나는 부분이 "
    "있으면 지적해주세요. 문제가 없으면 '특별한 문제를 발견하지 못했습니다'라고만 "
    "답하세요. 한국어로, 간결하게(핵심만) 답변하세요."
)


def _gitlab_request(method: str, path: str, token: str, base_url: str, data: dict = None):
    url = f"{base_url.rstrip('/')}{path}"
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "PRIVATE-TOKEN": token,
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode("utf-8"))


def _filter_changes(changes: list) -> list:
    """데이터·이미지 등 리뷰 의미가 없는 파일은 제외한다."""
    kept = []
    for c in changes:
        path = c.get("new_path") or c.get("old_path") or ""
        if path.lower().endswith(SKIP_EXTENSIONS):
            continue
        if any(path.startswith(p) for p in SKIP_PATH_PREFIXES):
            continue
        kept.append(c)
    return kept


def _build_diff_text(changes: list) -> str:
    parts = []
    for c in changes:
        path = c.get("new_path") or c.get("old_path") or "(알 수 없는 파일)"
        parts.append(f"### {path}\n{c.get('diff', '')}")
    return "\n\n".join(parts)


def review_merge_request(project_id: int, mr_iid: int, commit_sha: str):
    """백그라운드 스레드에서 실행되는 실제 리뷰 로직. 실패해도 메인 서버에 영향 없도록
    모든 예외를 여기서 잡아 로그만 남긴다(Webhook 응답과는 이미 분리된 이후라 여기서
    실패해도 GitLab 쪽에는 영향 없음)."""
    token = os.environ.get("GITLAB_API_TOKEN", "")
    base_url = os.environ.get("GITLAB_BASE_URL", "")
    if not token or not base_url:
        print("[gitlab_review_bot] GITLAB_API_TOKEN/GITLAB_BASE_URL 미설정 — 리뷰 생략")
        return

    key = (project_id, mr_iid)
    if _reviewed_sha.get(key) == commit_sha:
        print(f"[gitlab_review_bot] MR !{mr_iid}: 이미 리뷰한 커밋({commit_sha[:8]}), 생략")
        return

    try:
        mr = _gitlab_request(
            "GET", f"/projects/{project_id}/merge_requests/{mr_iid}/changes", token, base_url)
    except Exception as e:
        print(f"[gitlab_review_bot] diff 조회 실패: {e}")
        return

    changes = _filter_changes(mr.get("changes", []))
    if not changes:
        print(f"[gitlab_review_bot] MR !{mr_iid}: 리뷰 대상 파일 없음(데이터/이미지만 변경됨)")
        _reviewed_sha[key] = commit_sha
        return

    diff_text = _build_diff_text(changes)
    total_lines = diff_text.count("\n")
    if total_lines > MAX_DIFF_LINES:
        comment = (f"🤖 변경량이 많아({total_lines}줄) 자동 리뷰를 생략했습니다. "
                   f"직접 리뷰 부탁드립니다.")
    else:
        try:
            import rag_engine
            backend = rag_engine.OpenAICompatibleBackend()
            if not backend.is_available():
                print("[gitlab_review_bot] GNU_RAG_API_KEY 미설정 — 리뷰 생략")
                return
            review = backend.generate(SYSTEM_PROMPT, diff_text)
            comment = f"🤖 **Claude 자동 리뷰**\n\n{review}"
        except Exception as e:
            print(f"[gitlab_review_bot] Claude 호출 실패: {e}")
            return

    try:
        _gitlab_request(
            "POST", f"/projects/{project_id}/merge_requests/{mr_iid}/notes",
            token, base_url, data={"body": comment})
        _reviewed_sha[key] = commit_sha
        print(f"[gitlab_review_bot] MR !{mr_iid}: 리뷰 댓글 등록 완료")
    except Exception as e:
        print(f"[gitlab_review_bot] 댓글 등록 실패: {e}")


def handle_webhook_payload(payload: dict):
    """api_server.py가 Webhook 수신 직후 호출. 실제 처리는 백그라운드 스레드로 넘겨
    GitLab이 응답을 기다리다 타임아웃나지 않게 한다."""
    if payload.get("object_kind") != "merge_request":
        return
    attrs = payload.get("object_attributes", {})
    if attrs.get("action") not in ("open", "update"):
        return

    project_id = payload.get("project", {}).get("id")
    mr_iid = attrs.get("iid")
    commit_sha = (attrs.get("last_commit") or {}).get("id", "")
    if not project_id or not mr_iid:
        return

    threading.Thread(
        target=review_merge_request, args=(project_id, mr_iid, commit_sha), daemon=True,
    ).start()
