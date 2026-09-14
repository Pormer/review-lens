"use strict";
const $ = (q, root = document) => root.querySelector(q);
const $$ = (q, root = document) => [...root.querySelectorAll(q)];
const escapeHTML = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const safeURL = (value) => {
  try {
    const u = new URL(value);
    return ["https:", "http:"].includes(u.protocol) ? escapeHTML(u.href) : "#";
  } catch {
    return "#";
  }
};
const readStorage = (storage, key, fallback) => {
  try {
    return JSON.parse(storage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
};
let config = null,
  reportJob = null,
  pollTimer = null,
  pollGeneration = 0,
  toastTimer = null;
let history = readStorage(localStorage, "reviewlens-history", []);
if (!Array.isArray(history)) history = [];
history = history
  .filter((x) => x && typeof x.id === "string" && /^[a-f0-9-]{36}$/.test(x.id))
  .slice(0, 30);
let accessKey = readStorage(sessionStorage, "reviewlens-key", "");
let historyBusy = false;
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("#toast").hidden = true), 9000);
}
function saveHistory() {
  try {
    localStorage.setItem(
      "reviewlens-history",
      JSON.stringify(history.slice(0, 30)),
    );
  } catch {
    /* Private browsing may disable persistence. */
  }
  $("#history-count").textContent = history.length;
}
function remember(job) {
  history = [
    {
      id: job.id,
      name: job.request.product_name,
      mode: job.request.mode,
      date: job.created_at,
      status: job.status,
    },
    ...history.filter((x) => x.id !== job.id),
  ].slice(0, 30);
  saveHistory();
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Access-Key": accessKey,
      ...options.headers,
    },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const message = Array.isArray(data.detail)
      ? data.detail.map((e) => e.msg.replace(/^Value error, /, "")).join(" / ")
      : data.detail;
    if (response.status === 401) openSettings();
    const error = new Error(
      message || "요청에 실패했습니다. 잠시 후 다시 시도해 주세요.",
    );
    error.status = response.status;
    throw error;
  }
  return response;
}
function showView(name, stopPoll = true) {
  if (stopPoll) {
    clearTimeout(pollTimer);
    pollGeneration++;
  }
  for (const view of ["home", "loading", "report", "history", "guide"])
    $(`#${view}-view`).hidden = view !== name;
  const active =
    name === "history"
      ? "nav-history"
      : name === "guide"
        ? "nav-guide"
        : "nav-new";
  $$(".nav-item").forEach((x) => x.classList.toggle("active", x.id === active));
  $("#breadcrumb").textContent = {
    home: "새 상품 분석",
    loading: "분석 진행 중",
    report: "분석 리포트",
    history: "내 분석 기록",
    guide: "분석 가이드",
  }[name];
  if (name !== "report")
    window.history.replaceState(null, "", location.pathname);
  window.scrollTo({ top: 0 });
}
function openSettings() {
  $("#access-key").value = accessKey;
  if (!$("#settings-dialog").open) $("#settings-dialog").showModal();
}
$("#open-settings").addEventListener("click", openSettings);
$("#mobile-settings").addEventListener("click", openSettings);
$("#close-settings").addEventListener("click", () =>
  $("#settings-dialog").close(),
);
$("#settings-form").addEventListener("submit", (e) => {
  e.preventDefault();
  accessKey = $("#access-key").value.trim();
  try {
    sessionStorage.setItem("reviewlens-key", JSON.stringify(accessKey));
  } catch {}
  $("#settings-dialog").close();
  toast("서비스 접근 키를 저장했습니다.");
});
$("#nav-new").addEventListener("click", () => showView("home"));
$("#nav-guide").addEventListener("click", () => showView("guide"));
$("#nav-history").addEventListener("click", showHistory);
$("#loading-home").addEventListener("click", () => showView("home"));
$("#analysis-form").addEventListener("submit", (e) => {
  e.preventDefault();
  startAnalysis("live");
});
$("#demo-button").addEventListener("click", () => startAnalysis("demo"));
async function startAnalysis(mode) {
  if (!config)
    return toast(
      "서버 연결을 확인해 주세요. 페이지를 새로고침하면 다시 연결합니다.",
    );
  if (mode === "live" && !config.live_enabled)
    return toast(
      config.provider === "ollama"
        ? `Ollama를 실행하고 ${config.model} 모델을 설치한 뒤 페이지를 새로고침해 주세요. API 키는 필요 없습니다.`
        : "선택한 OpenAI 연동의 서버 설정을 확인해 주세요.",
    );
  const payload =
    mode === "demo"
      ? { ...config.demo_product, mode }
      : {
          product_name: $("#product-name").value.trim(),
          product_url: $("#product-url").value.trim(),
          mode,
        };
  $("#analyze-button").disabled = $("#demo-button").disabled = true;
  try {
    const created = await (
      await api("/api/analyses", {
        method: "POST",
        body: JSON.stringify(payload),
      })
    ).json();
    remember({
      id: created.id,
      request: payload,
      status: "queued",
      created_at: new Date().toISOString(),
    });
    await loadJob(created.id);
  } catch (e) {
    toast(e.message);
  } finally {
    $("#analyze-button").disabled = $("#demo-button").disabled = false;
  }
}
async function loadJob(id) {
  clearTimeout(pollTimer);
  const generation = ++pollGeneration;
  showView("loading", false);
  $("#loading-product").textContent =
    history.find((x) => x.id === id)?.name || "분석 불러오는 중";
  $("#loading-stage").textContent = "작업 상태 확인 중";
  let failures = 0;
  async function poll() {
    try {
      const job = await (await api(`/api/analyses/${id}`)).json();
      if (generation !== pollGeneration) return;
      failures = 0;
      remember(job);
      if (job.status === "completed") {
        renderReport(job);
        return;
      }
      if (job.status === "failed") {
        showHistory();
        toast(job.error);
        return;
      }
      $("#loading-stage").textContent = job.stage;
      $("#loading-product").textContent = job.request.product_name;
      pollTimer = setTimeout(poll, 1100);
    } catch (e) {
      if (generation !== pollGeneration) return;
      if (++failures < 4 && !e.status) {
        $("#loading-stage").textContent = "연결을 다시 확인하고 있어요";
        pollTimer = setTimeout(poll, 2500);
      } else {
        showView("history");
        renderHistory();
        toast(e.message);
      }
    }
  }
  await poll();
}
const num = (value) => (value == null ? "—" : Number(value).toFixed(2));
function citationButtons(ids) {
  return ids
    .map(
      (id) =>
        `<button class="citation" data-evidence="${escapeHTML(id)}">${escapeHTML(id)} ↗</button>`,
    )
    .join("");
}
function findings(items) {
  return items.length
    ? items
        .map(
          (x) =>
            `<article class="finding"><h3>${escapeHTML(x.title)}</h3><p>${escapeHTML(x.detail)}</p>${citationButtons(x.evidence_ids)}</article>`,
        )
        .join("")
    : '<p class="muted">판단할 수 있는 근거가 부족합니다.</p>';
}
function list(items) {
  return items.length
    ? `<ul>${items.map((x) => `<li>${escapeHTML(x)}</li>`).join("")}</ul>`
    : '<p class="muted">판단을 보류했습니다.</p>';
}
function renderReport(job) {
  reportJob = job;
  showView("report");
  window.history.replaceState(null, "", `#report=${job.id}`);
  const r = job.report,
    n = r.narrative,
    m = r.metrics;
  const specs = r.evidence.filter((x) => x.kind === "spec");
  $("#report-content").innerHTML = `
    <div class="report-heading"><div><div class="eyebrow">YOUR PURCHASE, IN FOCUS</div><h1>${escapeHTML(r.product_name)}</h1><span class="badge ${r.mode === "demo" ? "demo" : ""}">${r.mode === "demo" ? "가상 예제 리포트" : "공개 웹 근거 분석"}</span><span class="muted">${new Date(job.created_at).toLocaleString("ko-KR")}</span></div><div class="report-actions"><button class="secondary-button" id="export-markdown">↓ Markdown</button><button class="secondary-button" id="export-json">↓ JSON</button><button class="secondary-button" id="new-analysis">새 분석 ↗</button></div></div>
    ${r.mode === "demo" ? '<div class="notice">가상의 상품과 후기로 만든 시연용 리포트입니다. 실제 상품의 분석 결과가 아닙니다.</div>' : ""}
    <section class="card summary-card"><div class="eyebrow">✦ REVIEW LENS INSIGHT</div><h2>${escapeHTML(n.headline)}</h2><p>${escapeHTML(n.summary)}</p></section>
    <div class="metrics-grid"><div class="metric"><span>분석에 사용한 근거</span><strong>${m.evidence_count}<small> 건</small></strong><small>개별 리뷰 ${m.review_count} · 사용기 ${m.usage_count}</small></div><div class="metric"><span>근거가 있는 출처</span><strong>${m.source_count}<small> 개</small></strong><small>동일 상품으로 분류된 자료</small></div><div class="metric"><span>비교 표본 평균 별점</span><strong>${num(m.average_rating)}<small> / 5</small></strong><small>별점과 본문이 있는 ${m.paired_count}건</small></div><div class="metric"><span>별점·본문 괴리 비율</span><strong>${m.mismatch_percent == null ? "—" : m.mismatch_percent + "%"}<small></small></strong><small>${escapeHTML(m.sample_label)} · 전체 리뷰 대표값 아님</small></div></div>
    <div class="report-tabs" role="tablist" aria-label="리포트 상세"><button id="tab-button-overview" role="tab" aria-controls="tab-overview" aria-selected="true" data-tab="overview">종합 인사이트</button><button id="tab-button-ratings" role="tab" aria-controls="tab-ratings" aria-selected="false" tabindex="-1" data-tab="ratings">별점과 본문</button><button id="tab-button-evidence" role="tab" aria-controls="tab-evidence" aria-selected="false" tabindex="-1" data-tab="evidence">근거 · 출처 <span class="count">${m.evidence_count}</span></button></div>
    <div id="tab-overview" role="tabpanel" aria-labelledby="tab-button-overview"><div class="findings-grid"><section class="card"><h2 class="positive-title">↗ 이런 점이 좋아요</h2>${findings(n.pros)}</section><section class="card"><h2 class="negative-title">↘ 이런 점은 아쉬워요</h2>${findings(n.cons)}</section></div><section class="card stack-card"><h2>◈ 일상에서의 사용 경험</h2>${findings(n.usage)}</section>${specs.length ? `<section class="card stack-card"><h2>상품 정보</h2>${specs.map((x) => `<article class="finding"><h3>${escapeHTML(x.aspect)}</h3><p>${escapeHTML(x.summary)}</p>${citationButtons([x.id])}</article>`).join("")}</section>` : ""}<section class="card stack-card audience"><div><h3>이런 분께 적합해요</h3>${list(n.suitable_for)}</div><div><h3>구매 전 확인해 보세요</h3>${list(n.consider_before_buying)}</div></section></div>
    <div id="tab-ratings" role="tabpanel" aria-labelledby="tab-button-ratings" hidden><div class="notice">${escapeHTML(m.method)} ${m.paired_count < 10 ? "비교 표본이 10건 미만이므로 해석에 특히 주의해 주세요." : ""}</div><div class="chart-grid"><section class="card"><h2>같은 리뷰, 두 가지 신호</h2><div class="score-compare"><div><strong>${num(m.average_rating)}</strong><span>표본 평균 별점</span></div><span>→</span><div><strong>${num(m.average_text_score)}</strong><span>본문 감성 환산값</span></div></div><p class="muted">두 값 모두 같은 ${m.paired_count}건에서 계산했습니다. 본문 환산값은 모델의 감성 추정치입니다.</p></section><section class="card"><h2>비교 표본의 별점 분포</h2>${[5, 4, 3, 2, 1].map((v) => `<div class="chart-row"><span>${v} ★</span><meter min="0" max="${Math.max(m.paired_count, 1)}" value="${m.rating_distribution[v]}" aria-label="${v}점 ${m.rating_distribution[v]}건"></meter><b>${m.rating_distribution[v]}건</b></div>`).join("")}<small class="muted">소수 별점은 가장 가까운 정수로 집계합니다.</small></section></div><section class="card stack-card"><h2>별점과 내용이 달랐던 후기</h2>${
      m.gaps
        .filter((g) => g.is_mismatch ?? Math.abs(g.gap) >= 1.5)
        .map((g) => {
          const e = r.evidence.find((x) => x.id === g.evidence_id);
          return `<article class="finding"><h3>별점 ${num(g.rating)} · 본문 환산 ${num(g.text_score)}</h3><p>${escapeHTML(e?.summary || "")}</p>${citationButtons([g.evidence_id])}</article>`;
        })
        .join("") ||
      '<p class="muted">표시 기준을 충족한 후기가 없거나 비교 가능한 근거가 부족합니다.</p>'
    }</section></div>
    <div id="tab-evidence" role="tabpanel" aria-labelledby="tab-button-evidence" hidden><div class="evidence-toolbar"><button class="filter-button active" data-filter="all">전체</button><button class="filter-button" data-filter="review">개별 리뷰</button><button class="filter-button" data-filter="usage">사용 경험</button><button class="filter-button" data-filter="spec">상품 정보</button><span class="muted">중복·일치 불명·검증 불가 ${r.excluded_count}건 제외</span></div><div id="evidence-list"></div><section class="card stack-card"><h2>분석에 사용한 출처</h2>${r.sources.map((s) => `<article class="finding"><a class="source-link" target="_blank" rel="noopener noreferrer" href="${safeURL(s.url)}">${escapeHTML(s.id)} · ${escapeHTML(s.title)} ↗</a></article>`).join("") || '<p class="muted">사용할 수 있는 출처가 없습니다.</p>'}</section></div>
    <details class="card limitations" open><summary>분석 범위와 알아둘 점</summary>${list(r.limitations)}</details>`;
  renderEvidence("all");
  $('[data-tab="overview"]').addEventListener("keydown", tabKeydown);
  $('[data-tab="ratings"]').addEventListener("keydown", tabKeydown);
  $('[data-tab="evidence"]').addEventListener("keydown", tabKeydown);
  $$("[data-tab]").forEach((b) =>
    b.addEventListener("click", () => selectTab(b.dataset.tab)),
  );
  $$("[data-filter]").forEach((b) =>
    b.addEventListener("click", () => renderEvidence(b.dataset.filter)),
  );
  $$(".citation").forEach((b) =>
    b.addEventListener("click", () => {
      selectTab("evidence");
      renderEvidence("all");
      document
        .getElementById(`evidence-${b.dataset.evidence}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    }),
  );
  $("#new-analysis").addEventListener("click", () => showView("home"));
  $("#export-markdown").addEventListener("click", async () => {
    try {
      download(
        await (await api(`/api/analyses/${job.id}/markdown`)).blob(),
        "reviewlens-report.md",
      );
    } catch (e) {
      toast(e.message);
    }
  });
  $("#export-json").addEventListener("click", () =>
    download(
      new Blob([JSON.stringify(r, null, 2)], { type: "application/json" }),
      "reviewlens-report.json",
    ),
  );
}
function selectTab(tab) {
  $$("[data-tab]").forEach((b) => {
    const selected = b.dataset.tab === tab;
    b.setAttribute("aria-selected", String(selected));
    b.tabIndex = selected ? 0 : -1;
  });
  $$('[role="tabpanel"]').forEach((p) => (p.hidden = p.id !== `tab-${tab}`));
}
function tabKeydown(event) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const tabs = $$("[data-tab]");
  let index = tabs.indexOf(event.currentTarget);
  index =
    event.key === "Home"
      ? 0
      : event.key === "End"
        ? tabs.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) %
          tabs.length;
  selectTab(tabs[index].dataset.tab);
  tabs[index].focus();
}
function renderEvidence(filter) {
  const r = reportJob.report,
    items = r.evidence.filter((e) => filter === "all" || e.kind === filter);
  $$("[data-filter]").forEach((b) => {
    b.classList.toggle("active", b.dataset.filter === filter);
    b.setAttribute("aria-pressed", String(b.dataset.filter === filter));
  });
  $("#evidence-list").innerHTML =
    items
      .map((e) => {
        const source = r.sources.find((s) => s.id === e.source_id);
        return `<article class="card evidence-card" id="evidence-${escapeHTML(e.id)}"><div class="evidence-top"><span>${escapeHTML(e.id)} · ${{ review: "개별 리뷰", usage: "사용 경험", spec: "상품 정보" }[e.kind]} · ${escapeHTML(e.aspect)}</span><span>${e.rating == null ? "별점 없음" : `★ ${num(e.rating)}`}</span></div><h3>${escapeHTML(e.summary)}</h3><div class="evidence-label">${r.mode === "demo" ? "가상 예제 문장" : r.provider === "ollama" ? "수집 자료 발췌 · 검색 발췌 포함" : "연구 메모 발췌 · 원문 직접 인용 아님"}</div><blockquote>${escapeHTML(e.passage)}</blockquote><p class="muted">${e.verified_purchase ? "출처에 구매 인증 명시 · AI 추출" : "구매 인증 미확인"}${e.published_at ? ` · 게시일 ${escapeHTML(e.published_at)}` : " · 게시일 미확인"}</p>${source ? `<a class="source-link" href="${safeURL(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(source.title)} ↗</a>` : ""}</article>`;
      })
      .join("") || '<div class="empty-state">이 유형의 근거가 없습니다.</div>';
}
function download(blob, filename) {
  const url = URL.createObjectURL(blob),
    a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast("리포트를 내보냈습니다.");
}
function showHistory() {
  showView("history");
  renderHistory();
}
function renderHistory() {
  $("#history-list").innerHTML = history.length
    ? history
        .map(
          (item) =>
            `<article class="card history-row"><div><h3>${escapeHTML(item.name)}</h3><p>${item.mode === "demo" ? "가상 예제" : "공개 웹 분석"} · ${new Date(item.date).toLocaleString("ko-KR")} · ${{ queued: "대기", running: "진행 중", completed: "완료", failed: "실패" }[item.status] || "상태 확인 필요"}</p></div><div class="history-buttons"><button class="secondary-button" data-open="${item.id}">리포트 열기 ↗</button><button class="secondary-button" data-delete="${item.id}" aria-label="${escapeHTML(item.name)} 리포트 삭제">삭제</button></div></article>`,
        )
        .join("")
    : '<div class="empty-state"><span>▤</span>아직 분석 기록이 없어요.<br>새 상품을 분석하거나 예제 리포트를 체험해 보세요.</div>';
  $$("[data-open]").forEach((b) =>
    b.addEventListener("click", () => loadJob(b.dataset.open)),
  );
  $$("[data-delete]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (historyBusy) return;
      historyBusy = true;
      b.disabled = true;
      try {
        await api(`/api/analyses/${b.dataset.delete}`, { method: "DELETE" });
        history = history.filter((x) => x.id !== b.dataset.delete);
        saveHistory();
        renderHistory();
        toast("리포트를 삭제했습니다.");
      } catch (e) {
        if (e.status === 404) {
          history = history.filter((x) => x.id !== b.dataset.delete);
          saveHistory();
          renderHistory();
        } else {
          toast(e.message);
          b.disabled = false;
        }
      } finally {
        historyBusy = false;
      }
    }),
  );
}
async function init() {
  saveHistory();
  try {
    config = await (await api("/api/config")).json();
    $("#server-status").innerHTML =
      `<i></i> ${config.live_enabled ? (config.provider === "ollama" ? "로컬 AI 준비됨" : "OpenAI 연동 준비됨") : "예제 모드 사용 가능"}`;
    $("#live-note").textContent =
      config.provider === "ollama"
        ? config.live_enabled
          ? "로컬 AI와 무료 웹 검색으로 분석합니다. 호출당 API 요금이 없습니다."
          : "Ollama 모델을 준비하면 실제 분석을 사용할 수 있어요. API 키는 필요 없습니다."
        : "OpenAI를 선택한 서버입니다. 실제 분석에는 API 요금이 발생할 수 있어요.";
    $("#retention-note").textContent =
      `상품명·링크·리포트는 서버에 ${config.retention_days}일간 저장됩니다. 기본 로컬 모드는 AI 분석을 PC에서 수행하고 상품명 검색어만 공개 검색 서비스에 전송합니다. OpenAI 모드를 직접 선택한 경우에만 해당 API로 자료를 전송합니다. 개인정보가 포함된 링크는 입력하지 마세요. 분석 기록에서 리포트를 삭제할 수 있습니다.`;
    const match = location.hash.match(/^#report=([a-f0-9-]{36})$/);
    if (match) await loadJob(match[1]);
  } catch (e) {
    $("#server-status").textContent = "서버 연결 확인 필요";
    toast(e.message);
  }
}
init();
