// ===================== 설정 =====================
// API 서버가 이 정적 파일을 함께 서빙하므로 같은 오리진을 기본값으로 사용한다.
// [T16] 운영 서버에서는 nginx가 https://gapps.gnu.ac.kr/regulation/ 경로를 127.0.0.1:8000으로
// 넘겨주므로(접두어 /regulation 은 nginx가 떼고 전달), 브라우저가 보는 주소에는 접두어가 있고
// FastAPI가 보는 주소에는 없다. 그래서 API 호출도 "현재 페이지가 놓인 디렉터리" 기준으로
// 접두어를 자동 계산한다: 페이지가 /regulation/ 이면 /regulation/api/..., 루트(:8000/)면 /api/...
// → 로컬 개발(:8000), 현재 운영(:8000), 경로 배포(/regulation/) 모두 코드 수정 없이 동작.
// 파일을 다른 서버(예: 5500 포트)로 따로 열었을 때는 아래 값을 API 서버 주소로 바꿔주세요.
const API_BASE = window.location.pathname.replace(/\/[^/]*$/, "");  // 예: "" 또는 "/regulation"

const state = {
  source: "",     // "" | "대학" | "산학협력단"
  category: "",   // "" | "학칙" | "규정" | ...
  lastQuery: "",
  mode: "search", // "search" | "ask"
  lastAskQuery: "",
  includeRepealed: false, // [T20] 폐지 규정 포함 여부 (기본: 제외)
  chatHistory: [],        // [T26] 직전 대화 [{question, answer}] — 멀티턴용, 최근 6개까지 보관
  sort: "relevance",      // [T27] relevance | date
  recentOnly: false,      // [T27] 최근 1년 개정만
  aiEnabled: true,        // [T30] 서버 스위치(GNU_AI_TAB_ENABLED). false면 AI 탭을 화면에서 숨김
};

// [T27] "최근 1년" 기준 날짜 (YYYY-MM-DD)
function oneYearAgoISO() {
  const d = new Date(); d.setFullYear(d.getFullYear() - 1);
  return d.toISOString().slice(0, 10);
}

const el = {
  form: document.getElementById("search-form"),
  input: document.getElementById("search-input"),
  statusArea: document.getElementById("status-area"),
  results: document.getElementById("results"),
  sourceFilters: document.getElementById("source-filters"),
  categoryFilters: document.getElementById("category-filters"),
  modalOverlay: document.getElementById("modal-overlay"),
  modalClose: document.getElementById("modal-close"),
  modalBadge: document.getElementById("modal-badge"),
  modalTitle: document.getElementById("modal-title"),
  modalMeta: document.getElementById("modal-meta"),
  modalBody: document.getElementById("modal-body"),
  modalSiteLink: document.getElementById("modal-site-link"),
  tabArticle: document.getElementById("tab-article"),
  tabFull: document.getElementById("tab-full"),
  modeTabs: document.getElementById("mode-tabs"),
  askForm: document.getElementById("ask-form"),
  askInput: document.getElementById("ask-input"),
  askBtn: document.getElementById("ask-btn"),
  chatArea: document.getElementById("chat-area"),
};

// ===================== 유틸 =====================
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** 검색어 토큰이 등장하는 부분을 <mark>로 감싸 하이라이트 처리 */
function highlight(text, query) {
  const safe = escapeHtml(text || "");
  const terms = (query || "")
    .split(/\s+/).map((t) => t.trim()).filter((t) => t.length >= 1)
    .sort((a, b) => b.length - a.length);
  if (terms.length === 0) return safe;
  const escaped = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const re = new RegExp("(" + escaped.join("|") + ")", "gi");
  return safe.replace(re, "<mark>$1</mark>");
}

function badgeForSource(source) {
  return source === "대학" ? "src-univ" : "src-foundation";
}

async function apiGet(path, params) {
  const url = new URL(API_BASE + path, window.location.href);
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    if (Array.isArray(v)) v.forEach((item) => url.searchParams.append(k, item));
    else url.searchParams.append(k, v);
  });
  const res = await fetch(url.toString());
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `요청 실패 (${res.status})`);
  }
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    throw new Error(errBody.detail || `요청 실패 (${res.status})`);
  }
  return res.json();
}

// ===================== 모드 전환 (검색 ↔ AI에게 질문하기) =====================
function setMode(mode) {
  state.mode = mode;
  if (el.modeTabs) {
    el.modeTabs.querySelectorAll(".mode-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mode === mode);
    });
  }
  document.querySelectorAll("[data-mode-panel]").forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.modePanel !== mode);
  });
  if (mode === "ask" && el.askInput) el.askInput.focus();
  else if (el.input) el.input.focus();
}

// 캐시된 옛 버전의 index.html이 로드되어 모드 전환 요소가 없는 경우에도
// 아래 코드에서 예외가 나 검색 기능 전체가 멈추지 않도록 방어한다.
if (el.modeTabs) {
  el.modeTabs.querySelectorAll(".mode-tab").forEach((btn) => {
    btn.addEventListener("click", () => setMode(btn.dataset.mode));
  });
} else {
  console.warn("[app.js] #mode-tabs 요소를 찾을 수 없습니다. 브라우저 캐시를 새로고침(Ctrl+F5)해보세요.");
}

// ===================== 필터 초기화 =====================
// [T17] 카테고리는 출처별로 체계가 다르다 (대학: 학칙/규정/지침, 산학협력단: 제1편~제7편).
// 한 줄에 섞어 놓으면 뭐가 뭔지 알기 어려워, 출처별 소그룹으로 나눠 라벨을 붙이고
// 출처를 고르면 그 출처의 카테고리만 보이게 연동한다.
let categoriesBySource = {};   // {"대학": [...], "산학협력단": [...]}

