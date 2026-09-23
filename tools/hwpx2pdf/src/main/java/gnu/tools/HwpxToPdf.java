package gnu.tools;

import kr.dogfoot.hwpxlib.object.HWPXFile;
import kr.dogfoot.hwpxlib.object.content.section_xml.SectionXMLFile;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.Para;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.Run;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.RunItem;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.T;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.TItem;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.t.LineBreak;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.t.NormalText;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.t.Tab;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.object.Table;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.object.table.Tc;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.object.table.Tr;
import kr.dogfoot.hwpxlib.reader.HWPXReader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.pdmodel.font.PDFont;
import org.apache.pdfbox.pdmodel.font.PDType0Font;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * [T41] hwpx2pdf — hwpxlib(HWPX 파서)로 문단·표 구조를 그대로 읽어, PDFBox로 한글 폰트를 임베딩해
 * 표는 격자(테두리)까지 그리는 PDF로 새로 조판한다.
 *
 * "원본 파일의 정밀 복사"는 아니다(글꼴·자간·배경색·이미지 등은 재현하지 않음) — 대신 조문 순서·
 * 번호·개정 이력과 표의 칸 구성(격자)까지 정확하게 옮기는 것이 목표다. (README/사용자 협의 참고)
 *
 * 사용법: java -jar hwpx2pdf.jar <입력.hwpx> <출력.pdf> <글꼴.ttf> [<규정명목록.txt> <페이지맵출력.json>]
 *
 * 뒤 두 인자를 주면, 문서를 조판하는 동안 각 줄의 규정명과 정확히 일치하는(첫 등장) 문단을 만났을 때
 * 그 시점의 PDF 페이지 번호를 기록해 JSON({"규정명": 페이지번호, ...})으로 저장한다. 목차(표 셀)
 * 안의 언급은 제외되고, 실제 규정 본문 제목 문단(표가 아닌 일반 문단)만 매칭 대상이 된다.
 */
public class HwpxToPdf {
    private static final float MARGIN = 46f;
    private static final float FONT_SIZE = 10f;
    private static final float LEADING = FONT_SIZE * 1.5f;
    private static final float TABLE_FONT_SIZE = 9f;
    private static final float TABLE_CELL_PAD = 4f;
    private static final float TABLE_ROW_LEADING = TABLE_FONT_SIZE * 1.35f;

    private PDDocument doc;
    private PDFont font;
    private PDPage page;
    private PDPageContentStream cs;
    private float y;
    private final float pageWidth = PDRectangle.A4.getWidth();
    private final float pageHeight = PDRectangle.A4.getHeight();
    private final float usableWidth = pageWidth - 2 * MARGIN;

    private java.util.Set<String> pendingNames;
    private Map<String, Integer> foundPages;

    public static void main(String[] args) throws Exception {
        if (args.length < 3) {
            System.err.println("사용법: java -jar hwpx2pdf.jar <입력.hwpx> <출력.pdf> <글꼴.ttf> [<규정명목록.txt> <페이지맵출력.json>]");
            System.exit(2);
        }
        String namesFile = args.length > 3 ? args[3] : null;
        String mapOutFile = args.length > 4 ? args[4] : null;
        new HwpxToPdf().run(args[0], args[1], args[2], namesFile, mapOutFile);
    }

    private void run(String inPath, String outPath, String fontPath, String namesFile, String mapOutFile) throws Exception {
        System.out.println("[hwpx2pdf] 읽는 중: " + inPath);
        HWPXFile hwpxFile = HWPXReader.fromFilepath(inPath);

        if (namesFile != null) {
            pendingNames = new java.util.HashSet<>();
            for (String line : Files.readAllLines(new File(namesFile).toPath(), StandardCharsets.UTF_8)) {
                String n = line.trim();
                if (!n.isEmpty()) pendingNames.add(n);
            }
            foundPages = new LinkedHashMap<>();
        }

        try (PDDocument document = new PDDocument()) {
            this.doc = document;
            this.font = PDType0Font.load(document, new File(fontPath));
            newPage();

            int sectionCount = hwpxFile.sectionXMLFileList().count();
            for (int s = 0; s < sectionCount; s++) {
                SectionXMLFile section = hwpxFile.sectionXMLFileList().get(s);
                int paraCount = section.countOfPara();
                for (int p = 0; p < paraCount; p++) {
                    renderPara(section.getPara(p));
                }
            }
            closePage();
            document.save(outPath);
            System.out.println("[hwpx2pdf] 저장 완료: " + outPath + " (" + document.getNumberOfPages() + "페이지)");
        }

        if (mapOutFile != null) {
            StringBuilder json = new StringBuilder("{\n");
            int i = 0;
            for (Map.Entry<String, Integer> e : foundPages.entrySet()) {
                json.append("  \"").append(jsonEscape(e.getKey())).append("\": ").append(e.getValue());
                if (++i < foundPages.size()) json.append(",");
                json.append("\n");
            }
            json.append("}\n");
            Files.write(new File(mapOutFile).toPath(), json.toString().getBytes(StandardCharsets.UTF_8));
            if (!pendingNames.isEmpty()) {
                System.err.println("[hwpx2pdf] 경고: 문서에서 못 찾은 규정명 " + pendingNames.size() + "건: " + pendingNames);
            }
            System.out.println("[hwpx2pdf] 페이지 맵 저장 완료: " + mapOutFile + " (" + foundPages.size() + "건)");
        }
    }

