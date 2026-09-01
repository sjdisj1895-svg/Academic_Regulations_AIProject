# -*- coding: utf-8 -*-
"""
[T1 보조] 이미 저장된 텍스트 파일에서 law.go.kr 화면 잔여물(HTML 조각)을 제거합니다.
- 대상: data/university/**/*.txt
- 예: 조문목록 없음" src="/LSW/images/button/btn_dot.gif" /> 체크박스" value="..." />
      ');return false;" href="#AJAX">  등
사용법: python scripts/fix_texts.py
"""
import glob
import os
import re

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# 제거할 잔여물 패턴 (순서대로 적용)
JUNK_PATTERNS = [
    r'조문목록( 없음)?"\s*src="[^"]*"\s*/>',       # 이미지 태그 조각
    r'체크박스"\s*value="[^"]*"\s*/>',             # 체크박스 조각
    r"'\);return false;\"\s*href=\"#AJAX\">",      # onclick 조각
    r'\w*"\s*src="[^"]*"\s*/>',                    # 기타 이미지 조각
    r'\w*"\s*value="[^"]*"\s*/>',                  # 기타 입력 조각
]


def clean_file(path: str) -> bool:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    original = text
    for pat in JUNK_PATTERNS:
        text = re.sub(pat, " ", text)
    # 잔여물 제거 후 남는 공백 정리
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if text != original:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return True
    return False


def main():
    files = glob.glob(os.path.join(DATA_DIR, "university", "**", "*.txt"),
                      recursive=True)
    fixed = sum(1 for p in files if clean_file(p))
    print(f"[정리 완료] 전체 {len(files)}개 파일 중 {fixed}개에서 잔여물 제거")


if __name__ == "__main__":
    main()