// 산학협력단 카테고리("제3편 연구비 및 사업비 관리")는 칩에 넣기엔 길어 짧은 별칭을 보여준다.
// (필터 값 자체는 원래 이름을 그대로 사용, 마우스를 올리면 원래 이름이 표시됨)
function categoryChipLabel(cat) {
  const m = cat.match(/^(제\s*\d+\s*편)\s*(.*)$/);
  if (!m) return cat;
  const rest = m[2].replace(/\s+/g, " ").replace(/ 및 /g, "·").replace(/기 타/, "기타").trim();
  return `${m[1].replace(/\s+/g, "")} ${rest}`;
}

function renderCategoryChips() {
  const groups = state.source
    ? [[state.source, categoriesBySource[state.source] || []]]
    : Object.entries(categoriesBySource);
  // 현재 선택된 카테고리가 새 출처에 없으면 "전체"로 되돌린다
  const visible = new Set(groups.flatMap(([, cats]) => cats));
  if (state.category && !visible.has(state.category)) state.category = "";

  const allChip = `<button type="button" class="chip ${state.category ? "" : "active"}" data-value="">전체</button>`;
  const groupHtml = groups.map(([src, cats]) => {
    const cls = src === "대학" ? "univ" : "foundation";
    const label = groups.length > 1 ? `<span class="chip-subgroup-label ${cls}">${escapeHtml(src)}</span>` : "";
    const chips = cats.map((c) =>
      `<button type="button" class="chip ${state.category === c ? "active" : ""}" data-value="${escapeHtml(c)}" title="${escapeHtml(c)}">${escapeHtml(categoryChipLabel(c))}</button>`
    ).join("");
    return `<div class="chip-subgroup">${label}${chips}</div>`;
  }).join("");
  el.categoryFilters.innerHTML = allChip + groupHtml;
  bindChipGroup(el.categoryFilters, "category");
}

function renderFooterData(data) {
  const box = document.getElementById("footer-data");
  if (!box) return;
  const parts = [];
  if (data.data_date) parts.push(`데이터 기준일 <b>${escapeHtml(data.data_date)}</b>`);
  if (data.total_regulations) parts.push(`수록 규정 <b>${Number(data.total_regulations).toLocaleString()}</b>건`);
  parts.push("원문 출처: 국가법령정보센터(law.go.kr) · 경상국립대학교 홈페이지 · 산학협력단 규정집");
  box.innerHTML = parts.join(" · ");
  if (typeof syncFooterHeight === "function") syncFooterHeight();  // [T31] 푸터 내용이 채워진 뒤 높이 재측정
}

async function loadFilters() {
  try {
    const data = await apiGet("/api/filters");
    categoriesBySource = data.categories_by_source || { "": data.categories || [] };
    renderCategoryChips();
    renderFooterData(data);
    // [T30] AI 탭 노출 스위치: 서버가 꺼두면 탭 자체를 숨기고 검색 모드로 고정 (기능·API는 그대로)
    state.aiEnabled = data.ai_tab_enabled !== false;
    if (!state.aiEnabled) {
      if (el.modeTabs) el.modeTabs.classList.add("hidden");
      setMode("search");
    }
  } catch (e) {
    console.warn("필터 목록을 불러오지 못했습니다:", e);
  }
}

function bindChipGroup(container, stateKey) {
  container.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      container.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      state[stateKey] = chip.dataset.value;
      // 출처가 바뀌면 그 출처에 맞는 카테고리만 다시 그린다
      if (stateKey === "source") renderCategoryChips();
      if (state.mode === "search" && state.lastQuery) runSearch(state.lastQuery);
    });
  });
}
bindChipGroup(el.sourceFilters, "source");

// [T31] 푸터는 하단 고정(헤더는 스크롤). 푸터 실제 높이를 측정해 body 하단 여백(--footer-h)에 반영해
// 마지막 결과 카드가 푸터 뒤에 가리지 않게 한다 (푸터 데이터 채워진 뒤·창 크기 변경 시 재측정).
function syncFooterHeight() {
  const f = document.querySelector("footer.site-footer");
  if (!f) return;
  document.documentElement.style.setProperty("--footer-h", `${Math.ceil(f.getBoundingClientRect().height)}px`);
}
window.addEventListener("resize", syncFooterHeight, { passive: true });
window.addEventListener("load", syncFooterHeight);
if (document.fonts && document.fonts.ready) document.fonts.ready.then(syncFooterHeight);
syncFooterHeight();

// [T28] 페이지 전체 스크롤 + 우하단 TOP 버튼 (300px 넘게 내리면 표시). T21의 고정 헤더/접힘은
// "헤더가 고정되면 결과가 잘 안 보인다"는 피드백으로 제거했다.
const toTopBtn = document.getElementById("to-top");
if (toTopBtn) {
  const updateToTop = () => toTopBtn.classList.toggle("show", window.scrollY > 300);
  window.addEventListener("scroll", updateToTop, { passive: true });
  updateToTop();
  toTopBtn.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
    (state.mode === "ask" ? el.askInput : el.input).focus({ preventScroll: true });
  });
}

// [T20] 폐지 규정 포함 토글
const includeRepealedEl = document.getElementById("include-repealed");
if (includeRepealedEl) {
  includeRepealedEl.addEventListener("change", () => {
    state.includeRepealed = includeRepealedEl.checked;
    if (state.mode === "search" && state.lastQuery) runSearch(state.lastQuery);
  });
}

