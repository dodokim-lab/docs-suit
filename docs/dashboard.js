// 대시보드. 캐릭터, 캐릭터 설정, 테마 설정 세 화면을 탭으로 품는다. 화면마다 따로 열어도 되도록 탭은 iframe 으로 둔다.
// 웹 판은 index.html 이 써 보기(try.html)로 바로 넘기므로 이 파일은 suit.py serve 로 띄운 로컬 판에서만 돈다.
// suit.py serve 로 띄우면 맨 위 띠에서 슬롯을 고르고, 탭 주소의 ?slot= 으로 넘긴다. 한 탭에서 저장하면 다른 탭은 다음에 열 때 다시 읽는다.
(function () {
  "use strict";
  const PAGES = { character: "character.html", setup: "create.html", theme: "theme.html" };
  const L = window.DocsSuitLocal;
  const frames = {}, dirty = {};
  let slot = null, current = null;
  document.querySelectorAll("iframe[data-tab]").forEach((f) => { frames[f.dataset.tab] = f; });

  function src(tab) { return PAGES[tab] + (slot ? `?slot=${encodeURIComponent(slot)}` : ""); }

  function show(tab) {
    if (!Object.hasOwn(PAGES, tab)) return;  // 주소의 #constructor 같은 이름을 탭으로 받지 않는다
    current = tab;
    for (const [t, f] of Object.entries(frames)) {
      f.hidden = t !== tab;
      if (t === tab && (!f.src || dirty[t])) {
        dirty[t] = false;
        f.src = src(t);
      }
    }
    document.querySelectorAll("[role=tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
    if (location.hash !== `#${tab}`) history.replaceState(null, "", `#${tab}`);
  }

  // 띠의 슬롯을 바꾸면 모든 탭을 그 슬롯으로 다시 연다
  function banner(st) {
    L.banner(st, async (name) => {
      slot = name;
      for (const t of Object.keys(frames)) dirty[t] = true;
      show(current);
      try { banner(await L.api(L.stateUrl(slot))); } catch (e) { /* 띠는 다음에 다시 그린다 */ }
    });
  }

  // 처음 열 탭. 주소의 탭, 이 폴더에 이은 캐릭터가 있으면 캐릭터, 없으면 캐릭터 설정 순이다. 엔진의 serve_page 와 같다
  function firstTab(st) {
    const hash = location.hash.slice(1);
    if (Object.hasOwn(PAGES, hash)) return hash;
    if (st && st.exists && ["env", "arg", "folder"].indexOf(st.why) >= 0) return "character";
    return "setup";
  }

  document.querySelectorAll("[role=tab]").forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));
  window.addEventListener("message", async (ev) => {
    if (ev.origin !== location.origin || !ev.data || !ev.data.docsSuit) return;
    if (ev.data.docsSuit === "tab") return show(ev.data.tab);
    if (ev.data.docsSuit === "changed") {
      for (const t of Object.keys(frames)) if (t !== current) dirty[t] = true;
      if (L) try { banner(await L.api(L.stateUrl(slot))); } catch (e) { /* 띠는 다음에 다시 그린다 */ }
    }
  });

  (async () => {
    let st = null;
    if (L) {
      document.body.classList.add("is-local");
      try { st = await L.api(L.stateUrl()); banner(st); } catch (e) { document.getElementById("local").textContent = e.message; }
    }
    show(firstTab(st));
  })();
})();
