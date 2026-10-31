// 대시보드의 테마 설정 탭. 문서 종류가 맨 위의 구분이고, 종류마다 축 값의 조합을 고른다. 조립은 core.js 가 하고, 데이터는 themes.json 하나다.
// 축마다 같은 예문을 값별로 써 본 보기 카드를 보이고, 카드를 누르면 그 값을 고른다. 다시 누르면 고르기 전으로 돌아간다.
// suit.py serve 로 띄우면 "이번 문서에만" 은 에이전트에게 넘기고 "이 종류에 저장" 은 슬롯의 종류별 값에 쓴다.
// GitHub Pages 로 열면 종류별 값을 이 브라우저의 localStorage 에만 남긴다.
(function () {
  "use strict";
  const KEY = "docs-suit.personal";
  const $ = (id) => document.getElementById(id);
  // 정말 고를 축만 펼친다. 캐릭터 카드의 "지금 테마" 와 같은 세 축이고, 나머지는 "더 바꾸기" 에 접어 둔다
  const MAIN = ["register", "voice", "length"];
  const MORE = ["skeleton", "terms", "emphasis", "markup", "diagram", "sources", "exposure", "ai-disclosure", "visual-deck", "visual-doc"];
  const state = { cls: null, kind: undefined, aud: null, sets: {}, ctx: null };
  let T = null, C = null;

  const L = window.DocsSuitLocal;
  const local = { profile: null, slot: null };
  function loadPersonal() {
    if (L) return local.profile || {};
    try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; }
  }
  function savePersonal(p) {
    try { localStorage.setItem(KEY, JSON.stringify(p)); return true; } catch (e) { return false; }
  }
  function savedKinds() { return loadPersonal().kinds || {}; }

  // ---------------------------------------------------------------- 보기용 작은 마크다운
  function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
  function inline(s) {
    return esc(s)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "<a>$1</a>");
  }
  function md(src) {
    const lines = src.split("\n"), out = [];
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i];
      if (l.startsWith("```")) {
        const buf = [];
        for (i++; i < lines.length && !lines[i].startsWith("```"); i++) buf.push(lines[i]);
        out.push("<pre>" + esc(buf.join("\n")) + "</pre>");
      } else if (l.startsWith("### ")) {
        out.push("<h4>" + inline(l.slice(4)) + "</h4>");
      } else if (l.startsWith("- ")) {
        const buf = [];
        for (; i < lines.length && lines[i].startsWith("- "); i++) buf.push("<li>" + inline(lines[i].slice(2)) + "</li>");
        i--;
        out.push("<ul>" + buf.join("") + "</ul>");
      } else if (l.startsWith("|")) {
        const rows = [];
        for (; i < lines.length && lines[i].startsWith("|"); i++) {
          if (/^\|[-| ]+\|$/.test(lines[i])) continue;
          rows.push("<tr>" + lines[i].slice(1, -1).split("|").map((c) => "<td>" + inline(c.trim()) + "</td>").join("") + "</tr>");
        }
        i--;
        out.push("<table>" + rows.join("") + "</table>");
      } else if (l.trim()) {
        out.push("<p>" + inline(l) + "</p>");
      }
    }
    return out.join("");
  }

  // ---------------------------------------------------------------- 보기 그리기
  function deckPreview(sample) {
    const m = sample.match(/```json\n([\s\S]*?)\n```/);
    let t = {};
    try { t = JSON.parse(m[1]); } catch (e) { /* 색 정보가 없으면 기본색으로 그린다 */ }
    // style 속성에 넣는 값이라 #rrggbb 꼴의 색만 받는다. 기여받은 보기에 다른 CSS 를 끼워 넣지 못하게 한다
    if (!t || typeof t !== "object") t = {};
    for (const k of ["bg", "ink", "muted", "accent"]) if (!/^#[0-9a-fA-F]{3,8}$/.test(String(t[k] || ""))) t[k] = "";
    const head = t.head === "serif" ? "'Noto Serif KR', 'AppleMyungjo', serif" : "inherit";
    return `<span class="deck" style="display:flex;background:${esc(t.bg)};color:${esc(t.ink)}">
      <span class="s" style="color:${esc(t.muted)}">정류장 대기 조사</span>
      <span class="t" style="font-family:${head}">8시대 버스 한 대가<br>대기를 절반으로 줄인다</span>
      <span class="bar" style="display:block;background:${esc(t.accent)}"></span>
      <span class="n" style="color:${esc(t.accent)}">12분 → 6분</span>
      <span class="s" style="color:${esc(t.muted)}">출근 시간대 평균 대기</span></span>`;
  }
  const DOC_SAMPLE = "<h2>정류장 대기 시간 조사</h2><p>출근 시간대 평균 대기는 <strong>12분</strong>으로 다른 시간대의 두 배였다.</p>" +
    "<table><tr><th>시간대</th><th>대기</th></tr><tr><td>8시</td><td>12분</td></tr><tr><td>14시</td><td>6분</td></tr></table>" +
    "<blockquote>8시대 1회 증차를 제안한다.</blockquote>";
  function docPreview(value) {
    const doc = `<!doctype html><meta charset="utf-8"><style>${T.css[value] || ""} body{font-size:13px;margin:0 auto;padding:10px}</style>${DOC_SAMPLE}`;
    return `<iframe title="${esc(value)} 보기" sandbox srcdoc="${esc(doc)}" tabindex="-1"></iframe>`;
  }
  function preview(axis, value) {
    const sample = T.samples[`${axis}/${value}`] || "";
    if (axis === "visual-deck") return deckPreview(sample);
    if (axis === "visual-doc") return docPreview(value);
    return md(sample);
  }

  // ---------------------------------------------------------------- 화면
  function chip(box, label, pressed, onClick) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = label;
    b.setAttribute("aria-pressed", String(pressed));
    b.addEventListener("click", onClick);
    box.appendChild(b);
    return b;
  }

  function mainKinds() { return state.cls ? T.classes[state.cls].kinds : []; }

  // 처음 열 종류. 에이전트가 넘긴 종류, 클래스의 주력 문서 첫 번째, 첫 종류 순이다
  function firstKind() {
    if (state.ctx && state.ctx.fromAgent) return state.ctx.kind;
    return mainKinds()[0] || Object.keys(T.kinds)[0];
  }

  function buildKinds() {
    const c = $("classes");
    c.textContent = "";
    for (const [key, v] of Object.entries(T.classes)) {
      chip(c, v.label, state.cls === key, () => { state.cls = state.cls === key ? null : key; state.kind = firstKind(); render(); });
    }
    const box = $("kinds");
    box.textContent = "";
    const mine = savedKinds();
    const main = mainKinds();
    const row = (title, keys) => {
      if (!keys.length) return;
      if (title) {
        const h = document.createElement("p");
        h.className = "kgroup";
        h.textContent = title;
        box.appendChild(h);
      }
      const wrap = document.createElement("div");
      wrap.className = "chips small";
      box.appendChild(wrap);
      for (const key of keys) {
        const lab = (key ? T.kinds[key].label : "일반 글") + (key && mine[key] ? " · 내 조합" : "");
        chip(wrap, lab, state.kind === key, () => { state.kind = key; state.sets = {}; $("kindPick").open = false; render(); });
      }
    };
    const others = Object.keys(T.kinds).filter((k) => main.indexOf(k) < 0);
    row(main.length ? `${T.classes[state.cls].label}의 주력 문서` : "", main);
    row(main.length ? "다른 문서" : "", others);
    row("종류 없는 글", [null]);
  }

  function buildHead() {
    const k = state.kind;
    $("kindTitle").textContent = k ? T.kinds[k].label : "일반 글";
    const mine = k && savedKinds()[k];
    const now = state.ctx && state.ctx.fromAgent && state.ctx.kind === k;
    const auds = state.aud ? [state.aud] : (k && T.kinds[k].audience) || [];
    $("kindNote").textContent = [now ? "지금 쓰는 문서" : "",
      auds.length ? `독자 ${auds.map((x) => T.audiences[x].label).join(", ")}` : "",
      !k ? "고른 값은 이번 문서에만 씁니다" : mine ? "내가 저장한 조합" : "이 종류가 권하는 조합"].filter(Boolean).join(" · ");
    const a = $("auds");
    a.textContent = "";
    const def = k && T.kinds[k].audience ? T.kinds[k].audience.map((x) => T.audiences[x].label).join(", ") : "없음";
    chip(a, `기본 (${def})`, state.aud === null, () => { state.aud = null; render(); });
    for (const [key, v] of Object.entries(T.audiences)) chip(a, v.label, state.aud === key, () => { state.aud = key; render(); });
  }

  function axisSection(axis, vals, kspec) {
    const [v, src] = vals[axis];
    const sec = document.createElement("section");
    sec.className = "step";
    const h = document.createElement("h2");
    h.innerHTML = `${esc(T.axes[axis].label)} <span class="now">지금 <b>${esc(C.label(axis, v))}</b> · ${esc(C.SRC[src])}</span>`;
    sec.appendChild(h);
    const locked = kspec[axis] && axis !== "exposure";
    let note = "";
    if (locked) note = "이 축은 문서 종류의 틀이 정합니다.";
    else if (src === "talk") note = "정하지 않으면 AI 가 요청과 대화에서 읽어 맞춥니다.";
    else if (axis === "exposure") note = "개인정보를 지키는 축이라 더 조심하는 쪽으로만 바꿀 수 있습니다.";
    if (note) {
      const n = document.createElement("p");
      n.className = "note";
      n.textContent = note;
      sec.appendChild(n);
    }
    if (locked) return sec;
    const row = document.createElement("div");
    row.className = "cards";
    row.dataset.axis = axis;
    for (const [value, lab] of Object.entries(T.axes[axis].values)) {
      const b = document.createElement("button");
      b.type = "button";
      const chosen = state.sets[axis] === value, active = v === value;
      b.className = "card" + (active ? " active" : "") + (chosen ? " chosen" : "");
      b.setAttribute("aria-pressed", String(chosen));
      b.setAttribute("aria-label", `${T.axes[axis].label} ${lab}${active ? ", 지금 쓰는 값" : ""}`);
      const kind = axis === "visual-doc" ? " frame" : axis === "visual-deck" ? " slide" : "";
      b.innerHTML = `<span class="cl"><span>${esc(lab)}</span><span class="badge">${chosen ? "고름" : active ? "지금" : ""}</span></span>` +
        `<span class="pv${kind}">${preview(axis, value)}</span>`;
      b.addEventListener("click", () => {
        if (state.sets[axis] === value) delete state.sets[axis];
        else state.sets[axis] = value;
        render();
      });
      row.appendChild(b);
    }
    sec.appendChild(row);
    return sec;
  }

  function buildGallery(vals) {
    const keep = {};
    document.querySelectorAll(".cards").forEach((row) => { keep[row.dataset.axis] = row.scrollLeft; });
    const kspec = state.kind ? T.kinds[state.kind] : {};
    const shown = (axis) => (axis !== "visual-deck" || state.kind === "slides") && (axis !== "visual-doc" || vals.markup[0] === "html");
    for (const [id, axes] of [["gallery", MAIN], ["gallery2", MORE]]) {
      const g = $(id);
      g.textContent = "";
      for (const axis of axes.filter(shown)) g.appendChild(axisSection(axis, vals, kspec));
    }
    const rest = MORE.filter(shown);
    const picked = rest.filter((a) => state.sets[a]).length;
    $("moreSum").textContent = `더 바꾸기 · 축 ${rest.length}개와 독자` + (picked ? ` · 고른 것 ${picked}개` : "");
    document.querySelectorAll(".cards").forEach((row) => {
      if (keep[row.dataset.axis]) row.scrollLeft = keep[row.dataset.axis];
      row.classList.toggle("overflow", row.scrollWidth > row.clientWidth + 4);
    });
  }

  function buildPicked() {
    const ul = $("picked");
    ul.textContent = "";
    const keys = Object.keys(state.sets);
    if (!keys.length) {
      const li = document.createElement("li");
      li.className = "muted";
      li.textContent = "바꿀 축의 카드를 누르세요.";
      ul.appendChild(li);
    }
    for (const axis of keys) {
      const li = document.createElement("li");
      li.textContent = `${T.axes[axis].label} · ${C.label(axis, state.sets[axis])}`;
      ul.appendChild(li);
    }
    $("apply").disabled = !keys.length;
    $("save").disabled = !keys.length || !state.kind;
    $("save").title = state.kind ? "" : "종류 없는 글은 저장하지 않습니다";
    $("clearKind").hidden = !(state.kind && savedKinds()[state.kind]);
  }

  function render() {
    if (state.kind === undefined) state.kind = firstKind();
    const auds = state.aud ? [state.aud] : [];
    const r = C.resolve(state.kind, auds, state.sets, loadPersonal(), state.cls, true);
    buildKinds();
    buildHead();
    buildGallery(r.vals);
    buildPicked();
    $("warns").textContent = r.warns.join(" ");
    const chars = parseInt($("chars").value, 10) || null;
    const fmt = document.querySelector("input[name=fmt]:checked").value;
    $("out").value = C.compose(state.kind, r.auds, r.vals, chars, fmt, $("revise").checked, r.cls, null);
    state.review = C.review(state.kind, r.auds, r.vals, chars);
  }

  async function copy(text, done) {
    try {
      await navigator.clipboard.writeText(text);
      $("webStatus").textContent = done;
    } catch (e) {
      $("out").select();
      $("webStatus").textContent = "복사하지 못했습니다. 지침 칸을 선택해 두었으니 Ctrl+C 로 복사하세요.";
    }
  }

  // GitHub Pages 판의 "이 종류에 저장". 이 브라우저에만 남긴다
  function webSave() {
    if (!state.kind) { $("webStatus").textContent = "종류 없는 글은 저장하지 않습니다."; return; }
    const p = loadPersonal();
    p.kinds = Object.assign({}, p.kinds || {});
    p.kinds[state.kind] = Object.assign({}, p.kinds[state.kind] || {}, state.sets);
    const ok = savePersonal(p);
    state.sets = {};
    $("webStatus").textContent = ok ? `이 브라우저에 ${T.kinds[state.kind].label} 조합으로 저장했습니다.` : "저장하지 못했습니다. 브라우저 저장소가 막혀 있습니다.";
    render();
  }

  function wire() {
    document.querySelectorAll("aside .guide input").forEach((el) => el.addEventListener("input", render));
    $("copy").addEventListener("click", () => copy($("out").value, "복사했습니다."));
    $("copyReview").addEventListener("click", () => copy(state.review,
      "검토 지침을 복사했습니다. 새 대화에 붙여 넣고 원문과 다 쓴 글을 빈자리에 채웁니다."));
    $("download").addEventListener("click", () => {
      const blob = new Blob([$("out").value], { type: "text/markdown" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `docs-suit-${state.kind || "general"}.md`;
      a.click();
      URL.revokeObjectURL(a.href);
    });
    $("webSave").addEventListener("click", webSave);
    $("apply").addEventListener("click", async () => {
      try {
        const auds = state.aud ? [state.aud] : (state.ctx ? state.ctx.audiences : []);
        const sets = Object.assign({}, state.ctx && state.ctx.kind === state.kind ? state.ctx.sets : {}, state.sets);
        const r = await L.api("/api/pick", { kind: state.kind, audiences: auds, sets });
        $("status").textContent = "골랐습니다. 대화창에 \"골랐어\" 라고 하면 에이전트가 이 값으로 다시 씁니다.";
      } catch (e) { $("status").textContent = e.message; }
    });
    $("save").addEventListener("click", async () => {
      try {
        const r = await L.api("/api/defaults", { slot: local.slot, here: $("here").checked, kind: state.kind, defaults: { ...state.sets } });
        state.sets = {};
        applyLocal(r.state);
        L.changed();
        $("status").textContent = `${r.message}. 다음 ${T.kinds[state.kind].label}부터 이 조합으로 씁니다.`;
      } catch (e) { $("status").textContent = e.message; }
    });
    $("clearKind").addEventListener("click", async () => {
      try {
        const r = await L.api("/api/defaults", { slot: local.slot, here: $("here").checked, kind: state.kind, clear: true });
        applyLocal(r.state);
        L.changed();
        $("status").textContent = `${T.kinds[state.kind].label}를 종류가 권하는 조합으로 되돌렸습니다.`;
      } catch (e) { $("status").textContent = e.message; }
    });
    $("reset").addEventListener("click", () => { state.sets = {}; $("status").textContent = ""; render(); });
  }

  function applyLocal(st) {
    local.profile = st.merged || {};
    local.slot = st.slot;
    state.cls = (local.profile.profile || {}).class || state.cls;
    if (st.context && !state.ctx) {
      state.ctx = Object.assign({ fromAgent: !!(st.context.kind || st.context.audiences.length) }, st.context);
      if (state.ctx.fromAgent) {
        state.kind = st.context.kind;
        state.aud = st.context.audiences.length === 1 ? st.context.audiences[0] : null;
      }
    }
    L.banner(st, async (name) => {
      try {
        state.sets = {};
        applyLocal(await L.api(`/api/state?slot=${encodeURIComponent(name)}`));
      } catch (e) { $("status").textContent = e.message; }
    });
    render();
  }

  fetch("themes.json" + ((m) => (m ? `?v=${m.content}` : ""))(document.querySelector('meta[name="docs-suit-data"]'))).then((r) => r.json()).then(async (data) => {
    T = data;
    C = ThemeCore(T);
    wire();
    if (L) {
      document.body.classList.add("is-local");
      try { applyLocal(await L.api(L.stateUrl())); } catch (e) { $("status").textContent = e.message; }
    } else {
      $("guide").open = true;
    }
    // 에이전트가 쓰던 문서로 연 것이 아니면 무엇을 쓸지부터 고른다
    $("kindPick").open = !(state.ctx && state.ctx.fromAgent);
    render();
  })
    .catch(() => { $("out").value = "themes.json 을 읽지 못했습니다. 로컬에서 열 때는 docs 폴더에서 python3 -m http.server 로 띄워 주세요."; });
})();