// [T17] 담당부서·연락처 표기 정규화
// 원천 데이터 형식이 제각각이다: 부서 "교무처>교무과" / "산학연구과" / "대학원>대학원",
// 연락처 "교무처(교무과) 055-772-0101" / "055-772-0211". 화면에서는 항상
// "실무 부서 (상위 조직) · 전화번호(클릭 시 전화)" 형식으로 통일해 보여준다.
function parseDept(department, contact) {
  const contactStr = String(contact || "");
  const phoneMatch = contactStr.match(/\d{2,4}-\d{3,4}-\d{4}/);
  const phone = phoneMatch ? phoneMatch[0] : "";
  const contactDept = contactStr.replace(/\d[\d-]+/g, "").trim();  // "교무처(교무과)" 또는 ""

  let primary = "", parent = "";
  // 1순위: 연락처에 적힌 부서 — 규정 원문 헤더에서 조항별로 수집한 값이라 가장 정확하다.
  //        (목록 페이지의 department는 "관리 부서(총무과)"로 뭉뚱그려진 경우가 있음)
  const m = contactDept.match(/^([^()]+)\(([^()]+)\)$/);   // "교무처(교무과)" → 상위/실무
  if (m) { parent = m[1].trim(); primary = m[2].trim(); }
  else if (contactDept) { primary = contactDept; }
  // 2순위: department 필드 ("교무처>교무과" → 실무 부서=마지막, 상위=그 앞)
  if (!primary) {
    const parts = String(department || "").split(">").map((s) => s.trim()).filter(Boolean);
    primary = parts.length ? parts[parts.length - 1] : "";
    parent = parts.length >= 2 ? parts[parts.length - 2] : "";
  }
  if (parent === primary) parent = "";
  if (!primary) primary = "담당부서 미확인";
  return { primary, parent, phone, raw: contactStr };
}

function formatDeptHtml(department, contact) {
  const d = parseDept(department, contact);
  const html = [`<b>${escapeHtml(d.primary)}</b>`];
  if (d.parent) html.push(`<span class="dept-parent">${escapeHtml(d.parent)}</span>`);
  if (d.phone) html.push(`· <a class="dept-tel" href="tel:${d.phone}">${d.phone}</a>`);
  else if (d.raw) html.push(`· ${escapeHtml(d.raw)}`);
  return html.join(" ");
}

function formatDeptText(department, contact) {
  const d = parseDept(department, contact);
  return `${d.primary}${d.parent ? ` (${d.parent})` : ""}${d.phone ? ` · ${d.phone}` : d.raw ? ` · ${d.raw}` : ""}`;
}

// ===================== 검색 실행 =====================
el.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = el.input.value.trim();
  if (!q) return;
  runSearch(q);
});

// 결과없음 화면의 추천 검색어 클릭
el.statusArea.addEventListener("click", (e) => {
  const chip = e.target.closest(".suggest-chip");
  if (chip) {
    el.input.value = chip.dataset.q;
    runSearch(chip.dataset.q);
  }
});
el.results.addEventListener("click", (e) => {
  const card = e.target.closest(".result-card");
  if (card && !e.target.closest("a") && !e.target.closest(".btn-preview")) {
    openPreview(card.dataset.chunkId, card.dataset.regId);
  }
});

async function runSearch(query) {
  state.lastQuery = query;
  showLoading();
  try {
    const data = await apiGet("/api/search", {
      q: query, top_k: 15,
      source: state.source || undefined,
      category: state.category || undefined,
      include_repealed: state.includeRepealed ? "true" : undefined,
      since: state.recentOnly ? oneYearAgoISO() : undefined,   // [T27]
      sort: state.sort !== "relevance" ? state.sort : undefined, // [T27]
    });
    renderResults(data, query);
  } catch (err) {
    showError(err.message);
  }
}

// ===================== AI에게 질문하기 (RAG, /api/ask) =====================
if (el.askForm) {
  el.askForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = el.askInput.value.trim();
    if (!q) return;
    el.askInput.value = "";
    askQuestion(q);
  });
} else {
  console.warn("[app.js] #ask-form 요소를 찾을 수 없습니다. 브라우저 캐시를 새로고침(Ctrl+F5)해보세요.");
}

async function askQuestion(query) {
  state.lastAskQuery = query;
  el.askInput.disabled = true;
  el.askBtn.disabled = true;

  // 질문+답변을 하나의 묶음(exchange)으로 만들어 채팅 영역 맨 앞에 끼워 넣는다.
  // → 가장 최근 질문·답변이 항상 맨 위에 오고, 이전 대화는 그 아래로 밀려난다.
  const exchange = document.createElement("div");
  exchange.className = "chat-exchange";
  el.chatArea.insertBefore(exchange, el.chatArea.firstChild);

  appendUserMessage(exchange, query);
  const loadingId = appendLoadingMessage(exchange);
  // 새로 추가된(맨 위) 질문 묶음이 화면 맨 위로 오도록 스크롤
  exchange.scrollIntoView({ behavior: "smooth", block: "start" });

  // [T26] 직전 대화(최대 3개)를 함께 보내 "그럼 복학은?" 같은 이어 묻기를 이해하게 한다
  const payload = {
    question: query,
    top_k: 5,
    source: state.source ? [state.source] : undefined,
    category: state.category ? [state.category] : undefined,
    history: state.chatHistory.slice(-3),
  };
  try {
    let data;
    try {
      data = await askStreaming(payload, loadingId);   // [T26] 스트리밍 (첫 글자 1~2초 만에 표시)
    } catch (streamErr) {
      console.warn("[app.js] 스트리밍 실패, 일반 방식으로 재시도:", streamErr.message);
      data = await apiPost("/api/ask", payload);
    }
    replaceLoadingMessage(loadingId, data, query);
    if (data.used_llm) state.chatHistory.push({ question: query, answer: (data.answer || "").slice(0, 400) });
    if (state.chatHistory.length > 6) state.chatHistory.shift();
  } catch (err) {
    replaceLoadingMessageWithError(loadingId, err.message, query);
  } finally {
    el.askInput.disabled = false;
    el.askBtn.disabled = false;
    // focus()의 기본 동작은 입력창이 보이도록 페이지를 다시 스크롤시켜, 방금 새 질문을
    // 맨 위로 스크롤한 것을 되돌려버린다. preventScroll로 스크롤 위치는 그대로 둔다.
    el.askInput.focus({ preventScroll: true });
  }
}

