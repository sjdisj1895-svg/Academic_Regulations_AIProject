# -*- coding: utf-8 -*-
"""
MANUAL.md / README.md 내용을 바탕으로 프로젝트 소개 슬라이드(PPTX)를 생성하는 스크립트.
비전공자(교직원·의사결정자) 대상. 경상국립대학교 공식 VI 전용색상(BS13)을 테마로 사용한다.
  - GNU Blue  #009EDB (PANTONE 2192C)      - GNU Grey #43525A (Cool Gray 11C)
  - Silver    #BCBEC0 (877C)                - Gold     #B3A177 (871C)

실행:
    python scripts/generate_pptx.py
결과:
    프로젝트 폴더에 "AI_규정통합검색시스템_소개.pptx" 생성 (2026-09 기준 T1~T20 반영, 22장)
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = os.path.join(BASE_DIR, "docs_screenshots")
ASSET_DIR = os.path.join(BASE_DIR, "web", "assets")
OUT_PATH = os.environ.get("GNU_PPTX_OUT") or os.path.join(BASE_DIR, "AI_규정통합검색시스템_소개.pptx")

# ---------------------------------------------------------------- GNU 공식 VI 색상 (BS13)
BLUE = RGBColor(0x00, 0x9E, 0xDB)        # GNU Blue (Main)
BLUE_DEEP = RGBColor(0x00, 0x7F, 0xB3)   # GNU Blue 명도 하강 톤
GREY = RGBColor(0x43, 0x52, 0x5A)        # GNU Grey (Sub)
GREY_DEEP = RGBColor(0x2F, 0x3A, 0x41)
SILVER = RGBColor(0xBC, 0xBE, 0xC0)
GOLD = RGBColor(0xB3, 0xA1, 0x77)
BG_LIGHT = RGBColor(0xF3, 0xF6, 0xF8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
TEXT_DARK = RGBColor(0x2B, 0x35, 0x3B)
TEXT_SUB = RGBColor(0x66, 0x73, 0x7A)
BORDER = RGBColor(0xE3, 0xE8, 0xEB)
RED = RGBColor(0xB2, 0x3A, 0x3A)
GREEN_OK = RGBColor(0x2E, 0x8B, 0x57)

FONT = "맑은 고딕"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
TOTAL_SLIDES = 22
_page = {"n": 0}


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
    for i, line in enumerate(text.split("\n")):
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
                font=FONT, gap_after=8):
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


def add_page_number(slide):
    n = len(prs.slides._sldIdLst)  # 실제 슬라이드 순번 (표지 포함)
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
    # 우상단 소형 시그니처 (공식 국영문 가로조합)
    sig = os.path.join(ASSET_DIR, "gnu_emblem_combo_kr_en.png")
    if os.path.exists(sig):
        slide.shapes.add_picture(sig, prs.slide_width - Inches(3.1), Inches(0.42), height=Inches(0.36))


def add_table(slide, left, top, width, height, headers, rows, col_widths=None,
              header_bg=GREY, header_fg=WHITE, font_size=13):
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


def add_card(slide, left, top, width, height, fill=WHITE, line=BORDER):
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    card.fill.solid(); card.fill.fore_color.rgb = fill
    if line is None:
        card.line.fill.background()
    else:
        card.line.color.rgb = line
    card.shadow.inherit = False
    return card


def add_picture_fit(slide, path, left, top, max_w, max_h):
    """가로/세로 한도 안에 비율 유지로 이미지를 넣는다."""
    if not os.path.exists(path):
        return None
    from PIL import Image
    with Image.open(path) as im:
        w, h = im.size
    scale = min(max_w / w, max_h / h)
    return slide.shapes.add_picture(path, left, top, width=int(w * scale), height=int(h * scale))


def shot(name):
    return os.path.join(SHOT_DIR, name)


# ============================================================ 1. 표지
s = add_slide()
add_bg(s, BLUE_DEEP, BLUE, angle=45)
sig_w = os.path.join(ASSET_DIR, "gnu_emblem_combo_kr_en_white.png")
if os.path.exists(sig_w):
    s.shapes.add_picture(sig_w, Inches(0.6), Inches(0.6), height=Inches(0.55))
emb = os.path.join(ASSET_DIR, "gnu_emblem_b.png")
if os.path.exists(emb):
    plate = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(10.3), Inches(1.6), Inches(2.4), Inches(2.4))
    plate.fill.solid(); plate.fill.fore_color.rgb = WHITE; plate.line.fill.background(); plate.shadow.inherit = False
    s.shapes.add_picture(emb, Inches(10.45), Inches(1.75), height=Inches(2.1))
add_text(s, Inches(0.6), Inches(2.4), Inches(9.5), Inches(1.6),
         "AI 기반 대학·산학협력단\n규정집 통합 검색 시스템", size=40, color=WHITE, bold=True)
add_text(s, Inches(0.6), Inches(4.2), Inches(9.5), Inches(0.9),
         "규정 426건을 조·항 단위로 검색하고, 말로 물어보면 근거 조항과 함께 답하는 서비스\n"
         "— 2026년 9월 기준 개발 현황(T1~T20) 보고 —",
         size=17, color=WHITE, line_spacing=1.3)
add_text(s, Inches(0.6), Inches(6.5), Inches(11), Inches(0.5),
         "경상국립대학교 정보전산처  ·  총무과(대학 규정) / 산학협력단 산학연구과(산학협력단 규정)",
         size=13, color=RGBColor(0xE6, 0xF5, 0xFC))

# ============================================================ 2. 한 장 요약
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "SUMMARY", "한 장 요약 — 무엇을 만들었고, 지금 어디까지 왔나")
cards = [
    ("무엇", "학교 규정 426건(대학 363 + 산학협력단 63)을 조·항 9,258개로 쪼개 넣고,\n검색창 하나로 찾아주는 서비스", BLUE),
    ("두 가지 사용법", "🔍 검색: '휴학' → 0.1초에 관련 조항\n💬 AI에게 질문하기: '휴학 신청은 언제까지?' → 수 초에 답변 + 근거 조항", BLUE_DEEP),
    ("믿을 수 있나", "AI는 검색으로 찾은 조항만 참고해 답하고, 근거가 없으면 '찾을 수 없습니다'.\n자동 시험 15+7+23문항 모두 100% 통과", GREY),
    ("어디서", "학내망 https://gapps.gnu.ac.kr/regulation/\n(업무보고 서버와 포트 공유, 현재 정보전산처 공개 단계)", GOLD),
]
x0, y0, w, h = Inches(0.7), Inches(1.75), Inches(5.85), Inches(2.25)
for i, (t, d, col) in enumerate(cards):
    left = x0 + (i % 2) * (w + Inches(0.2)); top = y0 + (i // 2) * (h + Inches(0.2))
    c = add_card(s, left, top, w, h, fill=WHITE, line=BORDER)
    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, Inches(0.12), h)
    bar.fill.solid(); bar.fill.fore_color.rgb = col; bar.line.fill.background(); bar.shadow.inherit = False
    add_text(s, left + Inches(0.35), top + Inches(0.2), w - Inches(0.6), Inches(0.45), t, size=17, color=col, bold=True)
    add_text(s, left + Inches(0.35), top + Inches(0.7), w - Inches(0.6), h - Inches(0.9), d, size=13.5, color=TEXT_DARK, line_spacing=1.35)
add_text(s, Inches(0.7), Inches(6.45), Inches(11.9), Inches(0.6),
         "담당자가 할 일은 셋: 규정이 바뀌면 명령 한 줄(refresh_all.py) · 가끔 품질 점검 · 이상 답변 신고 시 근거·로그 확인",
         size=13, color=TEXT_SUB, align=PP_ALIGN.CENTER)
add_page_number(s)

# ============================================================ 3. 추진배경
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "PROBLEM", "추진배경 및 필요성")
add_bullets(s, Inches(0.7), Inches(1.7), Inches(11.9), Inches(2.2), [
    "기존 규정집 조회는 '규정명' 검색만 가능 → 조·항 단위 세부 내용을 찾기 어려움",
    "대학 규정과 산학협력단 규정이 서로 다른 사이트에 이원화 → 검색·조회의 일관성 결여",
    "규정 용어(예: '퇴학')와 사용자 말(예: '자퇴')이 달라 검색이 안 되는 경우가 잦음",
    "담당부서·시행일·폐지 여부처럼 '누구에게 물어야 하고, 지금 유효한가'를 확인하기 번거로움",
], size=17)
add_card(s, Inches(0.7), Inches(4.3), Inches(11.9), Inches(2.3))
add_text(s, Inches(1.0), Inches(4.5), Inches(6), Inches(0.4), "관련 부서", size=15, color=GREY, bold=True)
add_bullets(s, Inches(1.0), Inches(4.95), Inches(5.8), Inches(1.5), ["(대학) 총무과 055-772-0334", "(산학협력단) 산학연구과 055-772-0211"], size=14)
add_text(s, Inches(7.0), Inches(4.5), Inches(5.3), Inches(0.4), "벤치마킹", size=15, color=GREY, bold=True)
add_bullets(s, Inches(7.0), Inches(4.95), Inches(5.3), Inches(1.5), ["규정 카테고리 구분: 충남대학교", "조회 형식: 연세대학교(rules.yonsei.ac.kr)"], size=14)
add_page_number(s)

# ============================================================ 4. 목적 / 대상
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "PURPOSE", "프로젝트 목적 & 대상 사용자")
add_text(s, Inches(0.7), Inches(1.65), Inches(6), Inches(0.4), "🎯 목적", size=17, color=GREY, bold=True)
add_bullets(s, Inches(0.7), Inches(2.1), Inches(6.0), Inches(3.8), [
    "대학 + 산학협력단 규정을 한 검색창에서",
    "규정명뿐 아니라 조·항 단위 본문까지 검색",
    "키워드 + 의미(AI) 결합으로 자연어 질문도 처리",
    "규정 + 담당부서·연락처 + 시행일을 원스톱으로",
    "말로 물으면 근거 조항과 함께 답변 (AI 질문하기)",
], size=15)
add_text(s, Inches(6.9), Inches(1.65), Inches(5.6), Inches(0.4), "👥 대상", size=17, color=GREY, bold=True)
add_bullets(s, Inches(6.9), Inches(2.1), Inches(5.6), Inches(3.8), [
    "1차: 학내 구성원 (학생·교원·직원)",
    "2차: 규정 관리 담당자 (총무과·산학연구과)",
    "운영자: 정보전산처 (데이터 갱신·서버 운영)",
], size=15)
add_page_number(s)

# ============================================================ 5. 전체 여정 타임라인
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "JOURNEY", "개발 여정 한눈에 (T1 → T20)")
phases = [
    ("T1~T5", "검색 시스템", "수집·청킹·벡터DB\n하이브리드 검색·웹 화면\n품질 100%, 0.05초", BLUE),
    ("T6~T10", "AI 질문하기", "검색 근거만으로 답변\n환각 방지 가드레일\n로그·비용·장애 대응", BLUE_DEEP),
    ("T11~T15", "정확도 개선", "모델 교체 2회 → 롤백\n재순위화·문맥 보강\n질의 재작성, Claude 전환", GREY),
    ("T16", "운영 배포", "리눅스 서버 + systemd\nnginx /regulation/\n(업무보고와 포트 공유)", GREY_DEEP),
    ("T17~T20", "화면·데이터", "카테고리 정리·공식 VI\n시행일 표시·폐지 제외\n학적 평가셋 23문항", GOLD),
]
x = Inches(0.55); w = Inches(2.35); gap = Inches(0.12)
for i, (tag, title, desc, color) in enumerate(phases):
    box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, Inches(2.2), w, Inches(2.5))
    box.fill.solid(); box.fill.fore_color.rgb = color; box.line.fill.background(); box.shadow.inherit = False
    tf = box.text_frame; tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.TOP; tf.margin_top = Pt(14)
    p0 = tf.paragraphs[0]; p0.text = tag; p0.alignment = PP_ALIGN.CENTER
    for r in p0.runs: r.font.size = Pt(14); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = FONT
    p1 = tf.add_paragraph(); p1.text = title; p1.alignment = PP_ALIGN.CENTER; p1.space_before = Pt(6)
    for r in p1.runs: r.font.size = Pt(16); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = FONT
    p2 = tf.add_paragraph(); p2.text = desc; p2.alignment = PP_ALIGN.CENTER; p2.space_before = Pt(12)
    for r in p2.runs: r.font.size = Pt(11.5); r.font.color.rgb = RGBColor(0xF0, 0xF6, 0xFA); r.font.name = FONT
    if i < len(phases) - 1:
        arrow = s.shapes.add_shape(MSO_SHAPE.CHEVRON, x + w + Emu(8000), Inches(3.3), Inches(0.26), Inches(0.5))
        arrow.fill.solid(); arrow.fill.fore_color.rgb = SILVER; arrow.line.fill.background(); arrow.shadow.inherit = False
    x = x + w + gap
add_text(s, Inches(0.7), Inches(5.5), Inches(11.9), Inches(1.3),
         "처음 계획(T1~T5)은 '검색'까지였고, 그 뒤 AI 질문하기·정확도 개선·운영 배포·다듬기가 이어졌습니다.\n"
         "특히 T11·T13처럼 '해봤지만 되돌린' 단계도 기록해, 왜 지금 구조가 됐는지 근거를 남겼습니다.",
         size=14, color=TEXT_SUB, align=PP_ALIGN.CENTER, line_spacing=1.35)
add_page_number(s)

# ============================================================ 6. 검색이 동작하는 원리 (비전공자용)
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "HOW IT WORKS", "검색은 어떻게 찾아내나 — 두 가지 방법을 섞어 씁니다")
steps = [
    ("①", "규정 원문 수집", "국가법령정보센터·학교 홈페이지·\n산학협력단 규정집에서 426건 자동 수집", BLUE),
    ("②", "조·항 단위로 쪼개기", "'제31조(휴학) ①…' 단위 9,258개\n각 조문에 소속 장(章) 제목 부착", BLUE),
    ("③", "뜻을 숫자로 저장", "한국어 AI(KR-SBERT)가 문장의 '뜻'을\n숫자 벡터로 → 벡터DB(ChromaDB)", BLUE_DEEP),
    ("④", "두 방법으로 찾기", "키워드 일치(BM25) 40% +\n뜻이 비슷한 조항(벡터) 60%\n질문형 문장이면 뜻 75%", GREY),
    ("⑤", "결과 카드", "규정명·조항·본문 발췌·담당부서·\n시행일 · 미리보기 · 원문 이동", GOLD),
]
x = Inches(0.55); w = Inches(2.35); gap = Inches(0.12)
for i, (tag, title, desc, color) in enumerate(steps):
    c = add_card(s, x, Inches(1.9), w, Inches(3.0), fill=WHITE, line=BORDER)
    circ = s.shapes.add_shape(MSO_SHAPE.OVAL, x + Inches(0.15), Inches(2.05), Inches(0.5), Inches(0.5))
    circ.fill.solid(); circ.fill.fore_color.rgb = color; circ.line.fill.background(); circ.shadow.inherit = False
    circ.text_frame.text = tag; circ.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    for r in circ.text_frame.paragraphs[0].runs: r.font.bold = True; r.font.size = Pt(14); r.font.color.rgb = WHITE; r.font.name = FONT
    add_text(s, x + Inches(0.15), Inches(2.65), w - Inches(0.3), Inches(0.5), title, size=14.5, color=color, bold=True)
    add_text(s, x + Inches(0.15), Inches(3.15), w - Inches(0.3), Inches(1.7), desc, size=11.5, color=TEXT_DARK, line_spacing=1.3)
    if i < len(steps) - 1:
        arrow = s.shapes.add_shape(MSO_SHAPE.CHEVRON, x + w + Emu(8000), Inches(3.15), Inches(0.26), Inches(0.5))
        arrow.fill.solid(); arrow.fill.fore_color.rgb = SILVER; arrow.line.fill.background(); arrow.shadow.inherit = False
    x = x + w + gap
add_card(s, Inches(0.7), Inches(5.2), Inches(11.9), Inches(1.55), fill=WHITE, line=BLUE)
add_text(s, Inches(1.0), Inches(5.32), Inches(11.3), Inches(0.4), "비유하면", size=14, color=BLUE, bold=True)
add_text(s, Inches(1.0), Inches(5.7), Inches(11.3), Inches(1.0),
         "키워드 검색은 '책 뒤 색인에서 단어 찾기', 의미 검색은 '사서가 질문의 뜻을 이해하고 비슷한 내용의 조항을 골라주기'입니다. "
         "둘을 합치면 정확한 단어를 몰라도(예: '자퇴' ↔ 규정은 '퇴학') 찾을 수 있고, 학적 용어 동의어 사전으로 그 간극을 더 좁혔습니다.",
         size=13, color=TEXT_DARK, line_spacing=1.35)
add_page_number(s)

# ============================================================ 7. AI 질문하기 원리 + 안전장치
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "AI Q&A", "AI에게 질문하기 — '근거만 보고 답하는' AI")
flow = [("질문", "휴학 신청은\n언제까지 해야 해?", GREY), ("① 질의 재작성", "규정 문체 검색어로\n'휴학 신청 시기 및 절차'", BLUE),
        ("② 검색+재순위화", "상위 20개 후보를\n정밀 재비교 → 5개", BLUE), ("③ 답변 생성", "찾은 5개 조항만\n참고자료로 문장 작성", BLUE_DEEP),
        ("④ 검증", "근거 없는 규정명·숫자\n자동 경고 / 출처 첨부", GOLD)]
x = Inches(0.55); w = Inches(2.35); gap = Inches(0.12)
for i, (t, d, col) in enumerate(flow):
    box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, Inches(1.8), w, Inches(1.75))
    box.fill.solid(); box.fill.fore_color.rgb = col; box.line.fill.background(); box.shadow.inherit = False
    tf = box.text_frame; tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p0 = tf.paragraphs[0]; p0.text = t; p0.alignment = PP_ALIGN.CENTER
    for r in p0.runs: r.font.size = Pt(14); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = FONT
    p1 = tf.add_paragraph(); p1.text = d; p1.alignment = PP_ALIGN.CENTER; p1.space_before = Pt(6)
    for r in p1.runs: r.font.size = Pt(11.5); r.font.color.rgb = RGBColor(0xF0, 0xF6, 0xFA); r.font.name = FONT
    if i < len(flow) - 1:
        arrow = s.shapes.add_shape(MSO_SHAPE.CHEVRON, x + w + Emu(8000), Inches(2.45), Inches(0.26), Inches(0.45))
        arrow.fill.solid(); arrow.fill.fore_color.rgb = SILVER; arrow.line.fill.background(); arrow.shadow.inherit = False
    x = x + w + gap
add_text(s, Inches(0.7), Inches(3.8), Inches(11.9), Inches(0.4), "🛡 환각(지어내기) 방지 안전장치 — 여러 겹", size=16, color=GREY, bold=True)
headers = ["안전장치", "하는 일"]
rows = [
    ["관련성 문턱", "찾은 조항의 관련 점수가 기준(0.5) 미만이면 AI를 부르지 않고 즉시 '규정에서 찾을 수 없습니다'"],
    ["규정명 검증", "답변에 근거 목록에 없는 규정명이 등장하면 ⚠️ 자동 경고 문구를 붙임"],
    ["숫자 검증", "답변의 숫자가 참고자료에 없으면 경고 — '2분의 1 경과 전'을 '몇 주 전'으로 환산하는 것도 금지"],
    ["수치 질문 규칙", "금액·한도·기간을 묻는데 참고자료에 그 수치가 없으면 요약하지 말고 '찾을 수 없습니다'로 먼저 답하게 지시"],
    ["폐지 규정 제외", "폐지된 32건은 검색·답변 근거에서 자동 제외 (토글로 포함 가능)"],
]
add_table(s, Inches(0.7), Inches(4.25), Inches(11.9), Inches(2.5), headers, rows, col_widths=[2.2, 9.7], font_size=12)
add_page_number(s)

# ============================================================ 8. 화면 — 홈/검색 결과
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "SCREEN", "실제 화면 ① — 검색 결과 (공식 VI · 시행일 표시)")
add_picture_fit(s, shot("v2_results.png"), Inches(3.6), Inches(1.6), Inches(9.2), Inches(5.6))
add_bullets(s, Inches(0.6), Inches(1.8), Inches(2.9), Inches(5.0), [
    "상단: 공식 시그니처(BS08) 브랜드 바",
    "GNU Blue 헤더 + 흰 원판 엠블럼",
    "카테고리: 대학 / 산학협력단 소그룹",
    "'폐지된 규정도 포함' 토글",
    "카드 우상단: 시행 2021-03-01 · 제정",
    "담당부서: 실무부서(상위) · 전화(클릭)",
    "검색어 형광펜 하이라이트",
], size=12.5)
add_page_number(s)

# ============================================================ 9. 화면 — AI 질문 / 폐지 / 모바일
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "SCREEN", "실제 화면 ② — AI에게 질문하기 · 폐지 규정 표시 · 모바일")
add_picture_fit(s, shot("v2_ask_mode.png"), Inches(0.6), Inches(1.7), Inches(6.3), Inches(3.3))
add_text(s, Inches(0.6), Inches(5.05), Inches(6.3), Inches(0.35), "① AI에게 질문하기 탭 (예시 질문·안내 문구)", size=12.5, color=GREY, bold=True, align=PP_ALIGN.CENTER)
add_picture_fit(s, shot("v2_repealed_card.png"), Inches(0.6), Inches(5.45), Inches(6.3), Inches(1.4))
add_text(s, Inches(7.1), Inches(6.85), Inches(5.6), Inches(0.35), "③ 모바일(390px) — 소그룹 세로 배치", size=12.5, color=GREY, bold=True, align=PP_ALIGN.CENTER)
add_picture_fit(s, shot("v2_mobile.png"), Inches(8.6), Inches(1.6), Inches(2.6), Inches(5.2))
add_text(s, Inches(0.6), Inches(6.85), Inches(6.3), Inches(0.35), "② 폐지 규정 카드 — 빨간 '폐지' 배지·붉은 배경 (토글을 켰을 때만 표시)", size=12, color=RED, bold=True, align=PP_ALIGN.CENTER)
add_page_number(s)

# ============================================================ 10. 기술 스택
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "TECH STACK", "기술 스택 — 무료·오픈소스 기반 (유료는 답변용 AI API만)")
headers = ["단계", "기술", "쉽게 말하면"]
rows = [
    ["수집", "Python 표준 라이브러리, law.go.kr 연동, HWPX 파싱", "사람이 복사·붙이기 하던 걸 자동으로"],
    ["청킹", "정규식 기반 조문 분할 + 장(章) 제목 부착 (자체 개발)", "규정을 '조·항' 카드로 잘게 나누기"],
    ["임베딩", "KR-SBERT (서울대 한국어 특화 모델, 무료·오프라인)", "문장의 뜻을 숫자로 바꾸는 번역기"],
    ["벡터DB", "ChromaDB (임베디드, 서버 설치 불필요)", "그 숫자를 저장해 두는 창고"],
    ["검색 API", "FastAPI + 자체 BM25 + 하이브리드 결합", "키워드·의미 검색을 합쳐 순위 매기기"],
    ["재순위화", "BAAI/bge-reranker-v2-m3 (cross-encoder)", "상위 20개를 정밀 재채점 (AI 질문 탭만)"],
    ["답변 AI", "Claude Haiku 4.5 (학교 FactChat API) / 대체: Qwen2.5-1.5B 로컬", "찾은 조항을 읽고 답변 문장 작성"],
    ["웹 화면", "순수 HTML/CSS/JS, 공식 VI 색상", "빌드 도구 없이 서버가 바로 서빙"],
    ["운영", "Linux + systemd + nginx(/regulation/) · refresh_all.py", "항상 켜져 있고, 갱신은 한 줄"],
]
add_table(s, Inches(0.7), Inches(1.6), Inches(11.9), Inches(5.2), headers, rows, col_widths=[1.4, 5.6, 4.9], font_size=12)
add_page_number(s)

# ============================================================ 11. 결과 — 검색 시스템 (T1~T5)
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "RESULT ①", "검색 시스템 (T1~T5) — 수집·청킹·검색·화면·운영")
headers = ["단계", "핵심 결과"]
rows = [
    ["T1 수집", "426건 (대학 학칙 1·규정 228·지침 134 / 산학협력단 63) · 실패 0건 · 조항별 실제 담당부서·연락처 추출"],
    ["T2 청킹·임베딩", "9,258개 조·항 청크(소속 장 제목 포함) → KR-SBERT 임베딩 → ChromaDB"],
    ["T3 검색 API", "하이브리드(의미 60%+키워드 40%) · 출처/카테고리 필터 · 미리보기 API · 응답 0.05초"],
    ["T4 웹 화면", "검색창·필터·결과 카드·하이라이트·미리보기 모달·원문 이동·모바일 반응형"],
    ["T5 품질·운영", "자주 쓰는 검색어 15개 자동 점검 15/15(100%) · 원클릭 갱신(refresh_all.py) · 운영 매뉴얼"],
]
add_table(s, Inches(0.7), Inches(1.7), Inches(11.9), Inches(3.6), headers, rows, col_widths=[1.9, 10.0], font_size=13.5)
add_page_number(s)

# ============================================================ 12. 결과 — AI 질문하기 (T6~T10)
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "RESULT ②", "AI에게 질문하기 (T6~T10) — 답변 생성과 환각 방지")
rows = [
    ["T6 RAG 엔진", "검색 → 참고자료 조립 → 답변 생성 파이프라인. 참고자료 밖 내용은 '찾을 수 없습니다'"],
    ["T7 API", "/api/ask 추가 (기존 검색 API 무변경) · 60초 시간 초과 시 검색 결과만 안전 반환"],
    ["T8 화면", "검색 ↔ AI 질문하기 탭, 채팅형 답변 + 근거 조항 카드, 'AI 생성 참고용' 안내 문구"],
    ["T9 품질", "자동 평가 7문항: 답해야 할 4 · 거절해야 할 3 → 7/7(100%). 흔한 단어 하나로 답을 지어내던 문제 발견·수정"],
    ["T10 운영", "질문·답변 로그(개인정보 없음) · 비용 집계 스크립트 · AI 장애 시 검색 전용 모드 자동 전환"],
]
add_table(s, Inches(0.7), Inches(1.7), Inches(11.9), Inches(3.6), headers, rows, col_widths=[1.9, 10.0], font_size=13.5)
add_page_number(s)

# ============================================================ 13. 정확도 개선 여정 (T11~T15)
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "RESULT ③", "정확도 개선 여정 (T11~T15) — 해보고, 되돌리고, 다른 길로")
headers = ["단계", "시도", "결과 / 배운 점"]
rows = [
    ["T11", "임베딩 모델을 BGE-M3로 교체", "⛔ 롤백 — 무관한 질문(주식 시세)도 유사도 0.93으로 높게 나와 '거절' 안전장치 무력화"],
    ["T12", "재순위화(cross-encoder) + 조문에 장(章) 제목 부착", "✅ '휴학하려면 어떻게 해?' 오답 → 학사관리 규정 제31조 정답. 일반 검색 속도는 그대로"],
    ["T13", "임베딩 모델을 multilingual-e5-large로 교체", "⛔ 롤백 — 관련/무관 점수 차 0.02로 너무 좁고, 다른 주제 조항으로 오답 생성"],
    ["T14", "재순위화가 점수 낮은 후보를 1위로 올리는 결함 수정", "✅ 하이브리드 점수 게이트 도입 → T9 6/7 → 7/7"],
    ["T15", "질문형 질의 의미 비중↑ + LLM 질의 재작성 + 운영 AI를 Claude로", "✅ 답변 수십 초 → 수 초, 수치 없으면 '찾을 수 없다'고 먼저 답하도록 보강"],
]
add_table(s, Inches(0.7), Inches(1.65), Inches(11.9), Inches(4.3), headers, rows, col_widths=[0.9, 4.2, 6.8], font_size=12.5)
add_text(s, Inches(0.7), Inches(6.2), Inches(11.9), Inches(0.7),
         "교훈: '더 좋은 AI 모델'로 바꾸는 것보다, 검증된 안전장치를 유지한 채 검색 파이프라인을 다듬는 쪽이 이 도메인에선 더 안전하고 효과적이었습니다.",
         size=13, color=TEXT_SUB, align=PP_ALIGN.CENTER)
add_page_number(s)

# ============================================================ 14. 운영 배포 (T16)
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "RESULT ④", "운영 배포 (T16) — 리눅스 서버, 업무보고 페이지와 포트 공유")
add_card(s, Inches(0.7), Inches(1.7), Inches(11.9), Inches(2.2), fill=GREY, line=None)
add_text(s, Inches(1.0), Inches(1.85), Inches(11.3), Inches(0.4), "요청 흐름", size=14, color=RGBColor(0x9F, 0xDD, 0xF5), bold=True)
add_text(s, Inches(1.0), Inches(2.3), Inches(11.3), Inches(1.5),
         "https://gapps.gnu.ac.kr/            → nginx(80/443) → 127.0.0.1:8080  주간업무보고 (기존 그대로)\n"
         "https://gapps.gnu.ac.kr/regulation/ → nginx(80/443) → 127.0.0.1:8000  규정 통합 검색 (신규)\n\n"
         "nginx 설정에 location 블록 하나만 추가 · reload(무중단) · 백업으로 1분 내 롤백 가능",
         size=13.5, color=WHITE, line_spacing=1.35)
add_bullets(s, Inches(0.7), Inches(4.2), Inches(11.9), Inches(2.6), [
    "서버: Linux(CentOS 계열) + Python 가상환경 + systemd 서비스(재부팅 시 자동 시작)",
    "겪은 문제와 해결: 오래된 sqlite3 → pysqlite3 교체 / Windows 경로 구분자(\\) → '/' 정규화 / SELinux·firewalld / systemd는 .bashrc를 읽지 않으므로 Environment=로 API 키 지정",
    "웹 화면은 자기 경로를 보고 API 주소를 자동 계산 → :8000 직접 접속과 /regulation/ 경로 모두 같은 코드로 동작",
    "현재 학내망·정보전산처 공개 단계. 정착 후 :8000 직접 접근은 닫을 예정",
], size=13.5)
add_page_number(s)

# ============================================================ 15. 화면·데이터 다듬기 (T17~T20)
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "RESULT ⑤", "화면·데이터 다듬기 (T17~T20)")
headers = ["단계", "무엇을", "왜 / 효과"]
rows = [
    ["T17", "카테고리를 대학(학칙/규정/지침) · 산학협력단(제1~7편) 소그룹으로, 담당부서 표기 통일, 데이터 기준일·공식 푸터", "두 체계가 한 줄에 섞여 헷갈리던 문제 해소, 전화 클릭 통화"],
    ["T18", "학적 질문 23문항 평가셋 · 부설고/중학교 학칙 감점 · 학적 동의어(자퇴→퇴학 등)", "가장 많이 묻는 영역 정기 점검. 부설학교 학칙 혼입 2→0건, 23/23"],
    ["T19", "경상국립대 공식 VI: 전용색상 BS13, 시그니처 BS08, 엠블럼", "브랜드 일관성. 비공식 색 제거. 사용 승인은 추후 총무과 요청"],
    ["T20", "시행일·개정일·규정번호 수집(424/426) · 폐지 규정 32건 기본 제외 + 토글", "'지금 유효한 규정인가'를 바로 확인. 폐지 규정을 근거로 답하던 위험 제거"],
]
add_table(s, Inches(0.7), Inches(1.65), Inches(11.9), Inches(4.4), headers, rows, col_widths=[0.9, 6.0, 5.0], font_size=12.5)
add_page_number(s)

# ============================================================ 16. 폐지 규정 발견 (강조)
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "FINDING", "발견 — 폐지된 규정 32건이 '현행'처럼 검색되고 있었습니다")
add_card(s, Inches(0.7), Inches(1.7), Inches(5.7), Inches(4.9), fill=WHITE, line=RED)
add_text(s, Inches(1.0), Inches(1.9), Inches(5.1), Inches(0.4), "무슨 문제였나", size=16, color=RED, bold=True)
add_bullets(s, Inches(1.0), Inches(2.4), Inches(5.1), Inches(4.0), [
    "426건 중 32건(7.5%)이 이미 폐지된 규정 — 장학위원회 규정, 발전기금재단 연구비 지원 지침, 복수학사학위제 운영 지침 등",
    "원문 사이트에는 남아 있어 수집됐고, 카드에 표시도 없어 사용자가 구분할 수 없었음",
    "AI 답변이 폐지 규정을 근거로 인용할 위험",
], size=13.5)
add_card(s, Inches(6.9), Inches(1.7), Inches(5.7), Inches(4.9), fill=WHITE, line=GREEN_OK)
add_text(s, Inches(7.2), Inches(1.9), Inches(5.1), Inches(0.4), "어떻게 해결했나", size=16, color=GREEN_OK, bold=True)
add_bullets(s, Inches(7.2), Inches(2.4), Inches(5.1), Inches(4.0), [
    "법령정보센터 원문 헤더 '[시행 2026.5.29.] [학칙 제529호, 2026.5.29., 일부개정]'를 읽어 시행일·개정종류·폐지 여부를 자동 판별",
    "폐지 규정은 검색·AI 근거에서 기본 제외, 필요 시 '폐지된 규정도 포함' 토글 (빨간 배지로 구분)",
    "재수집 없이 헤더만 다시 읽어 3~4분에 완료, 이후 갱신(refresh_all.py) 때 자동 실행",
], size=13.5)
add_page_number(s)

# ============================================================ 17. 품질 지표 종합
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "QUALITY", "품질 지표 종합 (2026-09 기준, 변경마다 자동 재검증)")
headers = ["평가", "무엇을 확인하나", "결과", "목표"]
rows = [
    ["T5 검색 품질 (15문항)", "자주 쓰는 검색어·질문이 상위 5건에 관련 규정을 내는지", "15/15 (100%) · 평균 0.04초", "100% · 3초 이내 ✅"],
    ["T9 RAG 품질 (7문항)", "답해야 할 질문엔 근거로 답하고, 무관·수치 없는 질문은 거절하는지", "7/7 (100%) · 숫자 환각 0~1건(경고 처리)", "100% ✅"],
    ["학적 평가 (23문항)", "휴학·복학·전과·수강·성적·졸업 질문의 정답 조항이 상위 5건에 있는지", "23/23 (100%) · 부설학교 학칙 1위 0건", "100% · 0건 ✅"],
    ["화면 검증", "데스크톱·모바일 렌더링, 콘솔 오류", "Playwright 자동 캡처, 오류 0", "오류 0 ✅"],
    ["데이터", "규정 수 · 청크 수 · 시행일 확보 · 폐지 식별", "426건 · 9,258개 · 424/426 · 32건", "—"],
]
add_table(s, Inches(0.7), Inches(1.65), Inches(11.9), Inches(3.9), headers, rows, col_widths=[2.4, 5.0, 3.2, 1.9], font_size=12.5)
add_text(s, Inches(0.7), Inches(5.8), Inches(11.9), Inches(0.9),
         "남은 과제(기록됨): 학부 질문에 대학원 규정이 1위로 오는 3건 · 재순위화 단계 약 10초(AI 질문 탭의 병목) · VI 사용 승인",
         size=13, color=TEXT_SUB, align=PP_ALIGN.CENTER)
add_page_number(s)

# ============================================================ 18. 운영 매뉴얼 요약
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "OPERATION", "담당자가 할 일 — 운영 매뉴얼(MANUAL.md) 요약")
steps = [
    ("1", "규정이 바뀌었을 때", "python scripts/refresh_all.py  (수집 → 시행일 보강 → 청킹 → 벡터DB → 점검, 자동) · 특정 규정만: --skip-collect --name"),
    ("2", "가끔 품질 점검", "evaluate_search.py(15문항) · evaluate_rag.py(7문항) · evaluate_academic.py(학적 23문항) → 100%인지 확인"),
    ("3", "이상 답변 신고 시", "화면의 근거 조항 확인 → data/rag_logs/ 로그 확인 → 개발 담당자에게 질문·시간 전달"),
    ("4", "서버 반영(리눅스)", "git pull → sudo systemctl restart gnu-regulation-search  (nginx는 건드리지 않음)"),
    ("5", "AI 종류·비용", "FactChat API 키는 서버 환경변수로만 · rag_cost_report.py로 호출 수·비용 확인"),
]
y = Inches(1.7)
for num, title, desc in steps:
    circ = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.7), y, Inches(0.5), Inches(0.5))
    circ.fill.solid(); circ.fill.fore_color.rgb = BLUE; circ.line.fill.background(); circ.shadow.inherit = False
    circ.text_frame.text = num; circ.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    for r in circ.text_frame.paragraphs[0].runs: r.font.bold = True; r.font.size = Pt(16); r.font.color.rgb = WHITE; r.font.name = FONT
    add_text(s, Inches(1.4), y - Inches(0.03), Inches(2.9), Inches(0.5), title, size=15, color=GREY, bold=True)
    add_text(s, Inches(4.3), y - Inches(0.03), Inches(8.3), Inches(0.8), desc, size=12.5, color=TEXT_DARK, line_spacing=1.3)
    y += Inches(0.95)
add_page_number(s)

# ============================================================ 19. 보안·비용·한계
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "NOTES", "알아두실 점 — 보안 · 비용 · 한계")
cols = [
    ("🔐 보안", ["API 키는 서버 환경변수(systemd Environment=)로만 보관, 문서·채팅 공유 금지",
               "질문·답변 로그에 개인정보 저장 안 함", "외부 API 사용 시 질문 내용이 외부(AI 제공사)로 전송됨 — 민감 내용 주의"], GREY),
    ("💰 비용", ["검색·임베딩·재순위화: 전부 무료 오픈소스, 서버 내부 처리",
               "답변 AI(Claude Haiku 4.5): 학교 FactChat API 사용량 과금 — rag_cost_report.py로 집계",
               "API 없으면 무료 로컬 모델로 자동 대체(느림)"], BLUE_DEEP),
    ("⚠️ 한계", ["AI 답변은 참고용, 법적 효력은 원본 규정", "규정 원문이 바뀌면 refresh_all.py 실행 전까지는 이전 내용",
               "학부 질문에 대학원 규정이 먼저 나오는 경우 일부 · AI 질문 탭 응답 10초 안팎"], GOLD),
]
x = Inches(0.7)
for t, items, col in cols:
    add_card(s, x, Inches(1.7), Inches(3.8), Inches(4.9), fill=WHITE, line=BORDER)
    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, Inches(1.7), Inches(3.8), Inches(0.12))
    bar.fill.solid(); bar.fill.fore_color.rgb = col; bar.line.fill.background(); bar.shadow.inherit = False
    add_text(s, x + Inches(0.25), Inches(1.95), Inches(3.3), Inches(0.45), t, size=17, color=col, bold=True)
    add_bullets(s, x + Inches(0.25), Inches(2.5), Inches(3.3), Inches(4.0), items, size=12.5)
    x += Inches(4.05)
add_page_number(s)

# ============================================================ 20. 기대효과
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "EFFECT", "기대효과")
add_card(s, Inches(0.7), Inches(1.8), Inches(5.8), Inches(4.4), fill=GREY, line=None)
add_text(s, Inches(1.0), Inches(2.0), Inches(5.2), Inches(0.4), "행정 서비스 개선", size=17, color=WHITE, bold=True)
add_bullets(s, Inches(1.0), Inches(2.5), Inches(5.2), Inches(3.5), [
    "대학·산학협력단 규정을 한 곳에서, 조·항 단위로",
    "규정 + 담당부서 + 시행일 + 유효 여부를 원스톱 확인",
    "규정 개정 시 명령 한 줄로 갱신, 폐지 규정 자동 제외",
    "반복 문의(휴학·연구비 등) 1차 응대를 AI가 근거와 함께",
], size=14, color=WHITE)
add_card(s, Inches(6.8), Inches(1.8), Inches(5.8), Inches(4.4), fill=BLUE, line=None)
add_text(s, Inches(7.1), Inches(2.0), Inches(5.2), Inches(0.4), "학내 구성원 편의 향상", size=17, color=WHITE, bold=True)
add_bullets(s, Inches(7.1), Inches(2.5), Inches(5.2), Inches(3.5), [
    "정확한 규정 용어를 몰라도 말로 물어서 찾기",
    "검색 0.05초, AI 답변 수 초 — 근거 조항 즉시 확인",
    "모바일에서도 동일하게 이용",
    "경상국립대 공식 VI로 일관된 브랜드 경험",
], size=14, color=WHITE)
add_page_number(s)

# ============================================================ 21. 향후 계획
s = add_slide(); add_bg(s, BG_LIGHT)
add_kicker_title(s, "NEXT", "향후 계획 (제안)")
headers = ["구분", "내용", "비고"]
rows = [
    ["공개 확대", "정보전산처 → 총무과·산학연구과 검수 → 전체 학내 구성원 공개", "VI 사용 승인 병행"],
    ["정확도", "학부/대학원 규정 우선순위 조정 · 재순위화 후보 20→10개로 응답 단축 · 사용자 👍👎 피드백 수집", "평가셋 확대"],
    ["데이터", "규정 간 위임 관계(학칙 ↔ 하위 지침) 표시 · 개정 이력 보기", "law.go.kr 연혁 활용"],
    ["운영", "정기 갱신 일정(월 1회) · 로그 기반 자주 묻는 질문 칩 · :8000 직접 접근 차단", "MANUAL 반영"],
]
add_table(s, Inches(0.7), Inches(1.7), Inches(11.9), Inches(3.3), headers, rows, col_widths=[1.6, 7.6, 2.7], font_size=13)
add_page_number(s)

# ============================================================ 22. 마무리
s = add_slide()
add_bg(s, BLUE_DEEP, BLUE, angle=45)
if os.path.exists(sig_w):
    s.shapes.add_picture(sig_w, Inches(5.2), Inches(1.6), height=Inches(0.6))
add_text(s, Inches(0.8), Inches(2.6), Inches(11.7), Inches(1.0), "감사합니다", size=44, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
add_text(s, Inches(0.8), Inches(3.7), Inches(11.7), Inches(0.6), "AI 기반 대학·산학협력단 규정집 통합 검색 시스템  ·  https://gapps.gnu.ac.kr/regulation/", size=17, color=WHITE, align=PP_ALIGN.CENTER)
add_text(s, Inches(0.8), Inches(4.5), Inches(11.7), Inches(0.5),
         "문의 : 정보전산처(시스템 운영) · 총무과 055-772-0334(대학 규정) · 산학연구과 055-772-0211(산학협력단 규정)",
         size=13, color=RGBColor(0xE6, 0xF5, 0xFC), align=PP_ALIGN.CENTER)
add_text(s, Inches(0.8), Inches(6.6), Inches(11.7), Inches(0.4),
         "참고 문서 : README.md(개발 현황·근거) · MANUAL.md(운영 매뉴얼) · PRD.md · TASKS.md",
         size=12, color=RGBColor(0xD0, 0xEC, 0xF8), align=PP_ALIGN.CENTER)

prs.save(OUT_PATH)
print("saved:", OUT_PATH)
print("slide count:", len(prs.slides._sldIdLst))
