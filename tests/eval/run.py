#!/usr/bin/env python3
"""글 평가 실행기. docs-suit 를 켜고 쓴 글과 끄고 쓴 글, 사람 글을 같은 수치로 재서 견준다.

  python3 tests/eval/run.py gen --mode on,off            # 케이스 묶음을 켜고 끄고 쓴다. 사용료가 든다
  python3 tests/eval/run.py fetch katfish                # 연구 데이터를 받아 사람 글과 LLM 글로 나눈다
  python3 tests/eval/run.py measure                      # 모은 글을 모두 잰다
  python3 tests/eval/run.py report [--record]            # 보고서를 낸다. --record 면 tests/eval/results/ 에 남긴다

글과 기록은 저장소 밖 ~/.cache/docs-suit-eval/ 에 둔다. DOCS_SUIT_EVAL 로 바꿀 수 있다. 사람 글 원문과 라이선스가
없는 연구 데이터를 공개 저장소에 넣지 않기 위해서다. 저장소에는 잰 수치와 보고서만 남긴다.
에이전트가 도는 작업 폴더는 시스템 임시 폴더에 따로 만든다. 홈 폴더 아래에서 돌리면 Claude Code 가 상위 폴더의
~/.claude/CLAUDE.md 와 개인 스킬을 지침으로 실어서, 끈 글까지 그 사람의 문체 지침을 받고 쓴다.
사용료는 spent.jsonl 에 쌓는다. --cap 을 주면 합이 그 값에 닿은 뒤 새 글을 쓰지 않고, 동시에 도는 글이 있어 --jobs 건만큼 넘을 수 있다.
"""
import argparse
import html
import importlib.util
import json
import math
import os
import random
import re
import shutil
import statistics
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = Path(os.environ.get("DOCS_SUIT_EVAL", Path.home() / ".cache" / "docs-suit-eval"))


def scratch(prefix):
    """에이전트를 돌릴 빈 폴더. 홈 폴더 밖이어야 상위 폴더의 개인 지침이 실리지 않는다."""
    d = Path(tempfile.mkdtemp(prefix=prefix))
    if str(d.resolve()).startswith(str(Path.home().resolve()) + os.sep):
        sys.exit(f"작업 폴더가 홈 폴더 아래에 생겼다: {d}. TMPDIR 을 홈 폴더 밖으로 두고 다시 돌린다")
    return d


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 동작 테스트 실행기의 에이전트 호출과 본문 뽑기를 그대로 쓴다. 켠 글은 동작 테스트와 같은 조건에서 쓴다.
ar = load("agent_run", ROOT / "tests" / "agent" / "run.py")
suit = ar.suit
th = ar.th

# 글쓰기 요청만 고른다. 화면, 파일 만들기, 겹침, 문체 배우기, 다듬기처럼 본문 말고 다른 것을 재는 케이스는 뺀다.
SKIP_KEYS = ("expect", "file", "files", "samples", "folder", "revise", "page", "serve_kind", "call")


def plain_cases():
    return [c for c in ar.CASES if isinstance(c.get("kind"), str) and c["kind"] and not any(c.get(k) for k in SKIP_KEYS)]


# ---------------------------------------------------------------- 사용료
LOCK = threading.Lock()


def spent():
    log = DATA / "spent.jsonl"
    return sum(json.loads(x)["cost"] for x in log.read_text(encoding="utf-8").splitlines()) if log.exists() else 0.0