function appendUserMessage(container, text) {
  const div = document.createElement("div");
  div.className = "chat-msg chat-user";
  div.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
  container.appendChild(div);
}

let chatMsgSeq = 0;
function appendLoadingMessage(container) {
  const id = "chat-loading-" + (++chatMsgSeq);
  const div = document.createElement("div");
  div.className = "chat-msg chat-ai";
  div.id = id;
  div.innerHTML = `
    <div class="bubble ai-bubble ai-loading">
      <div class="loading-spinner"></div>
      AI가 규정을 검색하고 답변을 작성하고 있습니다... (최대 1분 정도 걸릴 수 있어요)
    </div>`;
  container.appendChild(div);
  return id;
}

const AI_DISCLAIMER = "⚠️ AI가 규정을 바탕으로 생성한 답변이며, 법적 효력은 원본 규정을 따릅니다.";

// [T26] /api/ask/stream (SSE) 읽기: meta(근거 카드 먼저) → token(글자 단위로 채움) → done(최종본 반환)
async function askStreaming(payload, loadingId) {
  const res = await fetch(API_BASE + "/api/ask/stream", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  if (!res.ok || !res.body) throw new Error(`스트리밍 요청 실패 (${res.status})`);

  const node = document.getElementById(loadingId);
  let streamEl = null, textAcc = "";
  const showStreamBubble = () => {
    if (!node || streamEl) return;
    node.innerHTML = `
      <div class="bubble ai-bubble">
        <div class="ai-answer-text ai-streaming" id="${loadingId}-stream"></div>
        <div class="ai-disclaimer">${AI_DISCLAIMER}</div>
      </div>
      <div class="ask-sources-label ai-streaming-note">근거 조항을 찾았습니다. 답변을 작성하는 중…</div>`;
    streamEl = document.getElementById(`${loadingId}-stream`);
  };

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "", done = null;
  while (true) {
    const { value, done: finished } = await reader.read();
    if (finished) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, idx); buf = buf.slice(idx + 2);
      let event = "message", dataStr = "";
      raw.split("\n").forEach((line) => {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
      });
      if (!dataStr) continue;
      const data = JSON.parse(dataStr);
      if (event === "meta") {
        if (data.found) showStreamBubble();
      } else if (event === "token") {
        showStreamBubble();
        textAcc += data.text;
        if (streamEl) streamEl.innerHTML = escapeHtml(textAcc).replace(/\n/g, "<br>") + `<span class="stream-cursor">▍</span>`;
      } else if (event === "done") {
        done = data;
      } else if (event === "error") {
        throw new Error(data.message || "스트리밍 오류");
      }
    }
  }
  if (!done) throw new Error("응답이 완료되지 않았습니다.");
  return done;
}

function replaceLoadingMessage(id, data, query) {
  const node = document.getElementById(id);
  if (!node) return;

  const answerHtml = escapeHtml(data.answer || "").replace(/\n/g, "<br>");
  let sourcesHtml = "";
  if (data.found && data.results && data.results.length) {
    sourcesHtml = `
      <div class="ask-sources-label">근거로 사용한 조항 (${data.results.length}건)</div>
      <div class="ask-sources">
        ${data.results.map((r) => resultCardHtml(r, query)).join("")}
      </div>`;
  }

  let fallbackHtml = "";
  if (!data.found) {
    const suggestChips = (data.suggestions || [])
      .map((s) => `<button type="button" class="suggest-chip ask-suggest-chip" data-q="${escapeHtml(s)}">${escapeHtml(s)}</button>`)
      .join("");
    fallbackHtml = `
      <div class="ask-fallback">
        <div>규정에서 관련 내용을 찾지 못했습니다. 아래 추천 검색어를 눌러보시거나 일반 검색으로 다시 찾아보세요.</div>
        <div class="suggest-list">
          ${suggestChips}
          <button type="button" class="btn-switch-search" data-q="${escapeHtml(query)}">일반 검색으로 전환</button>
        </div>
      </div>`;
  }

  // [T25] 👍/👎 피드백 (답변이 있을 때만) + 이어서 물어볼 질문 제안
  const chunkIds = (data.results || []).map((r) => r.chunk_id);
  const feedbackHtml = data.used_llm ? `
      <div class="feedback-bar" data-question="${escapeHtml(query)}" data-chunks="${escapeHtml(chunkIds.join(","))}" data-preview="${escapeHtml((data.answer || "").slice(0, 200))}">
        <span>이 답변이 도움이 되었나요?</span>
        <button type="button" class="feedback-btn" data-vote="up" aria-label="도움이 됐어요">👍</button>
        <button type="button" class="feedback-btn" data-vote="down" aria-label="도움이 안 됐어요">👎</button>
      </div>` : "";
  const followupHtml = (data.followups && data.followups.length) ? `
      <div class="followup-list">
        <span class="followup-label">이어서 물어보기</span>
        ${data.followups.map((q) => `<button type="button" class="followup-chip" data-q="${escapeHtml(q)}">${escapeHtml(q)}</button>`).join("")}
      </div>` : "";

  node.innerHTML = `
    <div class="bubble ai-bubble">
      <div class="ai-answer-text">${answerHtml}</div>
      <div class="ai-disclaimer">${AI_DISCLAIMER}</div>
      ${feedbackHtml}
    </div>
    ${sourcesHtml}
    ${followupHtml}
    ${fallbackHtml}`;
}

