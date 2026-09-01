# -*- coding: utf-8 -*-
"""
MANUAL.md / README.md 내용을 바탕으로 프로젝트 소개 슬라이드(PPTX)를 생성하는 스크립트.
경상국립대학교(GNU) 브랜드 컬러(시그니처 블루/다크 네이비/그린)를 테마로 사용합니다.

실행:
    python scripts/generate_pptx.py
결과:
    프로젝트 폴더에 "AI_규정통합검색시스템_소개.pptx" 생성
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = os.path.join(BASE_DIR, "docs_screenshots")
OUT_PATH = os.path.join(BASE_DIR, "AI_규정통합검색시스템_소개.pptx")

# ---------------------------------------------------------------- GNU 브랜드 컬러
NAVY = RGBColor(0x09, 0x1F, 0x46)
NAVY_DARK = RGBColor(0x06, 0x15, 0x30)
BLUE = RGBColor(0x00, 0x9E, 0xDB)
BLUE_DARK = RGBColor(0x00, 0x71, 0xDB)
NAVY_ACCENT = RGBColor(0x22, 0x49, 0x9D)
GREEN = RGBColor(0x00, 0x9E, 0x5E)
BG_LIGHT = RGBColor(0xF2, 0xF6, 0xFB)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
TEXT_DARK = RGBColor(0x17, 0x23, 0x3B)
TEXT_SUB = RGBColor(0x5C, 0x6B, 0x82)
BORDER = RGBColor(0xE1, 0xE8, 0xF2)

FONT = "맑은 고딕"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


def add_slide():
    return prs.slides.add_slide(BLANK)


def add_bg(slide, color_start, color_end=None, angle=45):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    shp.line.fill.background()
    shp.shadow.inherit = False
    if color_end is not None:
        shp.fill.gradient()
        stops = shp.fill.gradient_stops
        stops[0].color.rgb = color_start
        stops[0].position = 0.0
        stops[1].color.rgb = color_end
        stops[1].position = 1.0
        try:
            shp.fill.gradient_angle = angle
        except Exception:
            pass
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = color_start
    return shp


def add_text(slide, left, top, width, height, text, size=18, color=TEXT_DARK,
             bold=False, align=PP_ALIGN.LEFT, font=FONT, anchor=None, line_spacing=1.15):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    if anchor is not None:
        tf.vertical_anchor = anchor
    lines = text.split("\n")
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.alignment = align
        p.line_spacing = line_spacing
        for r in p.runs:
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.color.rgb = color
            r.font.name = font
    return box


def add_bullets(slide, left, top, width, height, items, size=16, color=TEXT_DARK,
                 bullet_color=BLUE, font=FONT, gap_after=8, bold_first=False):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = "•  " + item
        p.line_spacing = 1.2
        p.space_after = Pt(gap_after)
        for r in p.runs:
            r.font.size = Pt(size)
            r.font.color.rgb = color
            r.font.name = font
    return box


def add_page_number(slide, num, total):
    add_text(slide, prs.slide_width - Inches(1.6), prs.slide_height - Inches(0.5),
              Inches(1.3), Inches(0.35), f"{num} / {total}", size=11, color=TEXT_SUB,
              align=PP_ALIGN.RIGHT)


def add_kicker_title(slide, kicker, title, kicker_color=BLUE, title_color=NAVY):
    add_text(slide, Inches(0.6), Inches(0.35), Inches(10), Inches(0.4), kicker,
              size=14, color=kicker_color, bold=True)
    add_text(slide, Inches(0.6), Inches(0.68), Inches(11.8), Inches(0.7), title,
              size=28, color=title_color, bold=True)
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(1.35), Inches(1.1), Pt(4))
    line.line.fill.background()
    line.fill.solid()
    line.fill.fore_color.rgb = BLUE
    line.shadow.inherit = False


def add_table(slide, left, top, width, height, headers, rows, col_widths=None,
              header_bg=NAVY, header_fg=WHITE, font_size=13):
    n_rows = len(rows) + 1
    n_cols = len(headers)
    gshape = slide.shapes.add_table(n_rows, n_cols, left, top, width, height)
    table = gshape.table
    if col_widths:
        total = sum(col_widths)
        for i, w in enumerate(col_widths):
            table.columns[i].width = Emu(int(width * (w / total)))
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        cell.text = h
        cell.fill.solid()
        cell.fill.fore_color.rgb = header_bg
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        for p in cell.text_frame.paragraphs:
            p.alignment = PP_ALIGN.CENTER
            for r in p.runs:
                r.font.bold = True
                r.font.size = Pt(font_size)
                r.font.color.rgb = header_fg
                r.font.name = FONT
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = table.cell(i + 1, j)
            cell.text = str(val)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if i % 2 == 0 else BG_LIGHT
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.LEFT if j > 0 else PP_ALIGN.CENTER
                for r in p.runs:
                    r.font.size = Pt(font_size)
                    r.font.color.rgb = TEXT_DARK
                    r.font.name = FONT
    return table


TOTAL_SLIDES = 16

# ============================================================ 1. 표지
s = add_slide()
add_bg(s, NAVY, BLUE, angle=45)
circle = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(9.6), Inches(-1.6), Inches(5.5), Inches(5.5))
circle.fill.solid(); circle.fill.fore_color.rgb = BLUE_DARK; circle.fill.transparency = 0
circle.line.fill.background(); circle.shadow.inherit = False
try:
    circle.fill.fore_color.brightness = 0
except Exception:
    pass
badge = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.6), Inches(2.1), Inches(1.4), Inches(0.5))
badge.fill.solid(); badge.fill.fore_color.rgb = WHITE; badge.fill.transparency = 0
badge.line.color.rgb = WHITE; badge.line.width = Pt(1); badge.shadow.inherit = False
badge.text_frame.text = "GNU"
badge.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
for r in badge.text_frame.paragraphs[0].runs:
    r.font.bold = True; r.font.size = Pt(16); r.font.color.rgb = NAVY; r.font.name = FONT
add_text(s, Inches(0.6), Inches(2.9), Inches(11), Inches(1.3),
         "AI 기반 대학·산학협력단\n규정집 통합 검색 시스템", size=40, color=WHITE, bold=True)
add_text(s, Inches(0.6), Inches(4.5), Inches(11), Inches(0.6),
         "벡터DB 청킹 기반 AI 검색엔진으로 규정 검색의 정확도와 접근성을 향상시키다",
         size=18, color=WHITE)
add_text(s, Inches(0.6), Inches(6.6), Inches(11), Inches(0.5),
         "경상국립대학교 정보전산처  ·  총무과 / 산학협력단 산학연구과",
         size=13, color=RGBColor(0xDD, 0xEE, 0xFB))

# ============================================================ 2. 추진배경 및 필요성
s = add_slide()
add_bg(s, BG_LIGHT)
add_kicker_title(s, "PROBLEM", "추진배경 및 필요성")
items = [
    "현재 규정집 조회 시스템은 '규정명' 단순 검색만 제공 → 조·항 단위 세부 내용 검색이 어려움",
    "대학 규정과 산학협력단 규정이 서로 다른 웹사이트로 이원화 운영 → 검색·조회의 일관성 결여",
    "키워드 중심의 통합 검색 및 AI 기능이 반영된 규정집 조회 기능 개선 필요",
]
add_bullets(s, Inches(0.7), Inches(1.7), Inches(11.9), Inches(2.2), items, size=18)
card = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.7), Inches(4.1), Inches(11.9), Inches(2.5))
card.fill.solid(); card.fill.fore_color.rgb = WHITE; card.line.color.rgb = BORDER; card.shadow.inherit = False
add_text(s, Inches(1.0), Inches(4.3), Inches(6), Inches(0.4), "관련 부서", size=15, color=NAVY, bold=True)
add_bullets(s, Inches(1.0), Inches(4.75), Inches(5.8), Inches(1.6),
            ["(대학) 총무과", "(산학협력단) 산학연구과"], size=15)
add_text(s, Inches(7.0), Inches(4.3), Inches(5.3), Inches(0.4), "벤치마킹 대학", size=15, color=NAVY, bold=True)
add_bullets(s, Inches(7.0), Inches(4.75), Inches(5.3), Inches(1.6),
            ["규정 카테고리 구분 : 충남대학교", "조회 형식 등 : 연세대학교(rules.yonsei.ac.kr)"], size=15)
add_page_number(s, 2, TOTAL_SLIDES)

# ============================================================ 3. 프로젝트 목적 / 대상 사용자
s = add_slide()
add_bg(s, BG_LIGHT)
add_kicker_title(s, "PURPOSE", "프로젝트 목적 & 대상 사용자")
add_text(s, Inches(0.7), Inches(1.65), Inches(6), Inches(0.4), "🎯 프로젝트 목적", size=17, color=NAVY, bold=True)
add_bullets(s, Inches(0.7), Inches(2.1), Inches(6.0), Inches(3.5), [
    "대학 + 산학협력단 규정 통합 검색 환경 구축",
    "규정명뿐 아니라 조·항 단위 본문 내용까지 검색",
    "벡터DB 기반 청킹으로 시맨틱 검색 정확도 향상",
    "규정 + 담당부서(연락처) 원스톱 확인 제공",
], size=15)
add_text(s, Inches(6.9), Inches(1.65), Inches(5.6), Inches(0.4), "👥 대상 사용자", size=17, color=NAVY, bold=True)
add_bullets(s, Inches(6.9), Inches(2.1), Inches(5.6), Inches(3.5), [
    "1차 : 학내 구성원 (학생 · 교원 · 직원)",
    "2차 : 규정 관리 담당자 (총무과, 산학연구과)",
    "운영자 : 시스템 관리자 (데이터 등록·갱신)",
], size=15)
add_page_number(s, 3, TOTAL_SLIDES)

# ============================================================ 4. 주요 요구사항
s = add_slide()
add_bg(s, BG_LIGHT)
add_kicker_title(s, "REQUIREMENTS", "주요 요구사항 (검색 결과 표시 예시: PRD 4.1)")
headers = ["구분", "요구 항목"]
rows = [
    ["FR-01", "통합 검색 : 대학 + 산학협력단 규정을 하나의 검색창에서 검색 (제목+본문)"],
    ["FR-02", "하이브리드 검색 : 키워드 검색 + AI 의미(시맨틱) 검색 결합"],
    ["FR-03", "결과 표시 : 규정 구분·연관 규정명(전체)·조항(제0조 제0항)·담당부서/연락처"],
    ["FR-04", "'관련 사이트로 이동' 버튼 : 원본 규정 페이지로 새 창 이동"],
    ["FR-05", "'미리보기' 기능 : 조항/규정 전문을 팝업으로 확인"],
    ["FR-06", "카테고리(학칙/규정/지침)·출처(대학/산학협력단) 필터"],
    ["NFR-01", "검색 응답 속도 3초 이내"],
]
add_table(s, Inches(0.7), Inches(1.6), Inches(11.9), Inches(3.3), headers, rows,
          col_widths=[1.3, 10.6], font_size=13)
example = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.7), Inches(5.15), Inches(11.9), Inches(1.55))
example.fill.solid(); example.fill.fore_color.rgb = NAVY; example.line.fill.background(); example.shadow.inherit = False
add_text(s, Inches(1.0), Inches(5.25), Inches(11.3), Inches(0.35), "예) '연구비' 검색 결과 표시 예시", size=13, color=BLUE, bold=True)
add_text(s, Inches(1.0), Inches(5.6), Inches(11.3), Inches(1.0),
         "교무행정, 규정명, '제0조 제0항' 본문 내용 / 담당부서 : 총무과(T.0331)\n"
         "학생행정, 규정명, '제0조 제0항' 본문 내용 / 담당부서 : 산학협력지원실(T.0000)\n"
         "일반행정, 규정명, '제0조 제0항' 본문 내용 / 담당부서 : 산학협력단 산학연구과(T.0000)",
         size=13, color=WHITE, line_spacing=1.3)
add_page_number(s, 4, TOTAL_SLIDES)

# ============================================================ 5. MVP 범위
s = add_slide()
add_bg(s, BG_LIGHT)
add_kicker_title(s, "SCOPE", "MVP 범위")
in_box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.7), Inches(1.6), Inches(5.8), Inches(4.9))
in_box.fill.solid(); in_box.fill.fore_color.rgb = WHITE; in_box.line.color.rgb = GREEN; in_box.line.width = Pt(1.5)
in_box.shadow.inherit = False
add_text(s, Inches(1.0), Inches(1.8), Inches(5.2), Inches(0.4), "✅ In Scope (포함)", size=17, color=GREEN, bold=True)
add_bullets(s, Inches(1.0), Inches(2.3), Inches(5.2), Inches(4.0), [
    "규정 원문 수집 (대학+산학협력단)",
    "조·항 단위 청킹 + 벡터DB 구축",
    "하이브리드 통합 검색 API",
    "검색 결과 상세 카드(구분/규정명/조항/담당부서)",
    "미리보기, 관련 사이트 이동",
    "카테고리·출처 필터",
], size=14)
out_box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.8), Inches(1.6), Inches(5.8), Inches(4.9))
out_box.fill.solid(); out_box.fill.fore_color.rgb = WHITE; out_box.line.color.rgb = TEXT_SUB; out_box.line.width = Pt(1.5)
out_box.shadow.inherit = False
add_text(s, Inches(7.1), Inches(1.8), Inches(5.2), Inches(0.4), "⏭ Out of Scope (향후 확장)", size=17, color=TEXT_SUB, bold=True)
add_bullets(s, Inches(7.1), Inches(2.3), Inches(5.2), Inches(4.0), [
    "챗봇형 Q&A (RAG 답변 생성)",
    "규정 개정 이력 관리",
    "규정 관리자용 어드민(admin) 시스템",
    "다국어 지원",
], size=14, bullet_color=TEXT_SUB)
add_page_number(s, 5, TOTAL_SLIDES)

# ============================================================ 6. 전체 아키텍처
s = add_slide()
add_bg(s, BG_LIGHT)
add_kicker_title(s, "ARCHITECTURE", "시스템 아키텍처 (T1 → T5 파이프라인)")
steps = [
    ("T1", "데이터 수집", "대학·산학협력단\n규정 원문 수집", NAVY),
    ("T2", "청킹·임베딩", "조·항 단위 분할 +\nKR-SBERT 임베딩\n→ ChromaDB", BLUE_DARK),
    ("T3", "검색 API", "FastAPI\n하이브리드 검색\n(벡터+BM25)", BLUE),
    ("T4", "웹 화면", "검색·필터·\n미리보기 UI", NAVY_ACCENT),
    ("T5", "품질·운영", "자동 평가 +\n원클릭 갱신", GREEN),
]
x = Inches(0.55)
w = Inches(2.28)
gap = Inches(0.18)
for i, (tag, title, desc, color) in enumerate(steps):
    box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, Inches(2.3), w, Inches(2.6))
    box.fill.solid(); box.fill.fore_color.rgb = color; box.line.fill.background(); box.shadow.inherit = False
    tf = box.text_frame; tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.margin_top = Pt(14)
    p0 = tf.paragraphs[0]; p0.text = tag; p0.alignment = PP_ALIGN.CENTER
    for r in p0.runs: r.font.size = Pt(15); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = FONT
    p1 = tf.add_paragraph(); p1.text = title; p1.alignment = PP_ALIGN.CENTER; p1.space_before = Pt(6)
    for r in p1.runs: r.font.size = Pt(15); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = FONT
    p2 = tf.add_paragraph(); p2.text = desc; p2.alignment = PP_ALIGN.CENTER; p2.space_before = Pt(10)
    for r in p2.runs: r.font.size = Pt(11); r.font.color.rgb = RGBColor(0xE9,0xF3,0xFB); r.font.name = FONT
    if i < len(steps) - 1:
        arrow = s.shapes.add_shape(MSO_SHAPE.CHEVRON, x + w + Emu(15000), Inches(3.35), Inches(0.32), Inches(0.5))
        arrow.fill.solid(); arrow.fill.fore_color.rgb = TEXT_SUB; arrow.line.fill.background(); arrow.shadow.inherit = False
    x = x + w + gap
add_text(s, Inches(0.7), Inches(5.35), Inches(11.9), Inches(1.4),
         "대학 규정 사이트 + 산학협력단 게시판 → 텍스트 정리 → 조·항 청킹 → 한국어 AI 임베딩 → 벡터DB 저장\n"
         "→ 사용자가 검색어 입력 → 하이브리드 검색 서버가 관련 조항 반환 → 웹 화면에 결과·미리보기 표시",
         size=14, color=TEXT_SUB, align=PP_ALIGN.CENTER)
add_page_number(s, 6, TOTAL_SLIDES)

# ============================================================ 7. 기술 스택 (1/2)
s = add_slide()
add_bg(s, BG_LIGHT)
add_kicker_title(s, "TECH STACK", "기술 스택 ① — 데이터 수집 · 청킹 · 임베딩")
headers = ["구분", "기술", "선택 이유"]
rows = [
    ["공통", "Python 3.13 (Windows)", "AI/데이터 생태계 풍부, 전 단계를 한 언어로 통일"],
    ["T1 수집", "표준 라이브러리 (urllib·re·zipfile)", "외부 설치 없이 즉시 실행 가능"],
    ["T1 수집", "law.go.kr 연동 / HWPX 직접 파싱", "유료 변환 도구 없이 깨끗한 조문 텍스트 확보"],
    ["T2 청킹", "정규식 기반 조문 청킹(자체 개발)", "제0조·①②③ 패턴이 일정해 정확히 분할 가능"],
    ["T2 임베딩", "KR-SBERT (서울대 한국어 특화 모델)", "한국어 의미 유사도(STS)에 특화, 무료·오프라인 실행"],
    ["T2 벡터DB", "ChromaDB (임베디드 방식)", "서버 설치 없이 폴더에 저장, 메타데이터 필터 지원"],
]
add_table(s, Inches(0.7), Inches(1.6), Inches(11.9), Inches(4.6), headers, rows,
          col_widths=[1.3, 3.6, 7.0], font_size=13)
add_page_number(s, 7, TOTAL_SLIDES)

# ============================================================ 8. 기술 스택 (2/2)
s = add_slide()
add_bg(s, BG_LIGHT)
add_kicker_title(s, "TECH STACK", "기술 스택 ② — 검색 API · 웹 화면 · 운영")
rows2 = [
    ["T3 검색 API", "FastAPI + Uvicorn", "경량 웹 프레임워크, 자동 API 문서(Swagger) 제공"],
    ["T3 검색 방식", "하이브리드 검색 (BM25 자체구현 + 벡터 유사도)", "키워드 검색 + 의미 검색 결합으로 정확도 향상"],
    ["T4 웹 화면", "순수 HTML / CSS / JS (반응형)", "빌드 도구 없이 FastAPI가 바로 서빙, 유지보수 최소화"],
    ["T5 품질검증", "자체 평가 스크립트 (evaluate_search.py)", "PRD 성공 지표를 자동 회귀 테스트로 측정"],
    ["T5 운영", "원클릭 갱신 스크립트 (refresh_all.py)", "규정 개정 시 수집~벡터DB까지 한 번에 재생성"],
]
add_table(s, Inches(0.7), Inches(1.6), Inches(11.9), Inches(3.9), headers, rows2,
          col_widths=[1.5, 4.0, 6.4], font_size=13)
add_page_number(s, 8, TOTAL_SLIDES)

# ============================================================ 9. 화면 미리보기 - 메인/검색결과
s = add_slide()
add_bg(s, BG_LIGHT)
add_kicker_title(s, "SCREEN", "실제 화면 — 통합 검색 결과 (경상국립대 GNU 브랜드 컬러 적용)")
img1 = os.path.join(SHOT_DIR, "design_results_crop.png")
if not os.path.exists(img1):
    img1 = os.path.join(SHOT_DIR, "design_results.png")
if os.path.exists(img1):
    s.shapes.add_picture(img1, Inches(4.15), Inches(1.55), height=Inches(5.6))
add_text(s, Inches(0.6), Inches(2.0), Inches(3.4), Inches(1.2),
          "GNU 시그니처 블루 헤더\n배지(대학=네이비 / 산학협력단=그린)\n검색어 하이라이트(형광펜)",
          size=13, color=TEXT_SUB, line_spacing=1.4)
add_page_number(s, 9, TOTAL_SLIDES)

# ============================================================ 10. 화면 미리보기 - 모달/모바일
s = add_slide()
add_bg(s, BG_LIGHT)
add_kicker_title(s, "SCREEN", "실제 화면 — 미리보기 팝업 & 모바일 반응형")
img2 = os.path.join(SHOT_DIR, "design_modal.png")
img3 = os.path.join(SHOT_DIR, "design_mobile_crop.png")
if not os.path.exists(img3):
    img3 = os.path.join(SHOT_DIR, "design_mobile.png")
if os.path.exists(img2):
    s.shapes.add_picture(img2, Inches(0.9), Inches(2.0), width=Inches(6.2))
if os.path.exists(img3):
    s.shapes.add_picture(img3, Inches(9.0), Inches(1.6), height=Inches(4.9))
add_text(s, Inches(0.9), Inches(6.6), Inches(6.2), Inches(0.4), "① 미리보기 모달 (조항 / 규정 전문 탭)", size=13, color=NAVY, bold=True, align=PP_ALIGN.CENTER)
add_text(s, Inches(9.0), Inches(6.6), Inches(3.4), Inches(0.4), "② 모바일(375px) 반응형", size=13, color=NAVY, bold=True, align=PP_ALIGN.CENTER)
add_page_number(s, 10, TOTAL_SLIDES)

# ============================================================ 11. T1~T2 결과
s = add_slide()
add_bg(s, BG_LIGHT)
add_kicker_title(s, "RESULT", "구현 결과 ① — 데이터 수집 & 청킹/벡터DB")
headers = ["단계", "핵심 결과"]
rows = [
    ["T1 수집", "총 426건 수집 (대학 학칙 1 · 규정 228 · 지침 134, 산학협력단 63) · 실패 0건"],
    ["T2 청킹", "8,831개 조·항 단위 청크 생성 (규정 426건 전체 성공, 청킹 실패 0건)"],
    ["T2 임베딩", "KR-SBERT로 전량 임베딩 → ChromaDB 적재 완료"],
    ["테스트 검색", "\"연구비\" 검색 시 관련 조항 정상 반환 / 자연어 질의도 의미 기반으로 매칭"],
]
add_table(s, Inches(0.7), Inches(1.7), Inches(11.9), Inches(3.4), headers, rows,
          col_widths=[1.6, 10.3], font_size=14)
add_page_number(s, 11, TOTAL_SLIDES)

# ============================================================ 12. T3~T4 결과
s = add_slide()
add_bg(s, BG_LIGHT)
add_kicker_title(s, "RESULT", "구현 결과 ② — 검색 API & 웹 화면")
rows = [
    ["T3 API", "하이브리드 검색(의미 60%+키워드 40%) · 필터 · 미리보기 API 구현, 응답 0.05~0.12초"],
    ["T3 검증", "\"연구비\" 검색 결과가 PRD 예시 형식(구분/규정명/조항/담당부서)과 일치 확인"],
    ["T4 화면", "검색창·필터·결과카드·하이라이트·미리보기모달·사이트이동·반응형 전부 구현"],
    ["T4 검증", "Playwright로 실제 브라우저 렌더링 캡처 → 하이라이트 39개, 필터·모달 정상 확인"],
]
add_table(s, Inches(0.7), Inches(1.7), Inches(11.9), Inches(3.4), headers, rows,
          col_widths=[1.6, 10.3], font_size=14)
add_page_number(s, 12, TOTAL_SLIDES)

# ============================================================ 13. T5 품질 검증 결과
s = add_slide()
add_bg(s, BG_LIGHT)
add_kicker_title(s, "RESULT", "구현 결과 ③ — 검색 품질 검증 (PRD 6.2 성공 지표)")
headers = ["평가 항목", "결과", "PRD 6.2 목표"]
rows = [
    ["검색 성공률 (주요 키워드 15개, 상위5건 내 노출)", "15 / 15  (100%)", "상위 5건 내 노출  ✅"],
    ["평균 응답 시간", "0.054초", "평균 3초 이내  ✅"],
    ["최대 응답 시간", "0.096초", "-"],
    ["검색 튜닝", "BM25 한글 1글자 토큰 노이즈 발견·수정", "-"],
    ["원클릭 데이터 갱신", "refresh_all.py 검증 완료 (부분갱신 37.6초)", "DR-05  ✅"],
    ["담당부서·연락처 검수 자료", "140개 조합 CSV/Markdown 추출 완료", "-"],
]
add_table(s, Inches(0.7), Inches(1.65), Inches(11.9), Inches(4.6), headers, rows,
          col_widths=[4.2, 3.6, 3.0], font_size=13)
add_page_number(s, 13, TOTAL_SLIDES)

# ============================================================ 14. 운영 매뉴얼 요약 (MANUAL.md)
s = add_slide()
add_bg(s, BG_LIGHT)
add_kicker_title(s, "OPERATION", "운영 매뉴얼 요약 (MANUAL.md)")
steps = [
    ("1", "최초 설치", "pip install sentence-transformers chromadb fastapi uvicorn (한 번만)"),
    ("2", "평상시 실행", "python -m uvicorn scripts.api_server:app --port 8000 → 브라우저 접속"),
    ("3", "규정 개정 시 갱신", "python scripts/refresh_all.py (전체) 또는 --skip-collect --name (부분, 1분 이내)"),
    ("4", "검색 품질 점검", "python scripts/evaluate_search.py → 성공률·응답시간 자동 리포트"),
    ("5", "담당부서 연락처 검수", "python scripts/export_contacts.py → CSV/MD로 총무과·산학연구과 회신 요청"),
]
y = Inches(1.65)
for num, title, desc in steps:
    circ = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.7), y, Inches(0.5), Inches(0.5))
    circ.fill.solid(); circ.fill.fore_color.rgb = BLUE; circ.line.fill.background(); circ.shadow.inherit = False
    circ.text_frame.text = num
    circ.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    for r in circ.text_frame.paragraphs[0].runs:
        r.font.bold = True; r.font.size = Pt(16); r.font.color.rgb = WHITE; r.font.name = FONT
    add_text(s, Inches(1.4), y - Inches(0.03), Inches(3.0), Inches(0.5), title, size=15, color=NAVY, bold=True)
    add_text(s, Inches(4.3), y - Inches(0.03), Inches(8.2), Inches(0.6), desc, size=13, color=TEXT_DARK)
    y += Inches(0.95)
add_page_number(s, 14, TOTAL_SLIDES)

# ============================================================ 15. 기대효과
s = add_slide()
add_bg(s, BG_LIGHT)
add_kicker_title(s, "EFFECT", "기대효과")
box1 = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.7), Inches(1.8), Inches(5.8), Inches(4.4))
box1.fill.solid(); box1.fill.fore_color.rgb = NAVY; box1.line.fill.background(); box1.shadow.inherit = False
add_text(s, Inches(1.0), Inches(2.0), Inches(5.2), Inches(0.4), "행정 서비스 개선", size=17, color=WHITE, bold=True)
add_bullets(s, Inches(1.0), Inches(2.5), Inches(5.2), Inches(3.5), [
    "대학·산학협력단 규정 통합 검색 환경 구축",
    "규정 + 담당부서를 원스톱으로 확인",
    "규정 개정 시 원클릭 데이터 갱신",
], size=14, color=WHITE, bullet_color=BLUE)
box2 = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.8), Inches(1.8), Inches(5.8), Inches(4.4))
box2.fill.solid(); box2.fill.fore_color.rgb = GREEN; box2.line.fill.background(); box2.shadow.inherit = False
add_text(s, Inches(7.1), Inches(2.0), Inches(5.2), Inches(0.4), "학내 구성원 편의 향상", size=17, color=WHITE, bold=True)
add_bullets(s, Inches(7.1), Inches(2.5), Inches(5.2), Inches(3.5), [
    "복잡한 규정 체계에서 필요한 정보를 신속·정확하게 습득",
    "키워드뿐 아니라 자연어 질문으로도 검색 가능",
    "검색 성공률 100%, 평균 응답 0.05초의 빠른 검색 경험",
], size=14, color=WHITE, bullet_color=NAVY)
add_page_number(s, 15, TOTAL_SLIDES)

# ============================================================ 16. 마무리
s = add_slide()
add_bg(s, NAVY, BLUE, angle=45)
add_text(s, Inches(0.8), Inches(2.6), Inches(11.7), Inches(1.0),
          "감사합니다", size=44, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
add_text(s, Inches(0.8), Inches(3.7), Inches(11.7), Inches(0.6),
          "AI 기반 대학·산학협력단 규정집 통합 검색 시스템", size=18, color=WHITE, align=PP_ALIGN.CENTER)
add_text(s, Inches(0.8), Inches(4.5), Inches(11.7), Inches(0.5),
          "문의 : 정보전산처(시스템 운영) · 총무과 055-772-0334(대학 규정) · 산학연구과 055-772-0211(산학협력단 규정)",
          size=13, color=RGBColor(0xDD, 0xEE, 0xFB), align=PP_ALIGN.CENTER)
add_text(s, Inches(0.8), Inches(6.6), Inches(11.7), Inches(0.4),
          "참고 문서 : PRD.md · TASKS.md · README.md · MANUAL.md",
          size=12, color=RGBColor(0xC8, 0xDE, 0xF2), align=PP_ALIGN.CENTER)

prs.save(OUT_PATH)
print("saved final:", OUT_PATH)
print("slide count:", len(prs.slides.__iter__.__self__._sldIdLst))
