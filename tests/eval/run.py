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
사용료는 spent.jsonl 에 쌓고, 합이 --cap 에 닿으면 새 글을 쓰지 않는다. 동시에 도는 글이 있어 --jobs 건만큼 넘을 수 있다.
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import statistics
import sys
import tempfile
import threading
import time
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
    print(f"{a.set} 묶음 {len(items)}건, 쓸 글 {len(jobs)}편, 지금까지 쓴 사용료 {spent():.2f}달러, 상한 {a.cap}달러, "
          f"글은 {out}, 작업 폴더는 {work}", file=sys.stderr)

    def job(pair):
        item, mode = pair
        if spent() >= a.cap:
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


def get(url):
    time.sleep(0.5)  # 공공 서버에 몰아서 요청하지 않는다
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


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
                "kind": "notice", "label": "보도자료", "source": "korea-press", "date": day.group(1),
                "url": f"{KOREA}/briefing/pressReleaseView.do?newsId={nid}", "license": "공공누리 제1유형(출처표시), 정책브리핑",
                "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}, ensure_ascii=False), encoding="utf-8")
            got += 1
            have += 1
        print(f"2022-{month:02d}: {got}편, 모두 {have}편", file=sys.stderr)


def cmd_fetch(a):
    {"katfish": fetch_katfish, "korea-press": fetch_korea_press}[a.source]()


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
        if spent() >= a.cap:
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
                     "compose": meta.get("compose")})
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


def med(xs):
    return statistics.median(xs) if xs else None


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
        groups = {"사람 글": [r for r in rows if r["group"] == "human" and r["source"] == source and r["id"] in ids],
                  "끈 글": [r for r in paired if r["group"] == "off"], "켠 글": [r for r in paired if r["group"] == "on"]}
        use = [k for k in keys if not (source.startswith("katfish") and k in ONE_LINE)]
        closer, names = [], []
        for k in CLOSER:
            h, off, on = (med(vals(groups[n], k)) for n in groups)
            if None not in (h, off, on) and off != on:
                closer.append(abs(on - h) < abs(off - h))
                names.append(LABEL.get(k, k) if closer[-1] else None)
        tells = [fmt(med(vals(groups[n], "ai_tells_per_1k"))) for n in groups]
        note = (f"사람 글의 사실만 뽑아 같은 문서를 끄고, 켜고 쓰게 했다. AI 티 층에서 끈 글과 켠 글의 중앙값이 다른 수치 "
                f"{len(closer)}가지 가운데 {sum(closer)}가지에서 켠 글이 사람 글에 더 가깝다"
                + (f": {', '.join(n for n in names if n)}." if any(names) else ".")
                + f" 1000자당 AI 버릇은 사람 글 {tells[0]}, 끈 글 {tells[1]}, 켠 글 {tells[2]}이다."
                " 가독성 층은 사람 글과의 거리로 재지 않는다.")
        if source.startswith("katfish"):
            note += " KatFish 원문은 문단 구분 없이 한 줄이라 줄과 문단, 목록, 제목 수치는 견주지 않는다."
        picked = Counter(composed_kind(r) for r in groups["켠 글"])
        if picked:
            note += " 켠 글이 고른 문서 종류는 " + ", ".join(f"{k} {n}편" for k, n in picked.most_common()) + "이다."
        out.append(table(f"짝 묶음 {source}: 사람 글과 끈 글, 켠 글", groups, use, note))
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
    ai = [r for r in rows if r["group"] in ("llm", "off")]
    if human and ai:
        lines = ["| 패턴 | 층 | 사람 글에 보인 비율 | AI 글에 보인 비율 | 1000자당 사람 | 1000자당 AI |", "|---" * 6 + "|"]
        per_k = lambda r, n: r.get("tells", {}).get(n, 0) * 1000 / max(r["m"]["chars"], 1)
        for n, t in th.tells.items():
            h = sum(1 for r in human if n in r["shown"]) / len(human)
            g = sum(1 for r in ai if n in r["shown"]) / len(ai)
            if h or g:
                lines.append(f"| {t['label']} | {t['layer']} | {h:.1%} | {g:.1%} | "
                             f"{statistics.mean(per_k(r, n) for r in human):.2f} | {statistics.mean(per_k(r, n) for r in ai):.2f} |")
        out.append(f"### 문장 규칙 패턴별로 보인 비율\n\n사람 글 {len(human)}편과 AI 글 {len(ai)}편(연구 데이터의 LLM 글과 끈 글)에서 "
                   "check 가 그 패턴을 보이는 글의 비율이다. 사람 글에 자주 보이는 패턴은 잘못 거는 패턴이다.\n\n" + "\n".join(lines) + "\n")
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
    g.add_argument("--cap", type=float, default=40.0, help="사용료 상한(달러). spent.jsonl 의 합으로 잰다")
    f = sub.add_parser("fetch", help="사람 글과 연구 데이터를 받는다")
    f.add_argument("source", choices=("katfish", "korea-press"))
    p = sub.add_parser("pairs", help="사람 글의 사실로 같은 문서를 써 달라는 요청을 만든다")
    p.add_argument("source", help="human/ 아래 묶음 이름. 예: katfish-abstract")
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--model", default="sonnet")
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--cap", type=float, default=40.0)
    sub.add_parser("measure", help="모은 글을 모두 잰다")
    r = sub.add_parser("report", help="보고서를 낸다")
    r.add_argument("--record", action="store_true")
    a = ap.parse_args()
    {"gen": cmd_gen, "fetch": cmd_fetch, "pairs": cmd_pairs, "measure": cmd_measure, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