function replaceLoadingMessageWithError(id, message, query) {
  const node = document.getElementById(id);
  if (!node) return;
  node.innerHTML = `
    <div class="bubble ai-bubble ai-error">
      <div>⚠️ 답변 생성 중 문제가 발생했습니다: ${escapeHtml(message)}</div>
      <div class="suggest-list">
        <button type="button" class="btn-switch-search" data-q="${escapeHtml(query)}">일반 검색으로 전환</button>
      </div>
    </div>`;
}

// 채팅 영역 클릭: 근거 카드 미리보기 / 추천 검색어 / 일반 검색 전환 버튼 / [T25] 피드백 · 후속 질문
el.chatArea && el.chatArea.addEventListener("click", async (e) => {
  const fbBtn = e.target.closest(".feedback-btn");
  if (fbBtn) {
    const bar = fbBtn.closest(".feedback-bar");
    const vote = fbBtn.dataset.vote;
    bar.querySelectorAll(".feedback-btn").forEach((b) => (b.disabled = true));
    try {
      await apiPost("/api/feedback", {
        question: bar.dataset.question, vote,
        answer_preview: bar.dataset.preview,
        chunk_ids: (bar.dataset.chunks || "").split(",").filter(Boolean),
      });
      bar.innerHTML = vote === "up"
        ? `<span class="feedback-thanks">👍 감사합니다. 의견이 반영됩니다.</span>`
        : `<span class="feedback-thanks">👎 의견 감사합니다. 담당자가 답변 품질을 점검합니다. 원문은 아래 근거 조항에서 확인하세요.</span>`;
    } catch (_) {
      bar.innerHTML = `<span class="feedback-thanks">피드백 저장에 실패했습니다. 잠시 후 다시 시도해주세요.</span>`;
    }
    return;
  }
  const fuChip = e.target.closest(".followup-chip");
  if (fuChip) {
    el.askInput.value = "";
    askQuestion(fuChip.dataset.q);
    return;
  }
  const switchBtn = e.target.closest(".btn-switch-search");
  if (switchBtn) {
    const q = switchBtn.dataset.q || state.lastAskQuery || "";
    setMode("search");
    if (q) {
      el.input.value = q;
      runSearch(q);
    }
    return;
  }
  const suggestChip = e.target.closest(".ask-suggest-chip");
  if (suggestChip) {
    setMode("search");
    el.input.value = suggestChip.dataset.q;
    runSearch(suggestChip.dataset.q);
    return;
  }
  const previewBtn = e.target.closest(".btn-preview");
  if (previewBtn) {
    const card = previewBtn.closest(".result-card");
    openPreview(card.dataset.chunkId, card.dataset.regId);
    return;
  }
  const card = e.target.closest(".result-card");
  if (card && !e.target.closest("a")) {
    openPreview(card.dataset.chunkId, card.dataset.regId);
  }
});

// ===================== 화면 렌더링 =====================
function showLoading() {
  el.statusArea.innerHTML = `
    <div class="loading-wrap">
      <div class="loading-spinner"></div>
      검색 중입니다...
    </div>`;
  el.results.innerHTML = "";
}

function showError(message) {
  el.statusArea.innerHTML = "";
  el.results.innerHTML = `
    <div class="empty-state">
      <div class="empty-icon">⚠️</div>
      <div class="empty-title">검색 중 문제가 발생했습니다</div>
      <div>${escapeHtml(message)}</div>
    </div>`;
}

const SUGGESTIONS = ["연구비", "휴학", "장학금", "등록금", "연구윤리", "수강신청"];

