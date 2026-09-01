// ===================== 설정 =====================
// API 서버가 이 정적 파일을 함께 서빙하므로 같은 오리진(빈 문자열)을 기본값으로 사용.
// 파일을 다른 서버(예: 5500 포트)로 따로 열었을 때는 아래 값을 API 서버 주소로 바꿔주세요.
const API_BASE = "";

const state = {
  source: "",     // "" | "대학" | "산학협력단"
  category: "",   // "" | "학칙" | "규정" | ...
  lastQuery: "",
};

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

// ===================== 필터 초기화 =====================
async function loadFilters() {
  try {
    const data = await apiGet("/api/filters");
    el.categoryFilters.innerHTML =
      `<button type="button" class="chip active" data-value="">전체</button>` +
      data.categories.map((c) =>
        `<button type="button" class="chip" data-value="${escapeHtml(c)}">${escapeHtml(c)}</button>`
      ).join("");
    bindChipGroup(el.categoryFilters, "category");
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
      if (state.lastQuery) runSearch(state.lastQuery);
    });
  });
}
bindChipGroup(el.sourceFilters, "source");

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
    });
    renderResults(data, query);
  } catch (err) {
    showError(err.message);
  }
}

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
      </div>`;
    return;
  }

  el.statusArea.innerHTML = `
    <div class="status-summary">
      '<b>${escapeHtml(query)}</b>' 검색 결과 <b>${data.total}</b>건
      (${data.took_ms}ms) · 연관 규정
      <b>${data.related_regulations.length}</b>개: ${escapeHtml(data.related_regulations.join(", "))}
    </div>`;

  el.results.innerHTML = data.results.map((r) => resultCardHtml(r, query)).join("");
}

function resultCardHtml(r, query) {
  const badgeCls = badgeForSource(r.source);
  const locWithTitle = r.location + (r.article_title ? `(${r.article_title})` : "");
  return `
    <article class="result-card" data-chunk-id="${escapeHtml(r.chunk_id)}" data-reg-id="${escapeHtml(r.reg_id)}">
      <div class="card-top">
        <span class="badge ${badgeCls}">${escapeHtml(r.source)}</span>
        <span class="badge category">${escapeHtml(r.category)}</span>
        <span class="card-location">${escapeHtml(locWithTitle)}</span>
      </div>
      <div class="card-name">${highlight(r.name, query)}</div>
      <div class="card-snippet">${highlight(r.snippet, query)}</div>
      <div class="card-bottom">
        <div class="card-dept">담당부서: <b>${escapeHtml(r.department)}</b> (${escapeHtml(r.contact)})</div>
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
        `${c.category} · ${c.location}${c.article_title ? "(" + c.article_title + ")" : ""} · 담당부서: ${c.department} (${c.contact})`;
      el.modalBody.textContent = c.text;
      el.modalSiteLink.href = c.source_url;
    } else {
      const r = await apiGet(`/api/regulations/${encodeURIComponent(modalState.regId)}`);
      el.modalBadge.textContent = r.source;
      el.modalBadge.className = "badge " + badgeForSource(r.source);
      el.modalTitle.textContent = r.name;
      el.modalMeta.textContent = `${r.category} · 담당부서: ${r.department} (${r.contact})`;
      el.modalBody.textContent = r.full_text;
      el.modalSiteLink.href = r.source_url;
    }
  } catch (err) {
    el.modalBody.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div>${escapeHtml(err.message)}</div>`;
  }
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

// ===================== 초기화 =====================
loadFilters();
el.input.focus();