def pay(cost, what):
    with LOCK:
        DATA.mkdir(parents=True, exist_ok=True)
        with open(DATA / "spent.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"date": date.today().isoformat(), "what": what, "cost": cost}, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- 글 쓰기
def from_reply(reply):
    """답에서 본문만 뽑는다. 동작 테스트의 doc_text 는 200자 넘는 코드 블록을 본문으로 집어서, 그림 블록이 든 글에서
    그림만 남긴다. 여기서는 코드 블록이 답의 대부분일 때만 그 블록을 쓰고, --- 로 나뉜 답은 안내 조각을 걷는다.
    파일 쓰기가 막힌 에이전트가 안내 문단과 맺음 문단 사이에 본문을 넣어 답하기 때문이다."""
    reply = re.sub(r"^성장:.*$", "", reply, flags=re.M).strip()
    fence = max(re.findall(r"```[a-z]*\n(.*?)```", reply, re.S), key=len, default="")
    if len(fence) >= 0.7 * len(reply):
        return fence
    # 가장 긴 조각을 본문으로 잡고, 그보다 훨씬 짧고 제목이 없는 조각은 안내로 보고 걷는다.
    # 제목이 있는 조각은 본문 안의 구분선으로 나뉜 절이라 남긴다
    parts = re.split(r"^---\s*$", reply, flags=re.M)
    core = max(len(p.strip()) for p in parts)
    keep = [p for p in parts if len(p.strip()) == core or re.search(r"^#", p, re.M) or len(p.strip()) >= 0.4 * core]
    return "---".join(keep)


def asks_only(reply):
    """질문만 하고 멈춘 답인가. 동작 테스트의 only_asks 는 [확인 필요] 표시가 없는 글을 질문으로 보기 쉬워서,
    끈 글처럼 그 표시를 쓰지 않는 글에는 맞지 않는다. 여기서는 세 줄 넘는 답에서 본문 줄의 40% 넘게 물음표가 들었거나,
    300자 안쪽 답이 자료를 받으면 쓰겠다고 하면 질문으로 본다. 메일처럼 짧은 본문도 "알려 주시면" 은 쓰므로 그 말로는 가르지 않는다."""
    body = from_reply(reply)
    # 인용 블록에 본문을 담는 글이 있어서 인용 줄도 센다. 제목이 있으면 질문이 아니라 본문이다
    lines = [ln for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith(("|", "```"))]
    if not lines:
        return True
    if any(ln.lstrip().startswith("#") for ln in lines):
        return False
    asked = sum(1 for ln in lines if "?" in ln) / len(lines)
    return (asked >= 0.4 and len(lines) >= 3) or (len(body) < 300 and bool(re.search(r"(?:쓰|작성하|써 드리|정리해 드리|만들어 드리)겠", body)))


def body_of(agent, tmp, on):
    """에이전트가 쓴 본문. 켠 글은 check 에 넘긴 본문을 먼저 쓰고, 없으면 두 글 모두 같은 방법으로 뽑는다.
    작업 폴더에 만든 .md 가 있으면 그것을, 없으면 질문만 한 답을 빼고 답에서 뽑는다."""
    ts = [(tmp / n).read_text(encoding="utf-8") for n in ("transcript.jsonl", "transcript-2.jsonl") if (tmp / n).exists()]
    doc = ar.checked_body(ts) if on else ""
    made = [f for f in (tmp / "proj").rglob("*.md") if not {".agents", ".claude"} & set(f.parts) and f.name not in ar.GUIDE_FILES]
    if not doc and made:
        doc = max(made, key=lambda f: f.stat().st_size).read_text(encoding="utf-8")
    if not doc:
        replies = [ar.AGENTS[agent]["meta"](t)["reply"] for t in ts]
        doc = max((from_reply(r) for r in replies if not asks_only(r)), key=lambda d: len(suit.body_lines(d)), default="")
    return doc.strip() + "\n" if doc.strip() else ""


def write_one(agent, item, base, model, on):
    """요청 하나를 쓴다. 켠 글은 동작 테스트처럼 스킬과 시험 프로필을 두고, 끈 글은 빈 작업 폴더에서 쓴다.
    질문만 하고 멈추면 동작 테스트와 같은 말로 한 번 재촉한다."""
    if on:
        tmp, proj, env = ar.prepare(agent, item, base)
    else:
        tmp = base / item["id"]
        proj = tmp / "proj"
        proj.mkdir(parents=True)
        env = dict(os.environ, BROWSER="true")
    t0 = time.time()
    out, err = ar.invoke(agent, item["ask"], tmp, proj, env, model, keep=True)
    (tmp / "transcript.jsonl").write_text(out, encoding="utf-8")
    first = ar.AGENTS[agent]["meta"](out)
    cost = first["cost"]
    if first["session"] and not (on and ar.checked_body([out])) and asks_only(first["reply"]):
        env2 = dict(env, DOCS_SUIT_LOG=str(tmp / "calls-2.jsonl")) if on else env
        out2, _ = ar.invoke(agent, ar.FOLLOWUP, tmp, proj, env2, model, first["session"], keep=True)
        (tmp / "transcript-2.jsonl").write_text(out2, encoding="utf-8")
        cost += ar.AGENTS[agent]["meta"](out2)["cost"]
    meta = {"id": item["id"], "kind": item["kind"], "mode": "on" if on else "off", "agent": agent,
            "model": first["model"], "cost": round(cost, 4), "sec": round(time.time() - t0),
            "followup": (tmp / "transcript-2.jsonl").exists(),
            "set": "pairs" if item.get("pair") else "cases", "pair": item.get("pair")}
    if on:
        meta["compose"] = first_compose(tmp)
    return body_of(agent, tmp, on), meta


def first_compose(tmp):
    """켠 글이 처음 부른 compose 의 인자. 어떤 문서 종류와 독자로 조립했는지 보고서에 보인다."""
    for name in ("calls.jsonl", "calls-2.jsonl"):
        f = tmp / name
        for line in (f.read_text(encoding="utf-8").splitlines() if f.exists() else []):
            argv = json.loads(line).get("argv") or []
            if argv[:1] == ["compose"]:
                return argv[1:]
    return None


def cmd_gen(a):
    items = plain_cases() if a.set == "cases" else [json.loads(x) for x in (DATA / "pairs.jsonl").read_text(encoding="utf-8").splitlines()]
    if a.only:
        items = [c for c in items if c["id"] in a.only.split(",")]
    run = a.run or f"{date.today().isoformat()}-{a.set}"
    out = DATA / "gen" / run
    work = scratch(f"docs-suit-eval-{run}-")
    jobs = [(item, mode) for mode in a.mode.split(",") for item in items
            if a.redo or not (out / mode / f"{item['id']}.md").exists()]
    print(f"{a.set} 묶음 {len(items)}건, 쓸 글 {len(jobs)}편, 지금까지 쓴 사용료 {spent():.2f}달러, 상한 {a.cap or '없음'}{'달러' if a.cap else ''}, "
          f"글은 {out}, 작업 폴더는 {work}", file=sys.stderr)

    def job(pair):
        item, mode = pair
        if a.cap and spent() >= a.cap:
            return f"건너뜀 {mode}/{item['id']}: 사용료 상한"
        shutil.rmtree(work / mode / item["id"], ignore_errors=True)
        (work / mode).mkdir(parents=True, exist_ok=True)
        doc, meta = write_one(a.agent, item, work / mode, a.model, mode == "on")
        pay(meta["cost"], f"{run}/{mode}/{item['id']}")
        (out / mode).mkdir(parents=True, exist_ok=True)
        (out / mode / f"{item['id']}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        if doc:
            (out / mode / f"{item['id']}.md").write_text(doc, encoding="utf-8")
        return f"{'씀' if doc else '본문 없음'} {mode}/{item['id']} {meta['cost']:.2f}달러 {meta['sec']}초"

    with ThreadPoolExecutor(a.jobs) as ex:
        for line in ex.map(job, jobs):
            print(line, file=sys.stderr)
    print(f"사용료 합 {spent():.2f}달러", file=sys.stderr)


# ---------------------------------------------------------------- 사람 글과 연구 데이터
KATFISH = "https://raw.githubusercontent.com/Shinwoo-Park/detecting_llm_generated_korean_text_through_linguistic_analysis/main/katfish_dataset/"
KATFISH_KIND = {"abstract": "abstract", "essay": "essay"}


def fetch_katfish():
    """KatFish 의 논문 초록과 논설문을 받아 글쓴이별로 나눈다. 저장소에 라이선스 파일이 없어 로컬 검증에만 쓴다.
    사람 글은 human/katfish-<장르>, LLM 글은 llm/katfish-<장르> 에 둔다."""
    raw = DATA / "raw" / "katfish"
    raw.mkdir(parents=True, exist_ok=True)
    for genre, kind in KATFISH_KIND.items():
        f = raw / f"{genre}.jsonl"
        if not f.exists():
            urllib.request.urlretrieve(KATFISH + f.name, f)
        for i, line in enumerate(x for x in f.read_text(encoding="utf-8").splitlines() if x.strip()):
            row = json.loads(line)
            group = "human" if row["written_by"] == "human" else "llm"
            d = DATA / group / f"katfish-{genre}"
            d.mkdir(parents=True, exist_ok=True)
            # 원문은 문단 구분 없이 한 줄이라 그대로 둔다. 문단 수치는 이 묶음에서 견주지 않는다
            (d / f"{i}.md").write_text(row["text"].strip() + "\n", encoding="utf-8")
            (d / f"{i}.json").write_text(json.dumps({"kind": kind, "source": "katfish", "written_by": row["written_by"]},
                                                    ensure_ascii=False), encoding="utf-8")
    for group in ("human", "llm"):
        for genre in KATFISH_KIND:
            print(f"{group}/katfish-{genre}: {len(list((DATA / group / f'katfish-{genre}').glob('*.md')))}편", file=sys.stderr)


KOREA = "https://www.korea.kr"
UA = {"User-Agent": "Mozilla/5.0 (docs-suit eval; https://github.com/dodokim-lab/docs-suit)"}
# 보도자료 본문 뒤에 붙는 문의 문단과 참고 자료. 여기서 본문을 끊는다. 담당자 이름과 전화번호가 이 부분과 머리 표에 있다
PRESS_TAIL = re.compile(r"^\s*(?:○\s*)?[【\[<]?\s*(?:참고\s*\d|붙임|별첨|첨부\s*(?:[:：]|\d)|※\s*참고)|연락\s*주시기\s*바랍니다|문의\s*[:：]|^\s*끝\.?\s*$")
# 정부 문서가 머리표로 쓰는 글자. 한글 자모 ㅇ 과 가운뎃점, 한글 프로그램의 사용자 정의 글리프를 동그라미로 바꿔 목록으로 센다
GOV_BULLET = re.compile(r"^(?:ㅇ|[･・ㆍ∙]|[\ue000-\uf8ff\U000f0000-\U000ffffd])\s*")


def get(url, tries=5):
    for i in range(tries):
        time.sleep(0.5 * 2 ** i)  # 공공 서버에 몰아서 요청하지 않고, 서버 오류면 점점 길게 쉬고 다시 묻는다
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if (e.code < 500 and e.code != 429) or i == tries - 1:
                raise
            if e.code == 429:  # 요청 수 제한이면 서버가 알려 준 만큼, 없으면 30초 넘게 기다린다
                time.sleep(int(e.headers.get("Retry-After") or 30 * 2 ** i))


def press_body(text):
    """hwpx 에서 뽑은 보도자료 글의 본문. 표 줄은 머리 상자와 담당자 표, 붙임 표라 걷고, 문의 문단이나 참고 자료가
    나오면 그 뒤를 버린다."""
    out = []
    for ln in text.splitlines():
        ln = GOV_BULLET.sub("○ ", ln.strip())
        if PRESS_TAIL.search(ln):
            if out:
                break
            continue  # 본문 앞의 담당자 줄
        if re.search(r"\s끝\.?\s*$", ln):  # 본문 마지막 문장 뒤의 "끝." 표시
            ln = re.sub(r"\s끝\.?\s*$", "", ln)
            out.append(ln)
            break
        if re.match(r"※.*사진", ln):
            continue
        if ln and not ln.startswith("|"):
            # 큰 네모는 문단 머리표라 줄글 문단이면 걷는다. 작은 동그라미와 붙임표는 개조식 항목이라 목록으로 둔다
            if ln.startswith("□") and re.search(r"다\.\s*$", ln):
                ln = ln.lstrip("□ ")
            out.append(ln)
    return "\n\n".join(out)


def fetch_korea_press(want=30):
    """정책브리핑 보도자료를 2022년 1월부터 11월까지 달마다 고루 받는다. 공공누리 제1유형이고 ChatGPT 공개 전 글이다.
    본문이 hwpx 첨부에만 있어 엔진의 hwpx 추출기로 읽는다. 문장 수치를 잴 줄글 문장이 여섯 개 넘는 글만 고른다.
    줄글 비율로 거르면 개조식이 흔한 보도자료 가운데 줄글이 많은 글만 남아 사람 글이 치우친다. 원본 hwpx 는 raw/korea-press 에 두고 해시를 남긴다."""
    import hashlib
    raw = DATA / "raw" / "korea-press"
    out = DATA / "human" / "korea-press"
    raw.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    have = len(list(out.glob("*.md")))
    per_month = -(-want // 11)
    for month in range(1, 12):
        got = 0
        end = "2022-11-29" if month == 11 else f"2022-{month:02d}-28"
        ids = []
        for n in (2, 3, 4):  # 첫 쪽은 그 달 말일의 글이 몰려 있어 둘째 쪽부터 본다
            page = get(f"{KOREA}/briefing/pressReleaseList.do?period=direct&startDate=2022-{month:02d}-01&endDate={end}&pageIndex={n}")
            ids += re.findall(r"pressReleaseView\.do\?newsId=(\d+)", page.decode("utf-8", "replace"))
        ids = list(dict.fromkeys(ids))
        for nid in ids:
            if got >= per_month or have >= want:
                break
            if (out / f"{nid}.md").exists():
                continue
            view = get(f"{KOREA}/briefing/pressReleaseView.do?newsId={nid}").decode("utf-8", "replace")
            if "공공누리 제1유형" not in view and "자유이용허락 1유형" not in view:
                continue
            files = re.findall(r'download\.do\?fileId=(\d+)&amp;tblKey=(\w+)">\s*(?:<img[^>]*>)?([^<]*?\.hwpx)', view)
            title = re.search(r"<title>([^<]*)</title>", view)
            day = re.search(r"(2022\.\d{2}\.\d{2})", view)
            if not files or not day:
                continue
            fid, tbl, _ = files[0]
            f = raw / f"{nid}.hwpx"
            if not f.exists():
                f.write_bytes(get(f"{KOREA}/common/download.do?fileId={fid}&tblKey={tbl}"))
            try:
                text, _ = suit._doc_text(f, ".hwpx")
            except ValueError:
                continue
            body = press_body(text)
            sents = sum(len(r) for r in suit.sentences(body))
            if not (600 <= len(body) <= 3000 and sents > 6):
                continue
            name = re.sub(r"\s+-\s+보도자료\s*$", "", title.group(1).split("|")[0].strip() if title else "").replace("&quot;", '"')
            (out / f"{nid}.md").write_text(f"# {name}\n\n{body}\n", encoding="utf-8")
            (out / f"{nid}.json").write_text(json.dumps({
                "kind": "press-release", "label": "보도자료", "source": "korea-press", "date": day.group(1),
                "url": f"{KOREA}/briefing/pressReleaseView.do?newsId={nid}", "license": "공공누리 제1유형(출처표시), 정책브리핑",
                "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}, ensure_ascii=False), encoding="utf-8")
            got += 1
            have += 1
        print(f"2022-{month:02d}: {got}편, 모두 {have}편", file=sys.stderr)


# 정책브리핑에서 본문이 HTML 에 든 글. 연설문은 공공누리가 붙지 않아 저작권법 제24조(정치적 연설 등의 이용)에 기댄다
KOREA_HTML = {
    "korea-speech": {"list": "briefing/speechList.do", "view": "briefing/speechView.do", "kind": "script", "label": "연설문",
                     "license": "저작권법 제24조, 정책브리핑 연설문"},
    "korea-reporter": {"list": "news/reporterList.do", "view": "news/reporterView.do", "kind": "blog", "label": "정책기자단 기사",
                       "license": "공공누리 제1유형(출처표시), 정책브리핑 정책기자단", "kogl": True},
}


def korea_html_body(view):
    """정책브리핑 글 화면에서 본문만 뽑는다. 사진 표와 설명, 기자 이름과 메일 줄, 출처 줄은 걷는다.
    <br> 두 번은 문단을 나누고 한 번은 같은 문단 안의 줄이라 빈칸으로 잇는다."""
    i = view.find('class="view_cont"')
    if i < 0:
        return ""
    seg = view[view.find(">", i) + 1:]
    seg = seg[:min(x for x in (seg.find('class="article_footer"'), seg.find('class="source"'), len(seg)) if x >= 0)]
    seg = re.sub(r"<[^<>]*$", "", seg)  # 끊은 자리에 걸친 태그 조각
    seg = re.sub(r"<table.*?</table>", "\n\n", seg, flags=re.S | re.I)
    seg = re.sub(r"(?:<br\s*/?>\s*){2,}|</p>|</div>|</h\d>", "\n\n", seg, flags=re.I)
    seg = re.sub(r"<br\s*/?>", " ", seg, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", seg)).replace("\xa0", " ")
    paras = []
    for para in re.split(r"\n\s*\n", text):
        para = " ".join(para.split())
        if not para or "@" in para or "정책기자단" in para or para.startswith("<자료출처"):
            continue  # 기자 이름과 메일, 출처 줄
        paras.append(GOV_BULLET.sub("○ ", para))
    return "\n\n".join(paras)


def fetch_korea_html(source, want=30):
    """정책브리핑의 연설문이나 정책기자단 글을 2022년 1월부터 11월까지 달마다 고루 받는다. 줄글 문장이 여섯 개 넘고
    600~3000자인 글만 고른다. 정책기자단 글은 공공누리 제1유형이 붙은 글만 받는다."""
    cfg = KOREA_HTML[source]
    out = DATA / "human" / source
    out.mkdir(parents=True, exist_ok=True)
    have = len(list(out.glob("*.md")))
    per_month = -(-want // 11)
    for month in range(1, 12):
        got = 0
        end = "2022-11-29" if month == 11 else f"2022-{month:02d}-28"
        ids = []
        for n in (1, 2, 3):
            page = get(f"{KOREA}/{cfg['list']}?period=direct&startDate=2022-{month:02d}-01&endDate={end}&pageIndex={n}")
            ids += re.findall(re.escape(cfg["view"].split("/")[-1]) + r"\?newsId=(\d+)", page.decode("utf-8", "replace"))
        for nid in dict.fromkeys(ids):
            if got >= per_month or have >= want:
                break
            if (out / f"{nid}.md").exists():
                continue
            view = get(f"{KOREA}/{cfg['view']}?newsId={nid}").decode("utf-8", "replace")
            day = re.search(r"(2022\.\d{2}\.\d{2})", view)
            if not day or (cfg.get("kogl") and "자유이용허락 1유형" not in view and "공공누리 제1유형" not in view):
                continue
            body = korea_html_body(view)
            sents = sum(len(r) for r in suit.sentences(body))
            if not (600 <= len(body) <= 3000 and sents > 6):
                continue
            title = re.search(r"<title>([^<]*)</title>", view)
            name = html.unescape(re.sub(r"\s+-\s+[^-|]+$", "", title.group(1).split("|")[0].strip()) if title else "")
            (out / f"{nid}.md").write_text(f"# {name}\n\n{body}\n", encoding="utf-8")
            (out / f"{nid}.json").write_text(json.dumps({
                "kind": cfg["kind"], "label": cfg["label"], "source": source, "date": day.group(1),
                "url": f"{KOREA}/{cfg['view']}?newsId={nid}", "license": cfg["license"]}, ensure_ascii=False), encoding="utf-8")
            got += 1
            have += 1
        print(f"{source} 2022-{month:02d}: {got}편, 모두 {have}편", file=sys.stderr)


GEC_ROWS = "https://datasets-server.huggingface.co/rows?dataset=jaban%2Ferr_spelling_kor&config=default&split=val"


def fetch_gec():
    """맞춤법 교정 데이터의 검증 묶음 4,300쌍을 받는다. 틀린 문장(err)과 고친 문장(cor)의 짝이다. 올린 사람은 Apache-2.0 이라고
    적었지만 원출처를 확인하지 못해 로컬 검증에만 쓴다. 신청서가 필요한 Standard Korean GEC 말뭉치를 받기 전까지 쓴다."""
    out = DATA / "raw" / "gec" / "val.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    while True:
        page = json.loads(get(f"{GEC_ROWS}&offset={len(rows)}&length=100"))
        rows += [{"err": r["row"]["err"], "cor": r["row"]["cor"]} for r in page["rows"]]
        if not page["rows"] or len(rows) >= page.get("num_rows_total", 0):
            break
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"맞춤법 교정 짝 {len(rows)}쌍을 {out} 에 받았다", file=sys.stderr)


# 출처마다 따로 둔 수집기. 파일 이름과 함수 이름이다. GitHub 은 gh 로 로그인해 두어야 한다
SOURCES = {"github-pr": ("github", "fetch_github_pr"), "github-readme": ("github", "fetch_github_readme"),
           "kdca-health": ("public", "fetch_kdca_health"), "seoul-report": ("public", "fetch_seoul_report")}


def load_source(name):
    spec = importlib.util.spec_from_file_location(f"eval_source_{name}", HERE / "sources" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.DATA, mod.RAW_DIR = DATA, str(DATA / "raw")
    return mod


def cmd_fetch(a):
    if a.source in KOREA_HTML:
        return fetch_korea_html(a.source)
    if a.source in SOURCES:
        module, func = SOURCES[a.source]
        return getattr(load_source(module), func)(DATA / "human" / a.source, want=30)
    {"katfish": fetch_katfish, "korea-press": fetch_korea_press, "gec": fetch_gec}[a.source]()


# ---------------------------------------------------------------- 짝 요청
def batchim(word):
    ch = word.strip()[-1:]
    return bool(ch) and "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 != 0


PAIR_PROMPT = """아래 글은 사람이 쓴 {label_is}. 이 글을 보지 못한 사람이 AI 에게 같은 문서를 써 달라고 할 때 보낼 요청문을 만들어라.

- 요청문은 "{label_obj} 써 줘" 처럼 시작하고, 글에 나온 사실을 빠짐없이 목록으로 넣는다. 사실은 수치, 이름, 날짜, 대상, 방법, 결과 같은 것이다.
- 글의 문장과 표현, 문단 순서는 옮기지 않는다. 사실만 낱말 단위로 적는다.
- 누가 읽을 글인지와 대략의 분량(공백 포함 몇 자)을 한 줄씩 적는다.
- 요청문만 출력한다. 앞뒤에 설명을 붙이지 않는다.

<글>
{text}
</글>"""


def ask_claude(prompt, model):
    """도구 없이 한 번 묻는다. 동작 테스트처럼 사용자 설정과 MCP 를 끄고 돌린다."""
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--setting-sources", "project,local", "--strict-mcp-config",
           "--settings", '{"disableAllHooks": true}', "--model", model]
    p = ar.subprocess.run(cmd, stdin=ar.subprocess.DEVNULL, capture_output=True, text=True, timeout=300,
                          cwd=scratch("docs-suit-eval-ask-"))
    o = json.loads(p.stdout)
    return o.get("result", "").strip(), o.get("total_cost_usd", 0.0)


def cmd_pairs(a):
    """사람 글마다 그 글의 사실로 같은 문서를 써 달라는 요청을 만든다. 만든 요청은 gen --set pairs 가 쓴다.
    글은 이름순으로 고르고, 이미 만든 요청은 건너뛴다."""
    src = DATA / "human" / a.source
    files = sorted(src.glob("*.md"), key=lambda f: (len(f.stem), f.stem))[:a.limit]
    log = DATA / "pairs.jsonl"
    done = {json.loads(x)["id"] for x in log.read_text(encoding="utf-8").splitlines()} if log.exists() else set()
    todo = [f for f in files if f"{a.source}-{f.stem}" not in done]
    print(f"{a.source} 에서 {len(files)}편을 골랐고 새로 만들 요청 {len(todo)}건, 사용료 합 {spent():.2f}달러", file=sys.stderr)

    def one(f):
        if a.cap and spent() >= a.cap:
            return None
        meta = json.loads(f.with_suffix(".json").read_text(encoding="utf-8"))
        label = meta.get("label") or th.kinds[meta["kind"]]["label"]
        prompt = PAIR_PROMPT.format(label_is=label + ("이다" if batchim(label) else "다"),
                                    label_obj=label + ("을" if batchim(label) else "를"), text=f.read_text(encoding="utf-8"))
        ask, cost = ask_claude(prompt, a.model)
        pay(cost, f"pairs/{a.source}/{f.stem}")
        return {"id": f"{a.source}-{f.stem}", "kind": meta["kind"], "ask": ask, "pair": {"source": a.source, "id": f.stem}}

    with ThreadPoolExecutor(a.jobs) as ex:
        for row in ex.map(one, todo):
            if row and row["ask"]:
                with LOCK, open(log, "a", encoding="utf-8") as out:
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"요청 {len(done) + len(todo)}건, 사용료 합 {spent():.2f}달러", file=sys.stderr)


# ---------------------------------------------------------------- 재기
WINDOW = 100  # 품사 다양성을 재는 구간의 형태소 수


def kiwi_metrics():
    """품사 조합 다양성. Kiwi 가 있을 때만 잰다. 없으면 이 수치를 건너뛴다."""
    try:
        from kiwipiepy import Kiwi
    except ImportError:
        return None
    kiwi = Kiwi()

    def pos(doc):
        # 서로 다른 n-gram 의 비율은 글이 길수록 작아진다. 형태소 WINDOW 개씩 잘라 구간마다 재고 평균을 내서
        # 길이가 다른 글끼리 견줄 수 있게 한다. 한 구간도 안 되는 짧은 글은 재지 않는다
        flat = " ".join(s for row in suit.sentences(doc) for s in row)
        tags = [t.tag for t in kiwi.tokenize(flat)] if flat else []
        chunks = [tags[i:i + WINDOW] for i in range(0, len(tags) - WINDOW + 1, WINDOW)]
        out = {}
        for n in (2, 3):
            ratios = [len({tuple(c[i:i + n]) for i in range(len(c) - n + 1)}) / (len(c) - n + 1) for c in chunks]
            out[f"pos{n}_distinct"] = round(sum(ratios) / len(ratios), 3) if ratios else None
        return out
    return pos


def docs():
    """(묶음, 이름, 경로, 메타). 묶음은 on, off, human, llm 가운데 하나다."""
    for group in ("human", "llm"):
        for d in sorted((DATA / group).glob("*")):
            for f in sorted(d.glob("*.md")):
                yield group, d.name, f, json.loads(f.with_suffix(".json").read_text(encoding="utf-8"))
    for run in sorted((DATA / "gen").glob("*")):
        for mode in ("on", "off"):
            for f in sorted((run / mode).glob("*.md")):
                yield mode, run.name, f, json.loads(f.with_suffix(".json").read_text(encoding="utf-8"))


PLACEHOLDER = re.compile(r"\[확인 필요[^\]]*\]")
NUMBER = re.compile(r"(?<![\d.])\d{2,}(?:[.,]\d+)?")  # 두 자리 넘는 수. 목록 번호와 절 번호는 세지 않는다


def cmd_measure(a):
    # 생성한 글이 받은 요청. 요청에 없던 숫자를 셀 때 쓴다
    asks = {c["id"]: c["ask"] for c in plain_cases()}
    pairs = DATA / "pairs.jsonl"
    if pairs.exists():
        asks.update({r["id"]: r["ask"] for r in map(json.loads, pairs.read_text(encoding="utf-8").splitlines())})
    pos = kiwi_metrics()
    if pos is None:
        print("Kiwi 가 없어 품사 조합 다양성은 건너뛴다. pip install kiwipiepy 로 깔면 함께 잰다", file=sys.stderr)
    rows = []
    for group, source, f, meta in docs():
        # 엔진은 인용 블록을 예문으로 보고 걷지만, 면접 답변처럼 인용 블록에 본문을 담는 글이 있다.
        # 평가에서는 모든 묶음에서 인용 표시만 걷고 쓴 사람의 글로 잰다
        doc = re.sub(r"^[ \t]*>[ \t]?", "", f.read_text(encoding="utf-8"), flags=re.M)
        # 켠 글은 모르는 곳을 [확인 필요] 로 비우고 끈 글은 지어서 채운다. 자리표시가 문장 길이와 품사 수치에 섞이지 않게
        # 모든 묶음에서 "미정" 한 낱말로 바꿔 재고, 개수와 요청에 없던 숫자는 내용 수치로 따로 센다
        holes = len(PLACEHOLDER.findall(doc))
        doc = PLACEHOLDER.sub("미정", doc)
        m = suit.measure(doc, th, meta.get("kind"))
        m["holes_per_1k"] = round(holes * 1000 / m["chars"], 3) if m["chars"] else None
        if asks.get(meta.get("id")) is not None and group in ("on", "off"):
            m["new_numbers"] = len(set(NUMBER.findall(suit.plain_text(doc))) - set(NUMBER.findall(asks[meta["id"]])))
        if pos:
            m.update(pos(doc))
        # 패턴마다 걸린 횟수와 check 가 실제로 보일 패턴. 사람 글에 잘못 걸리는 비율을 잴 때 쓴다
        hits = {k: v for k, v in suit.tell_hits(th, doc, meta.get("kind")).items() if v}
        shown = [n for n, *_ in suit.tells_found(th, doc, {}, meta.get("kind"))]
        rows.append({"group": group, "source": source, "id": f.stem, "kind": meta.get("kind"), "m": m,
                     "tells": hits, "shown": shown, "set": meta.get("set", "cases"), "pair": meta.get("pair"),
                     "compose": meta.get("compose"), "suspect": suit.learn_sample(th, f.stem, doc, False)["suspect"]})
    (DATA / "measures.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    count = {}
    for r in rows:
        count[r["group"]] = count.get(r["group"], 0) + 1
    print(f"잰 글 {len(rows)}편: " + ", ".join(f"{k} {v}" for k, v in sorted(count.items())), file=sys.stderr)


# ---------------------------------------------------------------- 보고서
LABEL = {"chars": "글자 수", "lines_per_1k": "1000자당 줄", "blocks_per_1k": "1000자당 덩어리", "sentences": "문장 수",
         "sent_mean": "문장 평균 길이", "sent_median": "문장 길이 중앙값", "sent_cv": "문장 길이 변동계수",
         "sent_over80": "80자 넘는 문장 비율", "sent_under20": "20자 안쪽 문장 비율", "paras": "문단 수",
         "para_sents": "문단당 문장", "para_chars": "문단 평균 길이", "one_sent_paras": "한 문장 문단 비율",
         "list_share": "목록 비율", "table_share": "표 비율", "heading_share": "제목 비율", "chars_per_heading": "제목당 글자",
         "comma_per_sent": "문장당 쉼표", "comma_sents": "쉼표 든 문장 비율", "connective_comma": "연결어미 뒤 쉼표 비율",
         "ai_tells_per_1k": "1000자당 AI 버릇", "spelling": "맞춤법 패턴", "spacing": "띄어쓰기 패턴",
         "pos2_distinct": "품사 2-gram 다양성", "pos3_distinct": "품사 3-gram 다양성",
         "holes_per_1k": "1000자당 [확인 필요]", "new_numbers": "요청에 없던 숫자"}
# 수치의 층. 사람 글과 가까운지는 AI 티 층에서만 센다. 문장 길이와 문단 모양은 가독성 규칙이 정해서, 사람 글이
# 길고 빽빽하게 쓰는 장르에서 사람 글과 멀어져도 나빠진 것으로 보지 않는다. AI 버릇은 적을수록 낫고 사람 글과의 거리로 재지 않는다
LAYER = {"holes_per_1k": "내용", "new_numbers": "내용", "spelling": "표기", "spacing": "표기",
         "sent_cv": "AI 티", "comma_per_sent": "AI 티", "comma_sents": "AI 티", "connective_comma": "AI 티",
         "pos2_distinct": "AI 티", "pos3_distinct": "AI 티", "ai_tells_per_1k": "AI 버릇"}
LAYERS = ("내용", "표기", "AI 버릇", "AI 티", "가독성")
CLOSER = [k for k, v in LAYER.items() if v == "AI 티"]
# KatFish 원문은 문단 구분 없이 한 줄이라 줄과 문단, 목록, 제목 수치를 견주지 않는다
ONE_LINE = ("lines_per_1k", "blocks_per_1k", "paras", "para_sents", "para_chars", "one_sent_paras",
            "list_share", "table_share", "heading_share", "chars_per_heading")


def auc(xs, ys):
    """xs 가 ys 보다 클 확률. 0.5 면 두 묶음을 가르지 못하고, 0 이나 1 에 가까울수록 잘 가른다."""
    if not xs or not ys:
        return None
    gt = sum((x > y) + 0.5 * (x == y) for x in xs for y in ys)
    return gt / (len(xs) * len(ys))


def vals(rows, key):
    return [r["m"][key] for r in rows if r["m"].get(key) is not None]


def paired_p(a_rows, b_rows, key):
    """같은 요청으로 쓴 두 글의 차이가 우연인지 잰다. 차이의 부호를 무작위로 뒤집는 부호 순위 시험의 양쪽 p 다.
    차이가 0 인 짝은 빼고, 남은 짝이 여섯 쌍이 안 되면 재지 않는다. 열두 쌍까지는 모든 부호를 세고, 넘으면 정규 근사를 쓴다."""
    a = {r["pair"]["id"]: r["m"].get(key) for r in a_rows}
    d = [r["m"].get(key) - a[r["pair"]["id"]] for r in b_rows
         if a.get(r["pair"]["id"]) is not None and r["m"].get(key) is not None]
    d = [x for x in d if abs(x) > 1e-12]
    if len(d) < 6:
        return None
    order = sorted(range(len(d)), key=lambda i: abs(d[i]))
    ranks = [0.0] * len(d)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and abs(d[order[j + 1]]) == abs(d[order[i]]):
            j += 1
        for t in range(i, j + 1):
            ranks[order[t]] = (i + j) / 2 + 1
        i = j + 1
    w = sum(r if x > 0 else -r for r, x in zip(ranks, d))
    if len(d) <= 12:
        hits = 0
        for mask in range(1 << len(d)):
            hits += abs(sum(r if mask >> k & 1 else -r for k, r in enumerate(ranks))) >= abs(w) - 1e-9
        return hits / (1 << len(d))
    return math.erfc(abs(w) / math.sqrt(sum(r * r for r in ranks)) / math.sqrt(2))


P_CUT = 0.01  # 수치가 스물여섯 가지라 0.05 로 보면 우연히 한두 가지가 걸린다


def med(xs):
    return statistics.median(xs) if xs else None


def noise_section(rows, keys):
    """같은 요청을 같은 판으로 두 번 쓴 글로 짝 시험을 검증한다. 다시 쓴 글끼리는 차이가 없으니 걸리면 잘못 잡은 것이다."""
    rep = [r for r in rows if r.get("pair") and "repeat" in r["source"]]
    out, false_hits, tests = [], 0, 0
    for source in sorted({r["pair"]["source"] for r in rep}):
        ids = {r["pair"]["id"] for r in rep if r["pair"]["source"] == source}
        mine = [r for r in rows if r.get("pair") and r["pair"]["source"] == source and r["pair"]["id"] in ids]
        pick = lambda grp, again: [r for r in mine if r["group"] == grp and ("repeat" in r["source"]) == again]
        on_runs = sorted({r["source"] for r in mine if r["group"] == "on" and "repeat" not in r["source"]})
        off1, off2, on2 = pick("off", False), pick("off", True), pick("on", True)
        off1 = [r for r in off1 if r["source"] == min(x["source"] for x in off1)] if off1 else []
        on1 = [r for r in pick("on", False) if on_runs and r["source"] == on_runs[-1]]
        if not (off1 and off2 and on1 and on2):
            continue
        lines = ["| 층 | 수치 | 끈 글↔끈 글 다시 | 켠 글↔켠 글 다시 | 끈 글↔켠 글 | 끈↔끈 다시 p | 켠↔켠 다시 p | 끈↔켠 p |", "|---" * 8 + "|"]
        big = []
        for k in sorted(keys, key=lambda k: LAYERS.index(LAYER.get(k, "가독성"))):
            pairs = ((off1, off2), (on1, on2), (off1, on1))
            a = [auc(vals(x, k), vals(y, k)) for x, y in pairs]
            if None in a:
                continue
            ps = [paired_p(x, y, k) for x, y in pairs]
            for q in ps[:2]:
                tests += q is not None
                false_hits += q is not None and q < P_CUT
            big += [LABEL.get(k, k)] if ps[2] is not None and ps[2] < P_CUT else []
            lines.append(f"| {LAYER.get(k, '가독성')} | {LABEL.get(k, k)} | " + " | ".join(f"{max(x, 1 - x):.2f}" for x in a) + " | "
                         + " | ".join("" if q is None else (f"**{q:.3f}**" if q < P_CUT else f"{q:.3f}") for q in ps) + " |")
        out.append(f"### 실행 사이 흔들림 {source}\n\n같은 요청 {len(ids)}건을 같은 판으로 한 번 더 썼다. 다시 쓴 글끼리의 판별력이 흔들림이다. "
                   f"p 는 같은 요청끼리 짝지은 부호 순위 시험이고, {P_CUT} 아래는 굵게 적는다. 끈 글과 켠 글이 이 기준으로 다른 수치가 "
                   f"{len(big)}가지 있다" + (f": {', '.join(big)}." if big else ".") + "\n\n" + "\n".join(lines) + "\n")
    if tests:
        out.insert(0, f"### 짝 시험이 우연을 잘못 잡는 비율\n\n다시 쓴 판끼리 잰 {tests}번 가운데 {false_hits}번이 p<{P_CUT} 로 걸렸다. "
                      "다시 쓴 글끼리는 차이가 없어야 하니 이것이 짝 시험이 우연을 차이로 잘못 읽는 비율이다. "
                      "짝 묶음 절의 \"우연보다 큰 차이\" 는 이 시험으로 센다.\n")
    return out


def comma_cut(xs):
    """사람 글 90% 가 넘지 않는 값을 0.05 단위로 올린다. 0.2 밑으로는 내리지 않는다. defaults.yaml 의 comma 를 정한 방법이다."""
    xs = sorted(xs)
    return max(0.2, math.ceil(xs[min(len(xs) - 1, math.ceil(0.9 * len(xs)) - 1)] * 20 - 1e-9) / 20)


def comma_section(rows):
    """check 의 연결어미 쉼표 문턱을 종류별 사람 글에 대 본다. 반 나눠 잰 값은 한쪽 반으로 정한 문턱이 다른 반에 걸리는 비율이다."""
    ok = lambda r: r["m"].get("connective_comma") is not None and r["m"].get("sentences", 0) >= 5
    human_kind = {r["source"]: r["kind"] for r in rows if r["group"] == "human"}
    lines = ["| 종류 | 사람 글 | 정한 문턱 | 다시 뽑은 문턱 | 사람 글이 0.2 에 닿음 | 정한 문턱에 닿음 | 반 나눠 잰 평균 | 끈 글 | 켠 글 | LLM 글 |",
             "|---" * 10 + "|"]
    rng = random.Random(1)
    for kind in sorted({k for k in human_kind.values() if k in th.kinds}):
        srcs = [s for s, k in human_kind.items() if k == kind]
        h = [r["m"]["connective_comma"] for r in rows if r["group"] == "human" and r["source"] in srcs and ok(r)]
        if len(h) < 10:
            continue
        cut, again = th.comma.get(kind, 0.2), comma_cut(h)
        held = []
        for _ in range(1000):
            xs = h[:]
            rng.shuffle(xs)
            c = comma_cut(xs[:len(xs) // 2])
            held.append(sum(x >= c for x in xs[len(xs) // 2:]) / (len(xs) - len(xs) // 2))
        rate = lambda xs: f"{sum(x >= 0.2 for x in xs) / len(xs):.0%}→{sum(x >= cut for x in xs) / len(xs):.0%} ({len(xs)}편)" if xs else ""
        side = lambda grp: [r["m"]["connective_comma"] for r in rows if r["group"] == grp and ok(r) and (
            r["source"] in srcs if grp == "llm" else r.get("pair") and r["pair"]["source"] in srcs and "repeat" not in r["source"])]
        lines.append(f"| {kind} | {len(h)}편 | {cut:g} | {again:g}{'' if again == cut else ' (다름)'} | "
                     f"{sum(x >= 0.2 for x in h) / len(h):.0%} | {sum(x >= cut for x in h) / len(h):.0%} | {statistics.mean(held):.0%} | "
                     f"{rate(side('off'))} | {rate(side('on'))} | {rate(side('llm'))} |")
    return ["### 연결어미 뒤 쉼표 문턱\n\ncheck 는 연결어미 뒤 쉼표가 든 문장의 비율이 문턱에 닿으면 △ 로 보인다. 문턱은 `defaults.yaml` 의 `comma` 에 있고, "
            "적지 않은 종류는 0.2 다. 다시 뽑은 문턱은 지금 모은 사람 글로 같은 방법을 다시 돌린 값이고, 정한 문턱과 다르면 데이터가 늘어 바뀐 것이다. "
            "끈 글과 켠 글, LLM 글 칸은 0.2 일 때와 정한 문턱일 때 닿는 비율이다.\n\n" + "\n".join(lines) + "\n"]


def composed_kind(row):
    argv = row.get("compose")
    if argv is None:
        return "모름"
    return next((argv[i + 1] for i, v in enumerate(argv[:-1]) if v == "--kind"), "없음")


def fmt(x):
    if x is None:
        return ""
    if isinstance(x, float) and abs(x) >= 100:
        return f"{x:.0f}"
    return f"{x:.3g}" if isinstance(x, float) else str(x)


def table(title, groups, keys, note=""):
    """묶음마다 중앙값을 놓고, 첫 묶음과 나머지 묶음을 가르는 힘을 붙인다."""
    names = list(groups)
    head = f"### {title}\n\n" + (note + "\n\n" if note else "")
    head += "| 층 | 수치 | " + " | ".join(f"{n} 중앙값 ({len(groups[n])}편)" for n in names) + " | " + \
        " | ".join(f"{names[0]}↔{n} 판별력" for n in names[1:]) + " |\n"
    head += "|---" * (2 + len(names) * 2 - 1) + "|\n"
    lines = []
    for k in sorted(keys, key=lambda k: LAYERS.index(LAYER.get(k, "가독성"))):
        cols = [vals(groups[n], k) for n in names]
        if not any(cols):
            continue
        aucs = [auc(cols[0], c) for c in cols[1:]]
        lines.append(f"| {LAYER.get(k, '가독성')} | {LABEL.get(k, k)} | " + " | ".join(fmt(med(c)) for c in cols) + " | " +
                     " | ".join("" if x is None else f"{max(x, 1 - x):.2f}" for x in aucs) + " |")
    return head + "\n".join(lines) + "\n"


def cmd_report(a):
    rows = [json.loads(x) for x in (DATA / "measures.jsonl").read_text(encoding="utf-8").splitlines()]
    keys = [k for k in LABEL if any(k in r["m"] for r in rows)]
    by = lambda **kw: [r for r in rows if all(r[k] == v for k, v in kw.items())]
    out = [f"# 글 평가 보고서\n\n- 날짜: {date.today().isoformat()}\n- 잰 글: {len(rows)}편\n- 사용료 합: {spent():.2f}달러\n",
           "판별력은 두 묶음을 가르는 힘이다. 0.5 면 가르지 못하고 1 이면 완전히 가른다. 중앙값은 묶음 안 글들의 가운데 값이다.\n"]
    gen = [r for r in rows if r["group"] in ("on", "off") and r["set"] == "cases"]
    if gen:
        out.append(table("케이스 묶음: 끈 글과 켠 글", {"끈 글": by(group="off", set="cases"), "켠 글": by(group="on", set="cases")}, keys,
                         "같은 요청을 같은 모델이 docs-suit 를 끄고, 켜고 쓴 글이다. 짝지을 사람 글이 없어 둘만 견준다."))
        kinds = sorted({r["kind"] for r in gen})
        lines = ["| 종류 | 끈 글 평균 길이 | 켠 글 평균 길이 | 끈 글 AI 버릇 | 켠 글 AI 버릇 | 끈 글 글자 수 | 켠 글 글자 수 |", "|---" * 7 + "|"]
        for k in kinds:
            off, on = by(group="off", kind=k, set="cases"), by(group="on", kind=k, set="cases")
            lines.append(f"| {k} | " + " | ".join(fmt(med(vals(g, key))) for key in ("sent_mean",) for g in (off, on)) + " | " +
                         " | ".join(fmt(med(vals(g, "ai_tells_per_1k"))) for g in (off, on)) + " | " +
                         " | ".join(fmt(med(vals(g, "chars"))) for g in (off, on)) + " |")
        out.append("### 종류별 끈 글과 켠 글\n\n" + "\n".join(lines) + "\n")
    # 짝 묶음은 사람 글의 사실로 같은 문서를 쓰게 한 글이다. 사람 글도 짝을 지은 글만 견준다
    for source in sorted({r["pair"]["source"] for r in rows if r.get("pair")}):
        paired = [r for r in rows if r.get("pair") and r["pair"]["source"] == source]
        ids = {r["pair"]["id"] for r in paired}
        # 같은 요청을 다시 쓴 판(이름에 repeat)은 흔들림 절에서만 쓰고, 끈 글은 처음 쓴 판만 쓴다
        main = [r for r in paired if "repeat" not in r["source"]]
        first_off = min((r["source"] for r in main if r["group"] == "off"), default=None)
        groups = {"사람 글": [r for r in rows if r["group"] == "human" and r["source"] == source and r["id"] in ids],
                  "끈 글": [r for r in main if r["group"] == "off" and r["source"] == first_off]}
        paired = main
        runs = sorted({r["source"] for r in paired if r["group"] == "on"})
        for run in runs:
            groups["켠 글" if len(runs) == 1 else f"켠 글 {run}"] = [r for r in paired if r["group"] == "on" and r["source"] == run]
        last = list(groups)[-1]  # 견줌 문장은 가장 나중 판의 켠 글로 쓴다
        use = [k for k in keys if not (source.startswith("katfish") and k in ONE_LINE)]
        moved = [k for k in use if (lambda q: q is not None and q < P_CUT)(paired_p(groups["끈 글"], groups[last], k))]
        toward, away = [], []
        for k in [k for k in CLOSER if k in moved]:
            h, off, on = (med(vals(groups[n], k)) for n in ("사람 글", "끈 글", last))
            if None not in (h, off, on):
                (toward if abs(on - h) < abs(off - h) else away).append(LABEL.get(k, k))
        tells = [fmt(med(vals(groups[n], "ai_tells_per_1k"))) for n in ("사람 글", "끈 글", last)]
        is_ = lambda xs: ", ".join(xs) + ("이다" if batchim(xs[-1]) else "다")
        side = ""
        if toward and away:
            side = f" 그 가운데 AI 티 층에서 켠 글이 사람 글 쪽으로 간 수치는 {', '.join(toward)}, 멀어진 수치는 {is_(away)}."
        elif toward or away:
            side = f" 그 가운데 AI 티 층에서 켠 글이 사람 글{' 쪽으로 간' if toward else '에서 멀어진'} 수치는 {is_(toward or away)}."
        note = ("사람 글의 사실만 뽑아 같은 문서를 끄고, 켜고 쓰게 했다. 같은 요청끼리 짝지은 시험에서 끈 글과 켠 글이 우연보다 크게 다른 수치가 "
                + (f"{len(moved)}가지 있다: {', '.join(LABEL.get(k, k) for k in moved)}." if moved else "없다.") + side
                + f" 1000자당 AI 버릇은 사람 글 {tells[0]}, 끈 글 {tells[1]}, 켠 글 {tells[2]}이다."
                " 가독성 층은 사람 글과의 거리로 재지 않는다.")
        if source.startswith("katfish"):
            note += " KatFish 원문은 문단 구분 없이 한 줄이라 줄과 문단, 목록, 제목 수치는 견주지 않는다."
        if any(composed_kind(r) == "script" for r in groups[last]):
            note += (" 발표 원고 틀은 귀로 듣는 글이라 한 문장에 한 가지만 말하고 짧게 끊게 한다."
                     " 쉼표와 품사 다양성이 사람 글에서 멀어진 것은 그 결과이고, 가독성이 사람 글 닮음보다 앞선다.")
        for n in [g for g in groups if g.startswith("켠 글")]:
            picked = Counter(composed_kind(r) for r in groups[n])
            if picked:
                note += f" {n if n == '켠 글' else n + ' 판'}이 고른 문서 종류는 " + ", ".join(f"{k} {c}편" for k, c in picked.most_common()) + "이다."
        if len(runs) > 1:
            note += f" 사람 글과의 견줌은 가장 나중 판인 {last} 판으로 셌다."
        out.append(table(f"짝 묶음 {source}: 사람 글과 끈 글, 켠 글", groups, use, note))
    out += noise_section(rows, keys)
    for source in sorted({r["source"] for r in rows if r["group"] == "human"}):
        tag = source.split("-", 1)[-1]
        llm = by(group="llm", source=f"{source}")
        if not llm:
            continue  # 연구진의 LLM 글이 없는 사람 글은 짝 묶음에서 견준다
        groups = {"사람 글": by(group="human", source=source), "LLM 글": llm}
        use = [k for k in keys if not (source.startswith("katfish") and k in ONE_LINE)]
        out.append(table(f"연구 데이터 {source}: 사람 글과 LLM 글", groups, use,
                         f"{tag} 장르에서 사람 글과 연구진이 만든 LLM 글을 견준다. 지표가 AI 글을 가르는 힘을 docs-suit 와 상관없이 잰다. "
                         "LLM 글은 GPT-4o, Solar, Qwen2, Llama3.1 이 썼다."))
    human = [r for r in rows if r["group"] == "human"]
    sets = {"사람 글": human, "LLM 글": [r for r in rows if r["group"] == "llm"],
            "Claude 끈 글": [r for r in rows if r["group"] == "off"]}
    sets = {k: v for k, v in sets.items() if v}
    if len(sets) > 1:
        per_k = lambda r, n: r.get("tells", {}).get(n, 0) * 1000 / max(r["m"]["chars"], 1)
        lines = ["| 패턴 | 층 | AI 표지 | " + " | ".join(f"{k}에 보인 비율" for k in sets) + " | "
                 + " | ".join(f"1000자당 {k}" for k in sets) + " |", "|---" * (3 + 2 * len(sets)) + "|"]
        for n, t in th.tells.items():
            shown = [sum(1 for r in v if n in r["shown"]) / len(v) for v in sets.values()]
            if any(shown):
                lines.append(f"| {t['label']} | {t['layer']} | {'아니오' if str(t.get('ai')) == 'false' else '예'} | "
                             + " | ".join(f"{x:.1%}" for x in shown) + " | "
                             + " | ".join(f"{statistics.mean(per_k(r, n) for r in v):.2f}" for v in sets.values()) + " |")
        out.append(f"### 문장 규칙 패턴별로 보인 비율\n\ncheck 가 그 패턴을 보이는 글의 비율이다. LLM 글은 연구 데이터의 글이고, "
                   "Claude 끈 글은 docs-suit 없이 쓴 글이다. AI 표지가 아닌 패턴은 쉬운 말 규칙이라 사람 글에 보여도 잘못 건 것이 아니다. "
                   "AI 표지인 패턴이 사람 글에 자주 보이면 잘못 거는 패턴이다.\n\n" + "\n".join(lines) + "\n")
    # 문체 배우기는 AI 표지가 두 가지 넘게 걸린 샘플을 AI 글로 의심해 제안에서 뺀다. 사람 글을 의심하면 그 글에서 배우지 못한다
    lines = ["| 묶음 | 글 | AI 글로 의심 |", "|---|---|---|"]
    for grp in ("human", "llm", "off", "on"):
        for source in sorted({r["source"] for r in rows if r["group"] == grp}) if grp in ("human", "llm") else [None]:
            v = [r for r in rows if r["group"] == grp and (source is None or r["source"] == source) and "suspect" in r]
            if v:
                name = {"human": "사람", "llm": "LLM", "off": "Claude 끈 글", "on": "Claude 켠 글"}[grp] + (f" {source}" if source else "")
                lines.append(f"| {name} | {len(v)} | {sum(r['suspect'] for r in v) / len(v):.1%} |")
    out.append("### 문체 배우기가 AI 글로 의심하는 비율\n\n`learn` 은 AI 표지가 두 가지 넘게 걸린 샘플을 AI 글로 의심해 제안에서 뺀다. "
               "사람 글 줄은 잘못 의심하는 비율이다.\n\n" + "\n".join(lines) + "\n")
    out += comma_section(rows)
    gec = DATA / "raw" / "gec" / "val.jsonl"
    if gec.exists():
        pairs = [json.loads(x) for x in gec.read_text(encoding="utf-8").splitlines()]
        lines = ["| 패턴 | 틀린 문장에 걸림 | 고친 문장에 걸림 |", "|---|---|---|"]
        for n in ("spelling", "spacing"):
            rx = re.compile(th.tells[n]["re"], re.M)
            e = sum(1 for x in pairs if rx.search(x["err"]))
            c = sum(1 for x in pairs if rx.search(x["cor"]))
            lines.append(f"| {th.tells[n]['label']} | {e}건 ({e / len(pairs):.1%}) | {c}건 ({c / len(pairs):.1%}) |")
        out.append(f"### 표기 패턴을 맞춤법 교정 짝에 대 본 결과\n\n틀린 문장과 고친 문장 {len(pairs)}쌍이다. 고친 문장에 걸린 것은 잘못 건 것이다. "
                   "이 데이터의 틀림은 대부분 소리 나는 대로 친 오타라, 틀린 문장을 잡은 비율은 패턴이 겨냥한 꼴만 센다.\n\n"
                   + "\n".join(lines) + "\n")
    text = "\n".join(out)
    print(text)
    if a.record:
        dest = HERE / "results" / f"{date.today().isoformat()}.md"
        dest.parent.mkdir(exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        print(f"남김: {dest}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="docs-suit 글 평가")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen", help="켠 글과 끈 글을 쓴다")
    g.add_argument("--set", default="cases", choices=("cases", "pairs"))
    g.add_argument("--mode", default="on,off")
    g.add_argument("--agent", default="claude", choices=list(ar.AGENTS))
    g.add_argument("--model", default="sonnet")
    g.add_argument("--only")
    g.add_argument("--run", help="기록 이름. 주지 않으면 날짜와 묶음 이름이다. 같은 이름이면 이미 쓴 글은 건너뛴다")
    g.add_argument("--redo", action="store_true", help="이미 쓴 글도 다시 쓴다")
    g.add_argument("--jobs", type=int, default=4)
    g.add_argument("--cap", type=float, help="사용료 상한(달러). spent.jsonl 의 합으로 잰다. 주지 않으면 묶지 않는다")
    f = sub.add_parser("fetch", help="사람 글과 연구 데이터를 받는다")
    f.add_argument("source", choices=("katfish", "korea-press", "korea-speech", "korea-reporter", "gec") + tuple(SOURCES))
    p = sub.add_parser("pairs", help="사람 글의 사실로 같은 문서를 써 달라는 요청을 만든다")
    p.add_argument("source", help="human/ 아래 묶음 이름. 예: katfish-abstract")
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--model", default="sonnet")
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--cap", type=float)
    sub.add_parser("measure", help="모은 글을 모두 잰다")
    r = sub.add_parser("report", help="보고서를 낸다")
    r.add_argument("--record", action="store_true")
    a = ap.parse_args()
    {"gen": cmd_gen, "fetch": cmd_fetch, "pairs": cmd_pairs, "measure": cmd_measure, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