function renderResults(data, query) {
  if (data.total === 0) {
    el.statusArea.innerHTML = `<div class="status-summary">'<b>${escapeHtml(query)}</b>'에 대한 검색 결과가 없습니다.</div>`;
    el.results.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <div class="empty-title">검색 결과가 없습니다</div>
        <div>다른 검색어를 사용해보시거나 아래 추천 검색어를 참고해보세요.</div>
        <div class="suggest-list">
          ${SUGGESTIONS.map((s) => `<button type="button" class="suggest-chip" data-q="${s}">${s}</button>`).join("")}
        </div>
        <div class="empty-contact">
          찾는 규정이 없다면 원문 담당 부서에 문의해주세요 —
          대학 규정: 총무과 <a href="tel:055-772-0334">055-772-0334</a> ·
          산학협력단 규정: 산학연구과 <a href="tel:055-772-0211">055-772-0211</a><br>
          <a href="https://www.gnu.ac.kr/main/cm/cntnts/cntntsView.do?mi=1255&cntntsId=1214" target="_blank" rel="noopener">경상국립대학교 학칙/규정/지침 원문 페이지 ↗</a>
        </div>
      </div>`;
    return;
  }

  // [T29] 모바일에서는 연관 규정을 3개만 보여주고 "외 N개"로 축약 (긴 글 덩어리 방지). 규정명의
  //       '경상국립대학교' 접두어도 줄여 한 줄에 더 많이 들어가게 한다. 전체 목록은 title로 제공.
  const isMobile = window.matchMedia("(max-width: 600px)").matches;
  const rel = data.related_regulations;
  const shown = isMobile ? rel.slice(0, 3) : rel;
  const short = (n) => isMobile ? n.replace(/^경상국립대학교\s*/, "") : n;
  const more = rel.length - shown.length;
  el.statusArea.innerHTML = `
    <div class="status-summary" title="${escapeHtml(rel.join(", "))}">
      '<b>${escapeHtml(query)}</b>' 검색 결과 <b>${data.total}</b>건
      (${data.took_ms}ms) · 연관 규정
      <b>${rel.length}</b>개: ${escapeHtml(shown.map(short).join(", "))}${more > 0 ? ` <span class="status-more">외 ${more}개</span>` : ""}
    </div>`;

  el.results.innerHTML = data.results.map((r) => resultCardHtml(r, query)).join("");
  // [T28] 새 검색 결과는 결과 요약 줄이 화면 위쪽에 오도록 페이지를 스크롤한다
  // (검색창이 화면 밖으로 밀려 있어도 결과부터 바로 보이게. 맨 위로는 TOP 버튼)
  const top = el.statusArea.getBoundingClientRect().top + window.scrollY - 12;
  if (window.scrollY > top) window.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
}

function resultCardHtml(r, query) {
  const badgeCls = badgeForSource(r.source);
  const locWithTitle = r.location + (r.article_title ? `(${r.article_title})` : "");
  // [T20] 폐지 규정 배지 + 시행일(개정 종류) 표시
  const repealed = r.status === "폐지";
  const statusBadge = repealed ? `<span class="badge repealed" title="폐지된 규정입니다. 참고용으로만 보세요.">폐지</span>` : "";
  // [T24] 대학·산학협력단 양쪽에 같은 규정이 있으면 하나로 합쳐 보여주고 공통 배지를 붙인다
  const SOURCE_ORDER = ["대학", "산학협력단"];
  const sharedList = (r.also_sources && r.also_sources.length)
    ? [...new Set([r.source, ...r.also_sources])].sort((a, b) => SOURCE_ORDER.indexOf(a) - SOURCE_ORDER.indexOf(b))
    : [];
  const sharedBadge = sharedList.length
    ? `<span class="badge shared" title="${escapeHtml(sharedList.join(' · '))} 규정집에 모두 수록된 규정입니다 (같은 조문은 하나로 합쳐 표시)">${escapeHtml(sharedList.join('·'))} 공통</span>`
    : "";
  const dateText = r.enforce_date
    ? `시행 ${escapeHtml(r.enforce_date)}${r.revision_type ? ` · ${escapeHtml(r.revision_type)}` : ""}`
    : "";
  return `
    <article class="result-card ${repealed ? "repealed" : ""}" data-chunk-id="${escapeHtml(r.chunk_id)}" data-reg-id="${escapeHtml(r.reg_id)}"
             tabindex="0" role="button" aria-label="${escapeHtml(r.name)} ${escapeHtml(locWithTitle)} 미리보기">
      <div class="card-top">
        <span class="badge ${badgeCls}">${escapeHtml(r.source)}</span>
        <span class="badge category">${escapeHtml(r.category)}</span>
        ${statusBadge}${sharedBadge}
        <span class="card-location">${escapeHtml(locWithTitle)}</span>
        ${dateText ? `<span class="card-date">${dateText}</span>` : ""}
      </div>
      <div class="card-name">${highlight(r.name, query)}</div>
      <div class="card-snippet">${highlight(r.snippet, query)}</div>
      <div class="card-bottom">
        <div class="card-dept">담당부서: ${formatDeptHtml(r.department, r.contact)}</div>
        <div class="card-actions">
          <button type="button" class="btn-preview">미리보기</button>
          <a href="${escapeHtml(r.source_url)}" target="_blank" rel="noopener">관련 사이트로 이동 ↗</a>
        </div>
      </div>
    </article>`;
}

// ===================== 미리보기 모달 =====================
let modalState = { chunkId: null, regId: null, mode: "article" };

async function openPreview(chunkId, regId) {
  modalState = { chunkId, regId, mode: "article" };
  el.modalOverlay.classList.remove("hidden");
  setTab("article");
  el.modalBody.innerHTML = `<div class="loading-spinner"></div>`;
  await loadModalContent();
}

function setTab(mode) {
  modalState.mode = mode;
  el.tabArticle.classList.toggle("active", mode === "article");
  el.tabFull.classList.toggle("active", mode === "full");
}

el.tabArticle.addEventListener("click", async () => {
  setTab("article");
  el.modalBody.innerHTML = `<div class="loading-spinner"></div>`;
  await loadModalContent();
});
el.tabFull.addEventListener("click", async () => {
  setTab("full");
  el.modalBody.innerHTML = `<div class="loading-spinner"></div>`;
  await loadModalContent();
});

async function loadModalContent() {
  try {
    if (modalState.mode === "article") {
      const c = await apiGet(`/api/chunks/${encodeURIComponent(modalState.chunkId)}`);
      el.modalBadge.textContent = c.source;
      el.modalBadge.className = "badge " + badgeForSource(c.source);
      el.modalTitle.textContent = c.name;
      el.modalMeta.textContent =
        `${c.category}${c.status === "폐지" ? " · ⚠️ 폐지된 규정" : ""}${c.enforce_date ? ` · 시행 ${c.enforce_date}` : ""} · ${c.location}${c.article_title ? "(" + c.article_title + ")" : ""} · 담당부서: ${formatDeptText(c.department, c.contact)}`;
      el.modalBody.textContent = c.text;
      el.modalSiteLink.href = c.source_url;
    } else {
      const r = await apiGet(`/api/regulations/${encodeURIComponent(modalState.regId)}`);
      el.modalBadge.textContent = r.source;
      el.modalBadge.className = "badge " + badgeForSource(r.source);
      el.modalTitle.textContent = r.name;
      el.modalMeta.textContent = `${r.category}${r.status === "폐지" ? " · ⚠️ 폐지된 규정" : ""}${r.enforce_date ? ` · 시행 ${r.enforce_date}${r.revision_type ? "(" + r.revision_type + ")" : ""}` : ""}${r.rule_no ? ` · ${r.rule_no}` : ""} · 담당부서: ${formatDeptText(r.department, r.contact)}`;
      el.modalSiteLink.href = r.source_url;
      // [T25] 규정 전문에서 "지금 보고 있던 조항"을 하이라이트하고 그 위치로 자동 스크롤한다.
      // (AI 답변의 근거 조항을 전문 안에서 바로 확인할 수 있게 — 이전엔 전문을 직접 뒤져야 했다)
      renderFullTextWithHighlight(r.full_text, modalState.chunkId);
    }
  } catch (err) {
    el.modalBody.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div>${escapeHtml(err.message)}</div>`;
  }
}

