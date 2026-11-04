// 웹 판(GitHub Pages)에서만 GoatCounter 로 방문과 버튼 클릭 수를 센다. 남의 스크립트를 싣지 않고 /count 주소에 숫자만 보낸다.
// 쿠키를 쓰지 않고, 사용자가 적은 요청이나 지침은 보내지 않는다. 보내는 것은 화면 주소와 템플릿 이름, AI 이름뿐이다.
// 로컬 화면(suit.py serve)과 다른 곳에 올린 사본은 주소가 달라서 아무것도 보내지 않는다.
(function (root) {
  "use strict";
  const CODE = "docs-suit"; // GoatCounter 코드 이름. 비어 있으면 세지 않는다
  const on = Boolean(CODE) && root.location.hostname === "dodokim-lab.github.io";

  function send(path, event) {
    if (!on) return;
    const q = new URLSearchParams({ p: path, rnd: String(Math.random()).slice(2) });
    if (event) q.set("e", "true");
    else {
      q.set("t", document.title);
      if (document.referrer) q.set("r", document.referrer);
    }
    if (root.navigator.webdriver) q.set("b", "153"); // 자동화한 브라우저는 봇으로 알려 세지 않게 한다
    new Image().src = `https://${CODE}.goatcounter.com/count?${q}`;
  }

  root.dsCount = (name) => send(name, true);
  send(root.location.pathname, false);
})(window);