    private static String jsonEscape(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    // ------------------------------------------------------------ 페이지 관리
    private boolean textOpen = false;

    private void newPage() throws Exception {
        page = new PDPage(PDRectangle.A4);
        doc.addPage(page);
        cs = new PDPageContentStream(doc, page);
        y = pageHeight - MARGIN;
        textOpen = false;
    }

    private void closePage() throws Exception {
        endTextIfOpen();
        cs.close();
    }

    private void ensureSpace(float needed) throws Exception {
        if (y - needed < MARGIN) {
            endTextIfOpen();
            cs.close();
            newPage();
        }
    }

    private void beginTextIfNeeded(float size) throws Exception {
        if (!textOpen) {
            cs.beginText();
            cs.setFont(font, size);
            cs.setLeading(LEADING);
            cs.newLineAtOffset(MARGIN, y);
            textOpen = true;
        }
    }

    private void endTextIfOpen() throws Exception {
        if (textOpen) {
            cs.endText();
            textOpen = false;
        }
    }

    // ------------------------------------------------------------ 문단 순회
    /** 문단 안의 표(Table)를 먼저 뽑아 격자로 그리고, 남는 텍스트는 줄바꿈 조판한다 */
    private void renderPara(Para para) throws Exception {
        StringBuilder text = new StringBuilder();
        List<Table> tables = new ArrayList<>();
        int runCount = para.countOfRun();
        for (int r = 0; r < runCount; r++) {
            Run run = para.getRun(r);
            int itemCount = run.countOfRunItem();
            for (int i = 0; i < itemCount; i++) {
                RunItem item = run.getRunItem(i);
                if (item instanceof T) {
                    text.append(extractT((T) item));
                } else if (item instanceof Table) {
                    tables.add((Table) item);
                }
            }
        }

        String paraText = sanitize(text.toString(), font);
        if (!paraText.isEmpty()) {
            renderParagraphText(paraText);
            if (pendingNames != null) {
                String trimmed = paraText.trim();
                if (pendingNames.remove(trimmed)) {
                    foundPages.put(trimmed, doc.getNumberOfPages());
                }
            }
        }
        for (Table table : tables) {
            renderTable(table);
        }
        if (paraText.isEmpty() && tables.isEmpty()) {
            // 빈 문단도 원본의 줄 간격을 살리기 위해 한 줄 내려준다
            ensureSpace(LEADING);
            beginTextIfNeeded(FONT_SIZE);
            cs.newLine();
            y -= LEADING;
        }
    }

    private String extractT(T t) {
        if (t.onlyText() != null) return t.onlyText();
        StringBuilder sb = new StringBuilder();
        int n = t.countOfItems();
        for (int i = 0; i < n; i++) {
            TItem item = t.getItem(i);
            if (item instanceof NormalText) sb.append(((NormalText) item).text());
            else if (item instanceof LineBreak) sb.append("\n");
            else if (item instanceof Tab) sb.append("    ");
        }
        return sb.toString();
    }

    private void renderParagraphText(String paraText) throws Exception {
        for (String line : wrap(paraText, font, FONT_SIZE, usableWidth)) {
            ensureSpace(LEADING);
            beginTextIfNeeded(FONT_SIZE);
            cs.showText(line);
            cs.newLine();
            y -= LEADING;
        }
    }

    // ------------------------------------------------------------ 표 렌더링 (격자)
    private void renderTable(Table table) throws Exception {
        endTextIfOpen();
        int rowCount = table.countOfTr();
        if (rowCount == 0) return;

        // 1) 각 셀의 텍스트와 colSpan을 먼저 모아, 열 개수·너비를 정한다 (hwpxlib의 cellSz는
        //    hwpunit 단위라 열마다 정확한 원본 비율을 얻기 번거로워, 표 안 최대 열 수 기준으로
        //    균등 분할한다 — 내용은 정확하고 칸 구획도 유지되지만 원본과 폭 비율은 다를 수 있다)
        List<List<String>> grid = new ArrayList<>();
        List<List<Integer>> spanGrid = new ArrayList<>();
        int maxCols = 0;
        for (int r = 0; r < rowCount; r++) {
            Tr tr = table.getTr(r);
            List<String> row = new ArrayList<>();
            List<Integer> spans = new ArrayList<>();
            int cols = 0;
            for (int c = 0; c < tr.countOfTc(); c++) {
                Tc tc = tr.getTc(c);
                String cellText = extractCellText(tc);
                int colSpan = 1;
                if (tc.cellSpan() != null && tc.cellSpan().colSpan() != null) {
                    colSpan = Math.max(1, tc.cellSpan().colSpan());
                }
                row.add(cellText);
                spans.add(colSpan);
                cols += colSpan;
            }
            grid.add(row);
            spanGrid.add(spans);
            maxCols = Math.max(maxCols, cols);
        }
        if (maxCols == 0) return;

        float colWidth = usableWidth / maxCols;

        for (int r = 0; r < rowCount; r++) {
            List<String> row = grid.get(r);
            List<Integer> spans = spanGrid.get(r);
            // 이 행의 각 셀을 줄바꿈해 최대 줄 수를 구하고, 그만큼의 행 높이를 확보한다
            List<List<String>> wrapped = new ArrayList<>();
            int maxLines = 1;
            for (int c = 0; c < row.size(); c++) {
                float cellW = colWidth * spans.get(c) - 2 * TABLE_CELL_PAD;
                List<String> wl = wrap(sanitize(row.get(c), font), font, TABLE_FONT_SIZE, Math.max(cellW, 20));
                wrapped.add(wl);
                maxLines = Math.max(maxLines, wl.size());
            }
            float rowHeight = maxLines * TABLE_ROW_LEADING + 2 * TABLE_CELL_PAD;
            ensureSpace(rowHeight);

            float rowTop = y;
            float x = MARGIN;
            for (int c = 0; c < row.size(); c++) {
                float cellW = colWidth * spans.get(c);
                // 테두리
                cs.setLineWidth(0.6f);
                cs.addRect(x, rowTop - rowHeight, cellW, rowHeight);
                cs.stroke();
                // 텍스트
                cs.beginText();
                cs.setFont(font, TABLE_FONT_SIZE);
                cs.setLeading(TABLE_ROW_LEADING);
                cs.newLineAtOffset(x + TABLE_CELL_PAD, rowTop - TABLE_CELL_PAD - TABLE_FONT_SIZE);
                for (String l : wrapped.get(c)) {
                    cs.showText(l);
                    cs.newLine();
                }
                cs.endText();
                x += cellW;
            }
            y = rowTop - rowHeight;
        }
        y -= TABLE_ROW_LEADING * 0.4f;  // 표 다음 여백
    }

    private String extractCellText(Tc tc) {
        StringBuilder sb = new StringBuilder();
        if (tc.subList() == null) return "";
        int n = tc.subList().countOfPara();
        for (int p = 0; p < n; p++) {
            Para para = tc.subList().getPara(p);
            for (int r = 0; r < para.countOfRun(); r++) {
                Run run = para.getRun(r);
                for (int i = 0; i < run.countOfRunItem(); i++) {
                    RunItem item = run.getRunItem(i);
                    if (item instanceof T) sb.append(extractT((T) item));
                }
            }
            if (p < n - 1) sb.append("\n");
        }
        return sb.toString();
    }

    // ------------------------------------------------------------ 글꼴·줄바꿈 유틸
    private static final Map<Character, String> GLYPH_FALLBACK = new HashMap<>();
    static {
        GLYPH_FALLBACK.put('∼', "~");
        GLYPH_FALLBACK.put('〜', "~");
        GLYPH_FALLBACK.put('～', "~");
        GLYPH_FALLBACK.put('‐', "-");
        GLYPH_FALLBACK.put('–', "-");
        GLYPH_FALLBACK.put('—', "-");
        GLYPH_FALLBACK.put('‘', "'");
        GLYPH_FALLBACK.put('’', "'");
        GLYPH_FALLBACK.put('“', "\"");
        GLYPH_FALLBACK.put('”', "\"");
    }
    private final Map<Character, Boolean> glyphCache = new HashMap<>();

    private boolean hasGlyph(PDFont font, char c) {
        Boolean cached = glyphCache.get(c);
        if (cached != null) return cached;
        boolean ok;
        try { font.encode(String.valueOf(c)); ok = true; } catch (Exception e) { ok = false; }
        glyphCache.put(c, ok);
        return ok;
    }

    private String sanitize(String s, PDFont font) {
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '\t') { b.append("    "); continue; }
            if (c == '\n') { b.append('\n'); continue; }
            if (Character.isISOControl(c)) continue;
            if (hasGlyph(font, c)) { b.append(c); continue; }
            String fb = GLYPH_FALLBACK.get(c);
            if (fb != null) b.append(fb);
        }
        return b.toString();
    }

    private List<String> wrap(String text, PDFont font, float fontSize, float maxWidth) throws Exception {
        List<String> out = new ArrayList<>();
        for (String paragraph : text.split("\n", -1)) {
            if (paragraph.isEmpty()) { out.add(""); continue; }
            StringBuilder cur = new StringBuilder();
            for (int i = 0; i < paragraph.length(); i++) {
                char ch = paragraph.charAt(i);
                String trial = cur.toString() + ch;
                float w = font.getStringWidth(trial) / 1000 * fontSize;
                if (w > maxWidth && cur.length() > 0) {
                    out.add(cur.toString());
                    cur = new StringBuilder();
                }
                cur.append(ch);
            }
            out.add(cur.toString());
        }
        return out;
    }
}