// [T25] 전문 텍스트 안에서 해당 조항 구간을 찾아 <mark>로 감싸고 스크롤한다.
// 조항 구간 = 청크의 article 라벨("제31조")이 줄 첫머리에 나오는 곳부터 다음 "제N조"(또는 부칙/별표) 직전까지.
async function renderFullTextWithHighlight(fullText, chunkId) {
  let article = "", clauseText = "";
  try {
    if (chunkId) {
      const c = await apiGet(`/api/chunks/${encodeURIComponent(chunkId)}`);
      article = (c.article || "").trim();
      clauseText = (c.text || "").trim();
    }
  } catch (_) { /* 하이라이트는 부가 기능 — 실패해도 전문은 그대로 보여준다 */ }

  let start = -1, end = -1;
  if (article && /^제\s*\d+조/.test(article)) {
    const artNum = article.replace(/\s+/g, "");
    // 줄 시작의 "제31조(" 또는 "제31조 " (제31조의2 같은 변형은 문자열 일치로 처리)
    const re = new RegExp("(^|\\n)\\s*" + artNum.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "(?![\\d의])", "g");
    const m = re.exec(fullText);
    if (m) {
      start = m.index + m[1].length;
      const nextRe = /\n\s*(제\s*\d+조|부\s*칙|별\s*표|별\s*지)/g;
      nextRe.lastIndex = start + artNum.length;
      const n = nextRe.exec(fullText);
      end = n ? n.index : fullText.length;
    }
  }
  if (start < 0 && clauseText) {
    // 조항 라벨로 못 찾으면 청크 본문 앞 40자로 위치를 찾는다 (별표·부칙 등)
    const probe = clauseText.slice(0, 40);
    const idx = fullText.indexOf(probe);
    if (idx >= 0) { start = idx; end = Math.min(fullText.length, idx + clauseText.length); }
  }

  if (start < 0) {
    el.modalBody.textContent = fullText;
    return;
  }
  el.modalBody.innerHTML =
    escapeHtml(fullText.slice(0, start)) +
    `<mark class="modal-target" id="modal-target">${escapeHtml(fullText.slice(start, end))}</mark>` +
    escapeHtml(fullText.slice(end));
  const target = document.getElementById("modal-target");
  if (target) requestAnimationFrame(() => target.scrollIntoView({ block: "start", behavior: "smooth" }));
}

function closeModal() {
  el.modalOverlay.classList.add("hidden");
}
el.modalClose.addEventListener("click", closeModal);
el.modalOverlay.addEventListener("click", (e) => {
  if (e.target === el.modalOverlay) closeModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeModal();
});

// 카드 안의 "미리보기" 버튼 클릭 (버블링으로 카드 클릭과 겹치지 않게 별도 처리)
el.results.addEventListener("click", (e) => {
  const btn = e.target.closest(".btn-preview");
  if (btn) {
    const card = btn.closest(".result-card");
    openPreview(card.dataset.chunkId, card.dataset.regId);
  }
});

// ===================== [T23] 딥링크: 검색 조건을 URL에 반영 / URL에서 복원 =====================
// 예) /regulation/?q=휴학&source=대학&category=규정&repealed=1&mode=ask
// 결과를 링크로 공유·북마크할 수 있고, 브라우저 뒤로가기/앞으로가기가 검색 이력을 따라간다.
let _restoringFromUrl = false;

