// 웹 고르개(core.js)와 suit.py 가 같은 지침을 조립하는지 견준다. 실행: node tests/parity.js
const { execFileSync } = require("child_process");
const path = require("path");
const root = path.join(__dirname, "..");
const T = require(path.join(root, "docs", "themes.json"));
const C = require(path.join(root, "docs", "core.js"))(T);

const all = JSON.parse(execFileSync("python3", [path.join(__dirname, "parity_cases.py")], { maxBuffer: 1 << 28 }).toString());
const cases = all.compose;
let bad = 0;
for (const c of cases) {
  const r = C.resolve(c.kind, c.auds, c.sets, c.profile, c.cls, c.talk);
  const words = (c.profile || {}).words;
  const js = C.compose(c.kind, r.auds, r.vals, c.chars, c.fmt, c.revise, r.cls, (c.profile || {}).persona, c.voice, words);
  const rv = C.review(c.kind, r.auds, r.vals, c.chars, c.voice, words);
  if (js !== c.expected || rv !== c.review) {
    bad++;
    if (bad <= 3) console.log(`다름(${js !== c.expected ? "지침" : "검토"}): class=${c.cls} kind=${c.kind} audience=${c.auds} fmt=${c.fmt} talk=${c.talk}`);
  }
}
// 웹 캐릭터 만들기의 슬롯 파일과 캐릭터 그림
for (const c of all.slots) {
  if (C.dumpYaml(c.data) !== c.expected) {
    bad++;
    console.log("슬롯 파일이 다름:\n" + C.dumpYaml(c.data) + "\n--- 기대\n" + c.expected);
  }
}
for (const c of all.looks) {
  const look = C.lookOf(c.slot, c.tier);
  if (JSON.stringify(look) !== JSON.stringify(c.look) || JSON.stringify(C.lookGrid(look)) !== JSON.stringify(c.expected)) {
    bad++;
    console.log(`캐릭터 그림이 다름: ${JSON.stringify(c.slot)} 차수 ${c.tier} → ${JSON.stringify(look)} / 기대 ${JSON.stringify(c.look)}`);
  }
}
for (const c of all.texts) {
  if (C.cleanText(c.raw) !== c.expected) {
    bad++;
    console.log(`한 줄 답이 다름: ${JSON.stringify(c.raw)} → ${JSON.stringify(C.cleanText(c.raw))} / 기대 ${JSON.stringify(c.expected)}`);
  }
}
const total = cases.length + all.slots.length + all.looks.length + all.texts.length;
console.log(bad ? `parity 실패 ${bad}/${total}` : `parity 통과 ${total}건`);
process.exit(bad ? 1 : 0);
