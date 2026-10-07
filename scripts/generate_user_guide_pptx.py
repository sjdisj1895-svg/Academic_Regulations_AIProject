# -*- coding: utf-8 -*-
"""
비개발자(전 부서 공문 배포용) 사용자 안내 슬라이드(PPTX) 생성 스크립트.
AI 질문하기 기능은 아직 비공개라 제외하고, 검색 기능 사용법 위주로 구성한다.
경상국립대학교 공식 VI 전용색상(BS13)을 사용한다.

실행 전: C:/tmp/manual_home.png, manual_results.png, manual_preview.png 스크린샷 필요
실행: python scripts/generate_user_guide_pptx.py
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET_DIR = os.path.join(BASE_DIR, "web", "assets")
OUT_PATH = os.path.join(BASE_DIR, "경상국립대학교_규정통합검색_사용자안내.pptx")

SCREEN_HOME = "C:/tmp/manual_home.png"
SCREEN_RESULTS = "C:/tmp/manual_results.png"
SCREEN_PREVIEW = "C:/tmp/manual_preview.png"

# ---------------------------------------------------------------- GNU 공식 VI 색상 (BS13)
BLUE = RGBColor(0x00, 0x9E, 0xDB)
BLUE_DEEP = RGBColor(0x00, 0x7F, 0xB3)
GREY = RGBColor(0x43, 0x52, 0x5A)
GREY_DEEP = RGBColor(0x2F, 0x3A, 0x41)
GOLD = RGBColor(0xB3, 0xA1, 0x77)
BG_LIGHT = RGBColor(0xF3, 0xF6, 0xF8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
TEXT_DARK = RGBColor(0x2B, 0x35, 0x3B)
TEXT_SUB = RGBColor(0x66, 0x73, 0x7A)
BORDER = RGBColor(0xE3, 0xE8, 0xEB)

FONT = "맑은 고딕"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
TOTAL_SLIDES = 8


def add_slide():
    return prs.slides.add_slide(BLANK)


def add_bg(slide, color):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    shp.line.fill.background()
    shp.shadow.inherit = False
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    return shp


def add_text(slide, left, top, width, height, text, size=18, color=TEXT_DARK,
             bold=False, align=PP_ALIGN.LEFT, anchor=None, line_spacing=1.15):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    if anchor is not None:
        tf.vertical_anchor = anchor
    for i, line in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.alignment = align
        p.line_spacing = line_spacing
        for r in p.runs:
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.color.rgb = color
            r.font.name = FONT
    return box


def add_bullets(slide, left, top, width, height, items, size=16, color=TEXT_DARK, gap_after=10):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = "•  " + item
        p.line_spacing = 1.25
        p.space_after = Pt(gap_after)
        for r in p.runs:
            r.font.size = Pt(size)
            r.font.color.rgb = color
            r.font.name = FONT
    return box


def add_page_number(slide):
    n = len(prs.slides._sldIdLst)
    add_text(slide, prs.slide_width - Inches(1.6), prs.slide_height - Inches(0.5),
              Inches(1.3), Inches(0.35), f"{n} / {TOTAL_SLIDES}", size=11, color=TEXT_SUB,
              align=PP_ALIGN.RIGHT)


def add_kicker_title(slide, kicker, title):
    add_text(slide, Inches(0.6), Inches(0.35), Inches(10), Inches(0.4), kicker,
              size=14, color=BLUE, bold=True)
    add_text(slide, Inches(0.6), Inches(0.68), Inches(11.8), Inches(0.7), title,
              size=28, color=GREY, bold=True)
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(1.35), Inches(1.1), Pt(4))
    line.line.fill.background(); line.fill.solid(); line.fill.fore_color.rgb = BLUE; line.shadow.inherit = False
    sig = os.path.join(ASSET_DIR, "gnu_emblem_combo_kr_en.png")
    if os.path.exists(sig):
        slide.shapes.add_picture(sig, prs.slide_width - Inches(3.1), Inches(0.42), height=Inches(0.36))
    add_page_number(slide)


def add_card(slide, left, top, width, height, fill=WHITE, line=BORDER):
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    card.fill.solid(); card.fill.fore_color.rgb = fill
    if line is None:
        card.line.fill.background()
    else:
        card.line.color.rgb = line
    card.shadow.inherit = False
    return card


def add_screenshot(slide, path, caption, left=Inches(0.6), top=Inches(1.7),
                    height=Inches(5.0)):
    if os.path.exists(path):
        pic = slide.shapes.add_picture(path, left, top, height=height)
        # 테두리
        card = add_card(slide, left - Emu(20000), top - Emu(20000),
                         pic.width + Emu(40000), pic.height + Emu(40000), fill=WHITE, line=BORDER)
        slide.shapes._spTree.remove(card._element)
        slide.shapes._spTree.insert(list(slide.shapes._spTree).index(pic._element), card._element)
    else:
        add_text(slide, left, top, Inches(8), Inches(1), f"[스크린샷 없음: {path}]", color=TEXT_SUB)
    add_text(slide, left, top + height + Inches(0.15), Inches(8), Inches(0.4), caption,
              size=13, color=TEXT_SUB)


def add_table(slide, left, top, width, height, headers, rows, col_widths=None,
              header_bg=BLUE, header_fg=WHITE, font_size=14):
    gshape = slide.shapes.add_table(len(rows) + 1, len(headers), left, top, width, height)
    table = gshape.table
    if col_widths:
        total = sum(col_widths)
        for i, w in enumerate(col_widths):
            table.columns[i].width = Emu(int(width * (w / total)))
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        cell.text = h
        cell.fill.solid(); cell.fill.fore_color.rgb = header_bg
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        for p in cell.text_frame.paragraphs:
            p.alignment = PP_ALIGN.CENTER
            for r in p.runs:
                r.font.bold = True; r.font.size = Pt(font_size); r.font.color.rgb = header_fg; r.font.name = FONT
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = table.cell(i + 1, j)
            cell.text = str(val)
            cell.fill.solid(); cell.fill.fore_color.rgb = WHITE if i % 2 == 0 else BG_LIGHT
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.LEFT if j > 0 else PP_ALIGN.CENTER
                for r in p.runs:
                    r.font.size = Pt(font_size); r.font.color.rgb = TEXT_DARK; r.font.name = FONT
    return table


# ===================================================================== 1. 표지
s = add_slide()
add_bg(s, GREY_DEEP)
logo = os.path.join(ASSET_DIR, "gnu_emblem_b.png")
if os.path.exists(logo):
    s.shapes.add_picture(logo, Inches(5.92), Inches(1.0), height=Inches(1.6))
add_text(s, Inches(1), Inches(3.0), Inches(11.33), Inches(1.0),
          "경상국립대학교 규정 통합 검색 서비스", size=34, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
add_text(s, Inches(1), Inches(3.85), Inches(11.33), Inches(0.7),
          "이용 안내", size=22, color=RGBColor(0xBC, 0xD9, 0xEA), bold=True, align=PP_ALIGN.CENTER)
add_text(s, Inches(1), Inches(4.6), Inches(11.33), Inches(0.5),
          "대학·산학협력단 규정을 한 번에 검색하세요", size=15, color=RGBColor(0xBC, 0xBE, 0xC0),
          align=PP_ALIGN.CENTER)
add_text(s, Inches(1), Inches(6.6), Inches(11.33), Inches(0.4),
          "경상국립대학교 정보전산처", size=12, color=RGBColor(0x8A, 0x97, 0x9E), align=PP_ALIGN.CENTER)

# ===================================================================== 2. 서비스 소개
s = add_slide()
add_kicker_title(s, "SERVICE", "서비스 소개")
add_text(s, Inches(0.6), Inches(1.7), Inches(11.8), Inches(0.9),
          "대학 규정(학칙·규정·지침)과 산학협력단 규정을 조(條)·항(項) 단위로\n"
          "한 번에 검색할 수 있는 통합 검색 서비스입니다.", size=19, color=TEXT_DARK)
cards = [
    ("430건+", "등록된 규정"),
    ("9,390개+", "검색 가능한 조항"),
    ("3단계", "검색창 입력 → 결과 확인, 끝"),
]
cw = Inches(3.6)
gap = Inches(0.35)
startx = (prs.slide_width - (cw * 3 + gap * 2)) / 2
for i, (num, label) in enumerate(cards):
    x = startx + i * (cw + gap)
    add_card(s, x, Inches(3.3), cw, Inches(2.0), fill=BG_LIGHT, line=BORDER)
    add_text(s, x, Inches(3.6), cw, Inches(0.8), num, size=30, bold=True, color=BLUE, align=PP_ALIGN.CENTER)
    add_text(s, x, Inches(4.4), cw, Inches(0.6), label, size=14, color=GREY, align=PP_ALIGN.CENTER)
add_bullets(s, Inches(0.6), Inches(5.7), Inches(11.8), Inches(1.3), [
    "여러 게시판·문서에 흩어져 있던 규정을 일일이 찾던 번거로움을 줄입니다.",
    "검색 결과에서 담당부서·연락처까지 바로 확인할 수 있습니다.",
])

# ===================================================================== 3. 접속 방법
s = add_slide()
add_kicker_title(s, "ACCESS", "접속 방법")
add_table(
    s, Inches(0.6), Inches(1.9), Inches(11.8), Inches(2.4),
    ["항목", "내용"],
    [
        ["접속 주소", "https://regulations.gnu.ac.kr"],
        ["로그인", "별도 로그인·회원가입 없이 바로 이용 가능"],
        ["이용 환경", "PC·태블릿·휴대폰 어디서나 접속 (별도 앱 설치 불필요)"],
    ],
    col_widths=[3, 9], font_size=16,
)
add_text(s, Inches(0.6), Inches(4.8), Inches(11.8), Inches(0.6),
          "💡 주소를 즐겨찾기(북마크)에 추가해두면 다음부터 더 빠르게 접속할 수 있습니다.",
          size=14, color=TEXT_SUB)

# ===================================================================== 4. 검색 ① 키워드
s = add_slide()
add_kicker_title(s, "HOW TO SEARCH · STEP 1", "검색창에 키워드 입력")
add_screenshot(s, SCREEN_HOME, "메인 화면 — 검색창에 찾고 싶은 규정명이나 단어를 입력하고 검색")
add_bullets(s, Inches(8.8), Inches(1.9), Inches(4.1), Inches(4.5), [
    "규정명 일부만 적어도 검색됩니다.",
    "조항 본문에 있는 단어로도 검색됩니다.",
    "예시 검색어 버튼을 눌러 바로 체험해볼 수 있습니다.",
], size=15)

# ===================================================================== 5. 검색 ② 필터
s = add_slide()
add_kicker_title(s, "HOW TO SEARCH · STEP 2", "필터로 범위 좁히기")
add_screenshot(s, SCREEN_RESULTS, "검색 결과 화면 — 출처·분류 필터로 원하는 범위만 골라볼 수 있음")
add_bullets(s, Inches(8.8), Inches(1.9), Inches(4.1), Inches(4.5), [
    "전체·대학·산학협력단 중 선택",
    "분류 칩(학칙·규정·지침 등) 클릭",
    "'필터 더보기'에서 폐지 규정 포함,\n최근 개정만 보기 등 설정 가능",
], size=15)

# ===================================================================== 6. 검색 ③ 미리보기
s = add_slide()
add_kicker_title(s, "HOW TO SEARCH · STEP 3", "조항 미리보기 · 담당부서 확인")
add_screenshot(s, SCREEN_PREVIEW, "조항 클릭 시 뜨는 미리보기 — 담당부서·전화번호가 바로 보임")
add_bullets(s, Inches(8.8), Inches(1.9), Inches(4.1), Inches(4.5), [
    "담당부서 전화번호 클릭 시\n바로 전화 연결",
    "'규정 전문' 탭에서 전체 조문 확인",
    "'관련 사이트로 이동'으로\n원본 게시글 확인",
], size=15)

# ===================================================================== 7. FAQ
s = add_slide()
add_kicker_title(s, "FAQ", "자주 묻는 질문")
faqs = [
    ("검색을 했는데 결과가 안 나와요.",
     "검색어 철자를 확인하고, 적용된 필터를 '모두 해제'한 뒤 다시 검색해보세요. "
     "긴 문장보다 핵심 단어 위주로 검색하면 더 잘 찾아집니다."),
    ("우리 부서 이전 규정이 안 보여요.",
     "기본값은 '현재 시행 중인 규정'만 보여줍니다. 폐지·개정 전 규정은 "
     "'필터 더보기 → 폐지된 규정도 포함'을 체크하세요."),
    ("모바일에서도 똑같이 쓸 수 있나요?",
     "네, 화면이 자동으로 맞춰지며 기능은 PC와 동일합니다."),
]
y = Inches(1.8)
for q, a in faqs:
    add_card(s, Inches(0.6), y, Inches(12.1), Inches(1.5), fill=BG_LIGHT, line=BORDER)
    add_text(s, Inches(0.9), y + Inches(0.12), Inches(11.5), Inches(0.4), "Q. " + q,
              size=16, bold=True, color=BLUE)
    add_text(s, Inches(0.9), y + Inches(0.6), Inches(11.5), Inches(0.8), a, size=13, color=TEXT_DARK)
    y += Inches(1.7)

# ===================================================================== 8. 문의처
s = add_slide()
add_kicker_title(s, "CONTACT", "문의처")
add_table(
    s, Inches(0.6), Inches(2.0), Inches(12.1), Inches(1.3),
    ["담당", "연락처"],
    [
        ["정보전산처", "055-772-0627"],
    ],
    col_widths=[6, 6], font_size=16,
)
add_text(s, Inches(0.6), Inches(6.2), Inches(12.1), Inches(0.6),
          "감사합니다.", size=18, bold=True, color=GREY, align=PP_ALIGN.CENTER)

prs.save(OUT_PATH)
print(f"저장 완료: {OUT_PATH}")