function syncUrlFromState(query, push) {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (state.source) params.set("source", state.source);
  if (state.category) params.set("category", state.category);
  if (state.includeRepealed) params.set("repealed", "1");
  if (state.recentOnly) params.set("recent", "1");           // [T27]
  if (state.sort && state.sort !== "relevance") params.set("sort", state.sort); // [T27]
  if (state.mode === "ask") params.set("mode", "ask");
  const qs = params.toString();
  const url = window.location.pathname + (qs ? "?" + qs : "");
  if (url === window.location.pathname + window.location.search) return;
  if (push) history.pushState({ q: query }, "", url); else history.replaceState({ q: query }, "", url);
}

function applyStateFromUrl() {
  const p = new URLSearchParams(window.location.search);
  const q = (p.get("q") || "").trim();
  state.source = p.get("source") || "";
  state.category = p.get("category") || "";
  state.includeRepealed = p.get("repealed") === "1";
  state.recentOnly = p.get("recent") === "1";                                  // [T27]
  state.sort = p.get("sort") === "date" ? "date" : "relevance";               // [T27]
  // 칩·토글 표시를 상태에 맞춰 갱신
  el.sourceFilters.querySelectorAll(".chip").forEach((c) => c.classList.toggle("active", c.dataset.value === state.source));
  renderCategoryChips();
  if (includeRepealedEl) includeRepealedEl.checked = state.includeRepealed;
  const recentEl = document.getElementById("recent-only"); if (recentEl) recentEl.checked = state.recentOnly;
  const sortEl = document.getElementById("sort-select"); if (sortEl) sortEl.value = state.sort;
  setMode(p.get("mode") === "ask" && state.aiEnabled ? "ask" : "search");  // [T30] 탭이 꺼져 있으면 검색 고정
  if (q) {
    el.input.value = q;
    _restoringFromUrl = true;
    runSearch(q).finally(() => { _restoringFromUrl = false; });
  }
}

window.addEventListener("popstate", () => applyStateFromUrl());

// runSearch가 끝날 때 URL을 갱신한다 (URL에서 복원 중일 때는 다시 쓰지 않음)
const _origRunSearch = runSearch;
runSearch = async function (query) {  // eslint-disable-line no-func-assign
  await _origRunSearch(query);
  if (!_restoringFromUrl) syncUrlFromState(query, true);
};

// ===================== [T27] 정렬·기간 필터 · 키보드 단축키 · 인쇄 · 접근성 =====================
const sortSelectEl = document.getElementById("sort-select");
if (sortSelectEl) {
  sortSelectEl.addEventListener("change", () => {
    state.sort = sortSelectEl.value === "date" ? "date" : "relevance";
    if (state.mode === "search" && state.lastQuery) runSearch(state.lastQuery);
  });
}
const recentOnlyEl = document.getElementById("recent-only");
if (recentOnlyEl) {
  recentOnlyEl.addEventListener("change", () => {
    state.recentOnly = recentOnlyEl.checked;
    if (state.mode === "search" && state.lastQuery) runSearch(state.lastQuery);
  });
}

// 키보드: "/" → 현재 탭의 입력창 포커스, ↑↓ → 결과 카드 이동, Enter/Space → 카드 미리보기
document.addEventListener("keydown", (e) => {
  const tag = (e.target.tagName || "").toLowerCase();
  const typing = tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable;
  if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) {
    e.preventDefault();
    (state.mode === "ask" ? el.askInput : el.input).focus();
    return;
  }
  const card = e.target.closest && e.target.closest(".result-card");
  if (!card) return;
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    openPreview(card.dataset.chunkId, card.dataset.regId);
  } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    const cards = [...card.parentElement.querySelectorAll(".result-card")];
    const i = cards.indexOf(card);
    const next = cards[i + (e.key === "ArrowDown" ? 1 : -1)];
    if (next) { e.preventDefault(); next.focus({ preventScroll: false }); next.scrollIntoView({ block: "nearest" }); }
  }
});

// 인쇄: 모달이 열려 있을 때는 모달 내용만 인쇄 (print CSS가 나머지를 숨김)
const modalPrintBtn = document.getElementById("modal-print");
if (modalPrintBtn) modalPrintBtn.addEventListener("click", () => window.print());
// 모달 열림 상태를 body 클래스로 노출 (print CSS · 배경 스크롤 제어용)
const _modalObserver = new MutationObserver(() => {
  document.body.classList.toggle("modal-open", !el.modalOverlay.classList.contains("hidden"));
});
_modalObserver.observe(el.modalOverlay, { attributes: true, attributeFilter: ["class"] });

// ===================== [T25] 첫 화면: 많이 찾는 검색어 =====================
// 검색 전 빈 결과 영역에 로그 기반 인기 검색어 칩을 보여준다 (클릭 → 바로 검색).
async function renderPopular() {
  if (state.lastQuery || (window.location.search && new URLSearchParams(window.location.search).get("q"))) return;
  try {
    const data = await apiGet("/api/popular", { limit: 8 });
    if (!data.queries || !data.queries.length || state.lastQuery) return;
    el.statusArea.innerHTML = `
      <div class="popular-box">
        <div class="popular-label">🔥 많이 찾는 검색어</div>
        <div class="suggest-list">
          ${data.queries.map((q) => `<button type="button" class="suggest-chip" data-q="${escapeHtml(q)}">${escapeHtml(q)}</button>`).join("")}
        </div>
      </div>`;
  } catch (_) { /* 부가 기능 — 실패해도 조용히 넘어간다 */ }
}

// ===================== 초기화 =====================
loadFilters().then(() => {
  // 카테고리 칩이 채워진 뒤에 URL 상태를 반영해야 칩 선택 표시가 맞는다
  if (window.location.search) applyStateFromUrl();
  renderPopular();
});
el.input.focus();
