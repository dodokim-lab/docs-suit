// 웹 판의 써 보기 탭. 설치 없이 들어온 사람이 클래스와 템플릿을 고르고, 지침을 붙인 요청을 자기 AI 에 채워 연다.
// 템플릿은 themes/ko/trials/ 에서 오고, 축 값은 고를 수 없다. 문서 종류와 독자, 클래스의 기본값으로 core.js 가 조립한다.
// 클래스마다 끝에 두는 자유 형식은 종류 없이 조립해, 말투와 분량을 요청에 적은 대로 따르게 한다.
// ChatGPT 와 Claude 는 주소의 q 로 입력창을 채운다. Gemini 는 긴 주소를 받지 않아 복사해 두고 연다.
// 다른 사이트로 넘어가는 일이라 열기 전에 한 번 묻는다. 예를 누른 그 손짓 안에서 복사하고 새 창을 연다.
// 클래스 칸에는 그 클래스의 4차 전직 모습을, 머리 맵에는 고른 클래스가 전직하는 다섯 단계를 그린다.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const AI = {
    gpt: { name: "ChatGPT", open: (q) => "https://chatgpt.com/?q=" + encodeURIComponent(q), how: "새 창에서 ChatGPT 가 열리고 입력창에 요청이 채워집니다. 보내기를 누르면 글을 씁니다." },
    claude: { name: "Claude", open: (q) => "https://claude.ai/new?q=" + encodeURIComponent(q), how: "새 창에서 Claude 가 열리고 입력창에 요청이 채워집니다. 보내기를 누르면 글을 씁니다." },
    gemini: { name: "Gemini", open: () => "https://gemini.google.com/app", copy: true, how: "요청을 복사해 두고 새 창에서 Gemini 를 엽니다. 입력창에 붙여 넣고 보내세요." },
  };
  let pending = null;
  const FREE = "free";
  const NOTE = {
    trial: "예시 그대로 보내도 되고, 정류장 조사 대신 내 일을 적어도 됩니다. 글의 형식은 2번에서 고른 대로입니다.",
    free: "쓸 글과 읽을 사람, 담을 내용을 적습니다. 말투와 분량도 적으면 그대로 따릅니다.",
  };
  const state = { cls: null, trial: null };
  let T = null, C = null;

  function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  function trialsOf(cls) { return Object.keys(T.trials).filter((k) => T.trials[k].class === cls); }

  function rules() {
    if (state.trial === FREE) {
      const r = C.resolve(null, [], {}, null, null, true);
      return C.compose(null, r.auds, r.vals, null, "prompt", false, r.cls, null);
    }
    const t = T.trials[state.trial];
    const r = C.resolve(t.kind, [t.audience], {}, null, t.class, false);
    return C.compose(t.kind, r.auds, r.vals, null, "prompt", false, r.cls, null);
  }

  function withRules() { return `${rules()}\n---\n\n위 지침을 이번 글의 규칙으로 따른다.\n\n${$("ask").value.trim()}\n`; }

  function draw(canvas, grid, scale) {
    canvas.width = grid[0].length * scale;
    canvas.height = grid.length * scale;
    const ctx = canvas.getContext("2d");
    grid.forEach((row, y) => row.forEach((c, x) => {
      if (!c) return;
      ctx.fillStyle = c;
      ctx.fillRect(x * scale, y * scale, scale, scale);
    }));
  }

  function gridOf(cls, tier) { return C.lookGrid(C.lookOf({ profile: { class: cls } }, tier)); }

  function buildClasses() {
    $("classes").innerHTML = Object.keys(T.classes).map((c) =>
      `<button type="button" class="pick" data-cls="${esc(c)}" aria-pressed="${c === state.cls}"><canvas></canvas><b>${esc(T.classes[c].label)}</b></button>`).join("");
    $("classes").querySelectorAll("[data-cls]").forEach((b) => draw(b.querySelector("canvas"), gridOf(b.dataset.cls, 4), 3));
    $("stage").innerHTML = [0, 1, 2, 3, 4].map((t) => `<figure><canvas></canvas><figcaption>${esc(C.titleOf(state.cls, t))}</figcaption></figure>`).join("");
    $("stage").querySelectorAll("canvas").forEach((cv, t) => draw(cv, gridOf(state.cls, t), t === 4 ? 4 : 3));
    draw($("npc"), gridOf(state.cls, 0), 3);
  }

  function buildTrials() {
    $("trials").innerHTML = trialsOf(state.cls).map((k) => {
      const t = T.trials[k];
      const sub = `읽는 사람 ${T.audiences[t.audience].label}`;
      return `<button type="button" class="opt" data-trial="${esc(k)}" aria-pressed="${k === state.trial}"><b>${esc(t.label)}</b><span class="d">${esc(sub)}</span></button>`;
    }).join("") + `<button type="button" class="opt" data-trial="${FREE}" aria-pressed="${state.trial === FREE}"><b>자유 형식</b><span class="d">형식과 말투를 요청에 적은 대로</span></button>`;
  }

  function summary() {
    $("rules").value = rules();
    const t = T.trials[state.trial];
    $("picked").textContent = t ? `${T.kinds[t.kind].label} · ${T.audiences[t.audience].label} · 기본값` : "자유 형식";
  }

  function pick(trial) {
    state.trial = trial;
    const free = trial === FREE;
    $("ask").value = free ? "" : T.trials[trial].ask;
    $("ask").placeholder = free ? "예) 팀원들에게 보낼 다음 주 사무실 이사 공지를 해요체로 짧게 써 줘.\n- 이사 날짜는 다음 주 금요일\n- 짐은 목요일 저녁까지 상자에 담아 둔다" : "";
    $("askNote").textContent = free ? NOTE.free : NOTE.trial;
    $("reset").hidden = free;
    $("status").textContent = "";
    buildTrials();
    summary();
  }

  function pickClass(cls) {
    state.cls = cls;
    buildClasses();
    pick(trialsOf(cls)[0]);
  }

  // 자유 형식에서 요청을 비운 채 보내면 AI 가 무엇을 쓸지 되묻기만 한다. 보내기 전에 막고 칸으로 돌려보낸다
  function empty() {
    if ($("ask").value.trim()) return false;
    $("status").textContent = "3번에 쓸 이야기를 먼저 적어 주세요.";
    $("ask").focus();
    return true;
  }

  function ask(ai, raw) {
    if (empty()) return;
    const a = AI[ai];
    pending = { ai, raw };
    $("cfmTitle").textContent = raw ? `지침 없이 ${a.name} 로 같은 요청을 보낼까요?` : `${a.name} 로 글쓰기를 진행할까요?`;
    $("cfmBody").textContent = a.how;
    $("confirm").showModal();
  }

  function go() {
    const { ai, raw } = pending;
    const a = AI[ai];
    const text = raw ? $("ask").value.trim() : withRules();
    $("confirm").close();
    if (a.copy) copy(text, "요청을 복사했습니다. 열린 Gemini 입력창에 붙여 넣고 보내세요.");
    else $("status").textContent = `${a.name} 를 새 창에서 열었습니다.`;
    // 링크를 눌러 연 것처럼 열어야 휴대폰에서 앱으로 넘어갈 수 있다
    const link = document.createElement("a");
    link.href = a.open(text);
    link.target = "_blank";
    link.rel = "noopener";
    link.click();
  }

  async function copy(text, done) {
    try {
      await navigator.clipboard.writeText(text);
      $("status").textContent = done;
    } catch (e) {
      $("status").textContent = "복사하지 못했습니다. 브라우저가 클립보드를 막았습니다.";
    }
  }

  function wire() {
    $("classes").addEventListener("click", (e) => { const b = e.target.closest("[data-cls]"); if (b) pickClass(b.dataset.cls); });
    $("trials").addEventListener("click", (e) => { const b = e.target.closest("[data-trial]"); if (b) pick(b.dataset.trial); });
    $("ask").addEventListener("input", summary);
    $("reset").addEventListener("click", () => pick(state.trial));
    document.querySelectorAll("[data-ai]").forEach((b) => b.addEventListener("click", () => ask(b.dataset.ai, b.dataset.raw === "1")));
    $("cfmYes").addEventListener("click", go);
    $("cfmNo").addEventListener("click", () => $("confirm").close());
    $("copy").addEventListener("click", () => { if (!empty()) copy(withRules(), "지침을 붙인 요청을 복사했습니다. 쓰는 AI 의 입력창에 붙여 넣으세요."); });
  }

  fetch("themes.json" + ((m) => (m ? `?v=${m.content}` : ""))(document.querySelector('meta[name="docs-suit-data"]'))).then((r) => r.json()).then((data) => {
    T = data;
    C = ThemeCore(T);
    wire();
    // 주소의 ?class= 는 아무 글자나 올 수 있다. constructor 같은 이름이 객체의 물려받은 속성으로 잡히지 않게 제 키만 본다
    const want = new URLSearchParams(location.search).get("class");
    pickClass(want && Object.hasOwn(T.classes, want) ? want : "office");
  }).catch(() => { $("status").textContent = "themes.json 을 읽지 못했습니다."; });
})();
