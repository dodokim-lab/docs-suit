// 테마 조립 핵심. suit.py 의 resolve 와 compose 를 같은 순서로 옮겼다. 브라우저와 node 가 같이 쓴다.
// tests/parity.js 가 두 쪽의 출력이 글자 하나까지 같은지 확인한다.
(function (root) {
  "use strict";
  function make(T) {
    function fromAudiences(axis, auds, table) {
      const vals = auds.filter((a) => table[a] && table[a][axis]).map((a) => table[a][axis]);
      if (!vals.length) return null;
      const pick = (order) => vals.reduce((b, v) => (order.indexOf(v) < order.indexOf(b) ? v : b));
      if (axis === "exposure") return pick(T.exposureStrict);
      if (axis === "terms") return pick(T.termsPlain);
      return vals[0];
    }

    // suit.py resolve() 와 같은 순서: kind > arg > profile-kind > profile-audience > prefer > profile > audience > class > default
    // talk 이면 종류 없는 글의 문체 축은 직접 고른 값으로만 정하고, 없으면 [null, "talk"] 로 남겨 대화로 정하게 한다.
    function resolve(kind, auds, sets, profile, cls, talk) {
      const warns = [];
      profile = profile || {};
      cls = cls || (profile.profile && profile.profile.class) || null;
      const kspec = kind ? T.kinds[kind] : {};
      if (!auds.length && kspec.audience) auds = kspec.audience.slice();
      const pDef = profile.defaults || {};
      const pAud = profile.audiences || {};
      const pKindRaw = kind && profile.kinds ? profile.kinds[kind] : null;
      const pKind = pKindRaw && typeof pKindRaw === "object" ? pKindRaw : {};
      const prefer = (kind && T.prefer[kind]) || {};
      const cDef = cls ? T.classes[cls].defaults : {};
      const out = {};
      for (const axis of T.axesOrder) {
        const fixed = kspec[axis];
        if (axis === "exposure") {
          let base = null, src = null;
          for (const [c, s] of [[fixed, "kind"], [fromAudiences(axis, auds, T.audiences), "audience"], [cDef[axis], "class"], [T.defaults[axis], "default"]]) {
            if (c) { base = c; src = s; break; }
          }
          for (const [c, s] of [[sets[axis], "arg"], [pKind[axis], "profile-kind"], [fromAudiences(axis, auds, pAud), "profile-audience"], [pDef[axis], "profile"]]) {
            if (!c || T.exposureStrict.indexOf(c) < 0) continue;
            if (T.exposureStrict.indexOf(c) < T.exposureStrict.indexOf(base)) { base = c; src = s; }
            else if (c !== base) warns.push(`공개 범위는 더 조심하는 쪽으로만 바뀌어 ${c} 대신 ${base} 를 씁니다. 팀 안에서만 볼 글이면 독자에서 팀원·동료나 동료 개발자를 고릅니다`);
          }
          out[axis] = [base, src];
          continue;
        }
        if (fixed) {
          if (sets[axis] && sets[axis] !== fixed) warns.push(`${T.axes[axis].label} 은 문서 종류가 고정해 바꿀 수 없습니다`);
          out[axis] = [fixed, "kind"];
          continue;
        }
        if (talk && !kind && T.talkKeep.indexOf(axis) < 0) {
          out[axis] = sets[axis] ? [sets[axis], "arg"] : [null, "talk"];
          continue;
        }
        const chain = [[sets[axis], "arg"], [pKind[axis], "profile-kind"], [fromAudiences(axis, auds, pAud), "profile-audience"], [prefer[axis], "prefer"],
          [pDef[axis], "profile"], [fromAudiences(axis, auds, T.audiences), "audience"], [cDef[axis], "class"], [T.defaults[axis], "default"]];
        for (const [c, s] of chain) {
          if (!c) continue;
          if (s.startsWith("profile") && !(c in T.axes[axis].values)) continue;
          out[axis] = [c, s];
          break;
        }
      }
      return { vals: out, auds, cls, warns };
    }

    const SRC = { kind: "문서 종류가 고정", arg: "직접 고름", "profile-kind": "내 문서 종류 설정", "profile-audience": "내 독자 설정", prefer: "문서 종류가 권함",
      profile: "내 기본값", audience: "독자", class: "클래스", default: "중립 기본값", talk: "대화로 정함" };

    function label(axis, v) {
      if (v === null) return "정하지 않음";
      return v === "template" ? "문서 종류의 틀" : (T.axes[axis].values[v] || v);
    }

    function personaSection(cls, persona) {
      persona = persona || {};
      const rows = [];
      if (cls) rows.push(`- 클래스: ${T.classes[cls].label}`);
      for (const key of T.personaInPrompt) {
        if (persona[key]) rows.push(`- ${(T.persona[key] || {}).label || key}: ${persona[key]}`);
      }
      if (!rows.length) return "";
      return "## 쓰는 사람\n\n이 글을 쓰는 사람에 대한 맥락이다. 관점과 예시, 말투를 고르는 데만 쓰고, " +
        "사용자가 넣으라고 하지 않는 한 본문에 옮겨 적지 않는다.\n\n" + rows.join("\n");
    }

    // suit.py rule_sections() 와 같다. compose 와 review 가 같이 쓴다. 앞에 나온 절이 이긴다.
    // voice 는 슬롯의 내 문체 문서다. 맨 끝에 실어 다른 규칙이 정하지 않은 곳만 채운다.
    const VOICE_HEAD = "이 사람이 예전에 쓴 글에서 뽑은 버릇이다. 위의 규칙과 부딪치면 위의 규칙을 따르고, " +
      "위의 규칙이 정하지 않은 곳에서만 따른다.";
    // words 는 폴더 파일의 용어집이다. 팀이 정한 표기라 문서 종류 바로 뒤에 실어 축 규칙보다 앞세운다.
    const WORDS_HEAD = "이 폴더의 문서는 아래 표기를 따른다. 화살표 왼쪽 말을 쓰지 않고 오른쪽 말로 쓴다. 인용한 원문은 고치지 않는다.";
    function ruleSections(kind, vals, chars, revise, voice, words) {
      const out = [["공통 바닥", T.base]];
      if (revise) out.push(["다듬기", T.revise]);
      if (kind) out.push([`문서 종류 · ${T.kinds[kind].label}`, T.kindText[kind]]);
      if (words && Object.keys(words).length) {
        out.push(["표기 · 용어집", WORDS_HEAD + "\n\n" + Object.entries(words).map(([w, r]) => `- ${w} → ${r}`).join("\n")]);
      }
      const talk = T.composeOrder.filter((axis) => vals[axis][0] === null);
      if (talk.length) {
        out.push(["대화로 정하기", `정하지 않은 축: ${talk.map((axis) => T.axes[axis].label).join(", ")}\n\n` + T.talk]);
      }
      for (const axis of T.composeOrder) {
        const v = vals[axis][0];
        if (v === "template" || v === null) continue;
        if (axis === "visual-deck" && kind !== "slides") continue;
        if (axis === "visual-doc" && vals.markup[0] !== "html") continue;
        out.push([`${T.axes[axis].label} · ${label(axis, v)}`, T.rules[`${axis}/${v}`]]);
        if (axis === "length" && chars) {
          out.push([`글자수 · 공백 포함 ${chars}자 이내`,
            `- 본문은 공백 포함 ${chars}자를 넘기지 않는다. 넘치면 근거가 약한 문장부터 뺀다.\n` +
            "- 다 쓴 뒤 끝에 `(공백 포함 n자)` 로 센 값을 적는다.\n" +
            "- AI 가 센 글자수는 틀리기 쉽다. 제출 전에 글자수 세기 도구로 다시 잰다."]);
        }
      }
      if (voice) out.push(["내 문체", `${VOICE_HEAD}\n\n${voice}`]);
      return out;
    }

    function labels(kind, auds) {
      return [kind ? T.kinds[kind].label : "일반 글", auds.map((a) => T.audiences[a].label).join(", ") || "정하지 않음"];
    }

    function compose(kind, auds, vals, chars, fmt, revise, cls, persona, voice, words) {
      const [kindLabel, audLabel] = labels(kind, auds);
      const sections = ruleSections(kind, vals, chars, revise, voice, words).map(([h, b]) => `## ${h}\n\n${b}`);
      const who = personaSection(cls, persona);
      const parts = [
        `# 글쓰기 테마 · ${kindLabel} · 독자 ${audLabel}`,
        "이 대화에서 쓰는 글에 아래 규칙을 적용한다. 규칙끼리 부딪치면 앞에 나온 규칙을 따른다. 이 지침은 docs-suit 로 조립했다.",
        sections[0],
      ].concat(who ? [who] : [], sections.slice(1));
      let text = parts.join("\n\n") + "\n";
      if (fmt === "output-style") {
        text = "---\n" + `name: ${kindLabel} (${audLabel})\n` +
          `description: docs-suit 로 조립한 글쓰기 테마. ${kindLabel}, 독자 ${audLabel}\n` +
          "keep-coding-instructions: true\n---\n\n" + text;
      }
      return text;
    }
    // suit.py review() 와 같다. 쓴 사람과 같은 값으로 채점하되 페르소나는 싣지 않는다.
    function review(kind, auds, vals, chars, voice, words) {
      const [kindLabel, audLabel] = labels(kind, auds);
      const parts = [`# 검토 지침 · ${kindLabel} · 독자 ${audLabel}`, T.review]
        .concat(ruleSections(kind, vals, chars, false, voice, words).map(([h, b]) => `## 채점 기준 · ${h}\n\n${b}`));
      parts.push("## 원문\n\n(과제 안내문, 채용 공고, 요청 메일처럼 이 글이 따라야 할 원문 전체. 없으면 비워 둔다)");
      parts.push("## 검토할 글\n\n(다 쓴 글 전체)");
      return parts.join("\n\n") + "\n";
    }

    // ---------------------------------------------------------------- 캐릭터와 슬롯 파일
    // suit.py 의 look_of, look_grid, title_of, level_of, dump_yaml, clean_text 와 같은 규칙이다. tests/parity.js 가 견준다.
    const LAYERS = ["top", "hair", "prop"];

    function spriteGrid(name, custom) {
      const sp = T.sprites[name];
      const colors = {};
      for (const [ch, p] of Object.entries(sp.palette)) colors[ch] = custom && p.custom ? custom : p.color;
      return sp.rows.map((row) => Array.from(row).map((ch) => colors[ch] || null));
    }

    // 클래스가 전직할 때 여는 꾸미기. [차수, 부위, 값] 의 목록이다.
    function classRewards(cls) {
      const out = [];
      const table = (T.look.rewards || {})[cls] || {};
      for (const tier of Object.keys(table).sort((a, b) => parseInt(a, 10) - parseInt(b, 10))) {
        for (const item of table[tier]) {
          const i = item.indexOf(".");
          out.push([parseInt(tier, 10), item.slice(0, i), item.slice(i + 1)]);
        }
      }
      return out;
    }

    function lookLabel(part, val) {
      return part === "color" ? T.look.colors[val].label : T.look[part][val];
    }

    // 이 차수에서 새로 여는 꾸미기의 이름들. "소품 가방끈" 꼴이다.
    function openedAt(cls, tier) {
      const names = {};
      for (const [t, part, val] of classRewards(cls)) {
        if (t === tier) (names[part] = names[part] || []).push(lookLabel(part, val));
      }
      return Object.entries(names).map(([part, vals]) => `${T.look.parts[part]} ${vals.join(", ")}`);
    }

    // 부위마다 고를 수 있는 값. 머리 모양은 처음부터, 나머지는 클래스가 tier 차까지 연 것이다.
    function lookOpen(cls, tier) {
      const all = (part) => new Set(Object.keys(part === "color" ? T.look.colors : T.look[part]));
      if (tier === undefined || tier === null) return { top: all("top"), hair: all("hair"), prop: all("prop"), color: all("color") };
      const out = { top: new Set(["shirt"]), hair: all("hair"), prop: new Set(), color: new Set() };
      for (const [t, part, val] of classRewards(cls)) if (t <= tier) out[part].add(val);
      return out;
    }

    // 부위마다 가장 최근 차수에 연 꾸미기. 한 차수에 여럿을 열면 앞의 것이다.
    function lookLatest(cls, tier) {
      const out = {};
      if (tier === undefined || tier === null) return out;
      const seen = new Set();
      for (const [t, part, val] of classRewards(cls)) {
        if (t <= tier && !seen.has(`${t}.${part}`)) {
          out[part] = val;
          seen.add(`${t}.${part}`);
        }
      }
      return out;
    }

    // 슬롯의 look 에 기본값을 채운다. tier 를 주면 그 차수까지 클래스가 연 꾸미기만 입히고, 고르지 않은 부위는 가장 최근에 연 것을 입힌다.
    function lookOf(slot, tier) {
      const have = (slot && slot.look) || {};
      const bases = T.look.base || {};
      const base = have.base in bases ? have.base : Object.keys(bases)[0];
      const look = { base, top: "shirt", hair: (bases[base] || {}).hair, prop: null, color: null };
      const tables = { top: T.look.top, hair: T.look.hair, prop: T.look.prop, color: T.look.colors };
      const cls = ((slot && slot.profile) || {}).class;
      const opened = lookOpen(cls, tier);
      const latest = lookLatest(cls, tier);
      for (const part of ["top", "hair", "prop", "color"]) {
        const val = have[part];
        if (val === "none" && (part === "prop" || part === "color")) continue;
        if (val && tables[part] && val in tables[part] && opened[part].has(val)) {
          look[part] = val;
          continue;
        }
        if (part in latest) look[part] = latest[part];
      }
      return look;
    }

    function lookGrid(look) {
      const grid = spriteGrid(`base/${look.base}`);
      const color = look.color ? T.look.colors[look.color].color : null;
      for (const part of LAYERS) {
        if (!look[part]) continue;
        spriteGrid(`${part}/${look[part]}`, part === "top" ? color : null).forEach((row, y) => row.forEach((c, x) => {
          if (c) grid[y][x] = c;
        }));
      }
      return grid;
    }

    function titleOf(cls, tier) {
      const titles = (T.classes[cls] || {}).titles || [];
      return titles.length ? titles[Math.min(tier, titles.length - 1)] : null;
    }

    function levelCost(level) {
      let cost = 0;
      for (const [start, pts] of Object.entries(T.level).map(([k, v]) => [parseInt(k, 10), parseInt(v, 10)]).sort((a, b) => a[0] - b[0])) {
        if (level >= start) cost = pts;
      }
      return cost;
    }

    // suit.py CTRL_RE 와 같은 문자. 줄을 가르는 제어 문자가 값에 섞여 슬롯 파일에 새 키가 생기지 않게 빈칸으로 바꾼다.
    const CTRL = /[\x00-\x1f\x7f-\x9f\u{2028}\u{2029}\u{feff}]/gu;

    function cleanText(s) {
      return String(s).replace(CTRL, " ").replace(/"/g, "”").split(/\s+/).filter(Boolean).join(" ");
    }

    function quote(v) {
      v = String(v).replace(CTRL, " ");
      if (v === "" || v !== v.trim() || /[,:#[\]{}'"]/.test(v)) return '"' + v.replace(/"/g, "”") + '"';
      return v;
    }

    function one(v) {
      if (Array.isArray(v)) return "[" + v.map(quote).join(", ") + "]";
      if (v && typeof v === "object") return "{" + Object.entries(v).map(([k, x]) => `${k}: ${one(x)}`).join(", ") + "}";
      return quote(v);
    }

    // suit.py dump_yaml 과 같은 꼴. 빈 절은 건너뛴다.
    function dumpYaml(data, head) {
      const lines = [head === undefined ? T.profileHead : head, ""];
      for (const [section, body] of Object.entries(data)) {
        if (!body || (typeof body === "object" && !Object.keys(body).length)) continue;
        if (typeof body !== "object" || Array.isArray(body)) {
          lines.push(`${section}: ${one(body)}`, "");
          continue;
        }
        lines.push(`${section}:`);
        for (const [k, v] of Object.entries(body)) lines.push(`  ${k}: ${one(v)}`);
        lines.push("");
      }
      return lines.join("\n");
    }

    return { resolve, compose, review, label, SRC, lookOf, lookGrid, openedAt, titleOf, levelCost, cleanText, dumpYaml };
  }
  if (typeof module !== "undefined" && module.exports) module.exports = make;
  else root.ThemeCore = make;
})(typeof self !== "undefined" ? self : this);
