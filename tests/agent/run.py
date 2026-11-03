#!/usr/bin/env python3
"""동작 테스트. 실제 에이전트에 요청을 넣고, 에이전트가 suit.py 를 어떤 인자로 불렀는지와 쓴 본문을 채점한다.

에이전트마다 로그인이 필요하고 돌릴 때마다 사용료가 들어서 CI 에는 넣지 않는다.
  python3 tests/agent/run.py --agent claude                 # 케이스와 여러 턴 흐름 전체
  python3 tests/agent/run.py --agent antigravity --only sns,pr --model gemini-3.8-flash-high
  python3 tests/agent/run.py --agent claude --record        # tests/agent/results/claude.md 에 남긴다
홈 폴더의 스킬과 프로필은 건드리지 않는다. 케이스마다 임시 폴더에 프로젝트 단위 스킬과 시험 프로필을 두고,
DOCS_SUIT_LOG 로 suit.py 호출 인자를 모은다. Claude Code 는 사용자 설정과 개인 스킬을 끄고 돌린다.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SUIT = ROOT / "suit.py"
spec = importlib.util.spec_from_file_location("suit", SUIT)
suit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suit)
sys.path.insert(0, str(HERE))
from cases import CASES, FLOWS, PROFILE  # noqa: E402

th = suit.Themes(ROOT / "themes" / suit.DEFAULT_LANG)
RUN = f"python3 {SUIT}"


# ---------------------------------------------------------------- 에이전트
# 문서 파일을 만들어 달라는 케이스에서만 파일 쓰기와 문서를 만드는 도구를 더 허락한다. 임시 작업 폴더 안에서 돈다.
FILE_TOOLS = ("Write", "Edit", "Bash(python3:*)", "Bash(pandoc:*)")


def claude_cmd(ask, tmp, model, session=None, keep=False, files=False):
    # 사용자 설정과 개인 스킬, 전역 CLAUDE.md, MCP 를 끄고 처음 설치한 사람과 같은 조건으로 돌린다.
    allow = [f"Bash({RUN}:*)", "Bash(date:*)", "Read", "Skill"] + (list(FILE_TOOLS) if files else [])
    deny = [] if files else ["--disallowedTools", "Write", "Edit"]
    return ["claude", "-p", ask, "--output-format", "stream-json", "--verbose",
            "--setting-sources", "project,local", "--strict-mcp-config",
            "--settings", '{"disableAllHooks": true}',
            "--allowedTools"] + allow + deny + (["--model", model] if model else []) + \
        (["--resume", session] if session else [])


def claude_meta(out):
    meta = {"skills": [], "denied": 0, "cost": 0.0, "model": "", "reply": "", "session": ""}
    for line in out.splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("type") == "system" and o.get("subtype") == "init":
            meta["model"] = o.get("model", "")
            meta["session"] = o.get("session_id", "")
        elif o.get("type") == "assistant":
            for b in o["message"].get("content", []):
                if b.get("type") == "tool_use" and b.get("name") == "Skill":
                    meta["skills"].append(b["input"].get("skill", ""))
        elif o.get("type") == "result":
            meta["denied"] = len(o.get("permission_denials", []))
            meta["cost"] = o.get("total_cost_usd", 0.0)
            meta["sec"] = round(o.get("duration_ms", 0) / 1000)
            meta["reply"] = o.get("result", "")
    return meta


def antigravity_cmd(ask, tmp, model, session=None, keep=False, files=False):
    # 한 번 실행 모드는 확인 창을 띄우지 못해 명령을 거절한다. 작업 폴더 단위 설정이 없으므로
    # ~/.gemini/antigravity-cli/settings.json 의 permissions.allow 에 command(python3 <suit.py 절대 경로>) 가 있어야 한다.
    return ["agy", "-p", ask, "--output-format", "stream-json", "--print-timeout", "900s"] + \
        (["--model", model] if model else []) + (["--conversation", session] if session else [])


def antigravity_meta(out):
    meta = {"skills": [], "denied": 0, "cost": 0.0, "model": "", "reply": "", "session": ""}
    for line in out.splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("event") == "step_update":
            s = o["step_update"]
            path = ((s.get("tool_info") or {}).get("parameters") or {}).get("Path", "")
            if s.get("tool_name") == "read_file" and path.endswith("/SKILL.md"):
                meta["skills"].append(Path(path).parent.name)
        elif o.get("event") == "result":
            r = o["result"]
            meta["denied"] = len(r.get("denied_actions") or [])
            meta["sec"] = round(r.get("duration_seconds", 0))
            meta["reply"] = r.get("response", "")
            meta["session"] = r.get("conversation_id", "")
    return meta


def codex_cmd(ask, tmp, model, session=None, keep=False, files=False):
    # exec 모드는 확인을 묻지 않고 샌드박스 안에서 돌린다. suit.py 가 호출 기록을 쓰도록 임시 폴더를 쓰기 자리에 더하고,
    # 사용자 config.toml 은 읽지 않는다. 여러 턴 흐름은 세션을 이어 가야 해서 그때만 세션을 남긴다.
    common = ["--json", "--skip-git-repo-check", "--ignore-user-config"] + (["--model", model] if model else [])
    if session:
        return ["codex", "exec", "resume", session, ask, "-c", 'sandbox_mode="workspace-write"',
                "-c", f'sandbox_workspace_write.writable_roots=["{tmp}"]'] + common
    return ["codex", "exec", ask, "--sandbox", "workspace-write", "--add-dir", str(tmp)] + common + \
        ([] if keep else ["--ephemeral"])


def codex_meta(out):
    meta = {"skills": [], "denied": 0, "cost": 0.0, "model": "", "reply": "", "session": ""}
    for line in out.splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("type") == "thread.started":
            meta["session"] = o.get("thread_id", "")
        item = o.get("item") or {}
        if o.get("type") != "item.completed":
            continue
        if item.get("type") == "agent_message":
            meta["reply"] = item.get("text", "")
            # 질문을 중간 메시지로 보내고 마지막에는 "질문을 보냈습니다" 로 끝내기도 해서 한 턴의 메시지를 모두 모은다
            meta["said"] = (meta.get("said", "") + "\n" + meta["reply"]).strip()
        elif item.get("type") == "command_execution":
            for part in item.get("command", "").split():
                if part.endswith("/SKILL.md"):
                    meta["skills"].append(Path(part.strip("'\"")).parent.name)
    return meta


def codex_plan():
    """로그인한 ChatGPT 요금제. 토큰은 읽기만 하고 요금제 이름 말고는 꺼내지 않는다."""
    try:
        # CODEX_HOME 으로 다른 계정의 폴더를 주면 그 계정의 요금제를 읽는다
        home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        auth = json.loads((home / "auth.json").read_text(encoding="utf-8"))
        payload = auth["tokens"]["id_token"].split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return claims["https://api.openai.com/auth"]["chatgpt_plan_type"]
    except (OSError, KeyError, IndexError, ValueError):
        return ""


AGENTS = {
    "claude": {"skill": ".claude/skills/docs-suit/SKILL.md", "cmd": claude_cmd, "meta": claude_meta,
               "version": ["claude", "--version"]},
    "antigravity": {"skill": ".agents/skills/docs-suit/SKILL.md", "cmd": antigravity_cmd, "meta": antigravity_meta,
                    "version": ["agy", "--version"],
                    "note": "한 번 실행 모드는 허용 규칙 밖의 명령을 만나면 답 없이 끝난다. 이 표는 종류와 축을 고르는 단계까지 잰다."},
    "codex": {"skill": ".agents/skills/docs-suit/SKILL.md", "cmd": codex_cmd, "meta": codex_meta,
              "version": ["codex", "--version"], "plan": codex_plan},
}

# 에이전트 쪽 사정으로 답 없이 끝난 건은 틀림이 아니라 재지 못한 것으로 센다. 앞의 까닭이 먼저 잡힌다.
UNMEASURED = (("사용 한도", ("quota", "RESOURCE_EXHAUSTED", "usage limit", "rate limit")),
              ("연결 실패", ('"type":"turn.failed"', "AGY_ERROR")))


# ---------------------------------------------------------------- 고르기 채점
def compose_args(argv):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--kind")
    p.add_argument("--audience")
    p.add_argument("--set", action="append")
    p.add_argument("--chars", type=int)
    p.add_argument("--class", dest="cls")
    p.add_argument("--revise", action="store_true")
    a, _ = p.parse_known_args(argv[1:])
    return a


def describe(argv):
    return " ".join(x for x in argv if not x.startswith("/"))


def case_profile(case):
    return suit.merge_folder(PROFILE if case.get("profile", True) else {}, case.get("folder", {}))


def grade(case, calls, reply="", first=None):
    """(맞았나, 에이전트가 부른 것, 어긋난 까닭, 조립된 값, 글자수) 를 돌려준다. reply 는 첫 턴에 에이전트가 한 말 전부이고,
    first 는 calls 에 재촉한 턴의 호출이 섞였을 때 첫 턴의 호출만 따로 준 것이다."""
    expect = case.get("expect", "compose")
    composes = [c for c in calls if c[:1] == ["compose"] and not {"--help", "-h"} & set(c)]
    shown = "; ".join(describe(c) for c in composes) or ", ".join(sorted({c[0] for c in calls if c})) or "부르지 않음"
    if expect == "skip":
        return not calls, shown, "" if not calls else "문서 요청이 아닌데 suit.py 를 불렀다", None, None
    if any(c[:1] == ["bootstrap"] and "--yes" in c for c in calls):
        return False, shown, "사용자의 답 없이 프로필을 저장했다", None, None
    if expect == "serve":
        # --detach 는 뒤에서 도는 서버로 suit.py serve 를 다시 불러 그 호출도 기록에 남는다. 에이전트가 부른 것만 본다.
        serves = [c for i, c in enumerate(calls) if c[:1] == ["serve"]
                  and not (i and "--detach" in calls[i - 1] and "--cwd" in c and "--no-open" in c and "--detach" not in c)]
        if not serves:
            return False, shown, "serve 를 부르지 않았다", None, None
        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("--page")
        p.add_argument("--detach", action="store_true")
        p.add_argument("--kind")
        a, _ = p.parse_known_args(serves[-1][1:])
        # 예전 화면 이름은 대시보드 탭 이름으로 읽는다. --page 를 빼면 엔진이 고르므로 auto 로 센다
        page = suit.DASH_ALIAS.get(a.page, a.page) or "auto"
        pages = case["page"] if isinstance(case["page"], list) else [case["page"]]
        why = ([] if a.detach else ["--detach 없이 띄웠다"]) + ([] if page in pages else [f"탭이 {page} 이다"])
        if case.get("serve_kind") and a.kind != case["serve_kind"]:
            why.append(f"화면을 종류 {a.kind or '없이'} 로 띄웠다")
        return not why, "; ".join(describe(c) for c in serves), ", ".join(why), None, None
    if expect == "call":
        # 대화로 바로 처리할 요청. 대시보드를 띄우지 않고 이 명령을 불러야 하고, offer 면 답에서 대시보드를 권해야 한다
        hits = [c for c in calls if c[:1] == [case["call"]] and all(x in c for x in case.get("args", []))]
        why = ([] if hits else [f"{' '.join([case['call']] + case.get('args', []))} 를 부르지 않았다"])
        why += ["묻지 않고 대시보드를 띄웠다"] if any(c[:1] == ["serve"] for c in calls) else []
        why += ["대시보드를 권하지 않았다"] if case.get("offer") and "대시보드" not in reply else []
        return not why, ", ".join(sorted({" ".join(c[:2]) for c in calls if c})) or "부르지 않음", ", ".join(why), None, None
    if not composes:
        return False, shown, "compose 를 부르지 않았다", None, None
    a = compose_args(composes[-1])
    why = []
    if expect == "conflict" and reply and (wrote_first(first or calls) or not any(m in reply for m in case["mention"])):
        # 작업 폴더의 지침 파일이 docs-suit 와 다른 값을 정한 케이스. 첫 턴에서는 본문을 끝내 check 를 부르기 전에 겹친 값을
        # 들어 어느 쪽을 따를지 물어야 하고, 재촉받은 뒤에는 그 지침의 값으로 조립해야 한다.
        why.append("쓰기 전에 지침 파일과 겹치는 값을 묻지 않았다")
    kinds = case["kind"] if isinstance(case["kind"], list) else [case["kind"]]
    if (a.kind or "") not in kinds:
        why.append(f"종류가 {a.kind or '없음'} 이다")
    try:
        vals, auds, _ = suit.resolve(th, a.kind or None, suit._auds(a.audience), suit._sets(a.set), case_profile(case), a.cls,
                                    talk=True)
    except suit.Missing as e:
        return False, shown, f"엔진이 거절했다: {e}", None, None
    if case.get("audience") and case["audience"] not in auds:
        why.append(f"독자가 {','.join(auds) or '없음'} 이다")
    for axis, v in case.get("want", {}).items():
        if vals[axis][0] != v:
            why.append(f"{axis} 가 {vals[axis][0]} 이다")
    if case.get("chars") and a.chars != case["chars"]:
        why.append(f"글자수가 {a.chars} 이다")
    if bool(case.get("revise")) != a.revise:
        why.append("다듬기인데 --revise 를 붙이지 않았다" if case.get("revise") else "새로 쓰는 글에 --revise 를 붙였다")
    return not why, shown, ", ".join(why), vals, a.chars


# ---------------------------------------------------------------- 본문 검사
# 잴 때는 엔진의 suit.check_doc 을 쓴다. 에이전트가 check 로 스스로 고친 뒤의 본문을 같은 기준으로 다시 잰다.
# 자료가 모자라 질문만 하고 멈추면 실제 사용자처럼 한 번 더 재촉해 본문을 받는다. 고르기 채점은 첫 턴 기록만 쓴다.
FOLLOWUP = "더 줄 정보는 없어. 모르는 곳은 [확인 필요]로 비워 두고 지금 써 줘."


CHECKED = re.compile(r"check\s+-\s[^\n]*<<\s*'?(\w+)'?\n(.*?)\n\1(?:\n|$)", re.S)


def checked_body(transcripts):
    """에이전트가 마지막으로 check 에 heredoc 으로 넘긴 본문. SKILL.md 가 답에 보이는 본문을 검사한 본문과 같게 두라고
    하므로, 앞뒤 안내와 채울 곳 목록이 섞인 답보다 이것을 잰다. 에이전트마다 기록 꼴이 달라 JSON 안의 문자열을 다 훑는다."""
    found = []

    def walk(x):
        if isinstance(x, str):
            found.extend(m.group(2) for m in CHECKED.finditer(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    for t in transcripts:
        for line in t.splitlines():
            try:
                walk(json.loads(line))
            except ValueError:
                continue
    # compose 끝의 검사 안내도 같은 꼴의 heredoc 을 담는다. 그 자리표시는 본문이 아니다.
    found = [b for b in found if b.strip() != "(본문 전체)"]
    return found[-1] if found else ""


def wrote_first(calls):
    """본문을 다 써서 check 까지 부른 턴인가."""
    return any(c[:1] == ["check"] for c in calls)


# 쓰기 전에 사용자에게 자료를 달라고 되묻는 말. 물음표 없이 "보내 주십시오" 로 묻는 답도 질문으로 본다
# 초안 끝의 "알려 주시면 반영해 드리겠습니다" 같은 맺음말이나 본문의 "정보가 부족하다" 는 걸리지 않게, 쓰기 전에 되묻는 말만 둔다
ASK_META = re.compile(r"먼저 여쭤|먼저 여쭙|먼저 받아야|지어 쓰지 않|지어 쓸 수 (?:도 )?없|지어낼 수 없|지어내지 않으려|"
                      r"(?:작성하|쓰)려면 (?:다음|아래)|(?:알려|보내) 주시면 (?:초안|작성|쓰|써)")


def only_asks(reply):
    """질문만 하고 멈춘 답인가. 질문이 여럿이고 본문의 [확인 필요] 표시가 없으면 질문만 하고 멈춘 것이다.
    요청 표현이 한 번뿐이어도 답이 짧으면 자료를 달라고 하고 멈춘 것이다. "보내 주시면 쓰겠습니다" 같은 꼴이다.
    제목이 없는 1500자 안쪽 답이 자료를 달라고 되물으면 굵은 번호 목록으로 물어도 질문으로 본다."""
    asks = len(re.findall(r"\?|주세요|여쭤|여쭙|주시면", reply))
    asked_back = ASK_META.search(reply) and not re.search(r"^#", reply, re.M) and len(reply) < 1500
    return not suit.UNRESOLVED.search(reply) and (asks >= 2 or (asks and len(reply) < 400) or bool(asked_back))


# 케이스가 작업 폴더에 두는 에이전트 지침 파일. 에이전트가 쓴 본문이 아니다.
GUIDE_FILES = {"AGENTS.md", "CLAUDE.md", "GEMINI.md"}


def doc_text(reply, proj):
    """에이전트가 쓴 본문. 작업 폴더에 만든 .md 가 있으면 그것을, 없으면 답의 코드 블록이나 --- 사이, 메일 꼴,
    답 전체 순으로 쓴다. 질문만 하고 멈췄으면 빈 문자열을 돌려준다."""
    # 답 끝의 `성장:` 줄은 check 가 만든 줄이라 본문이 아니다. 남겨 두면 분량을 잴 때 함께 센다.
    reply = re.sub(r"^성장:.*$", "", reply, flags=re.M).rstrip()
    made = [f for f in proj.rglob("*.md") if not {".agents", ".claude"} & set(f.parts) and f.name not in GUIDE_FILES]
    if made:
        return max(made, key=lambda f: f.stat().st_size).read_text(encoding="utf-8")
    blocks = [b for b in re.findall(r"```[a-z]*\n(.*?)```", reply, re.S) if len(b) > 200]
    if blocks:
        return max(blocks, key=len)
    # --- 로 나뉜 답은 본문과 덧붙인 안내가 섞여 있다. [확인 필요] 표시가 가장 많은 조각을 본문으로 본다.
    mail = re.search(r"^제목\s*[:：].*?(?:올림|드림|배상)\s*$", reply, re.M | re.S)
    if mail:
        return mail.group(0)
    if only_asks(reply):
        return ""
    # --- 로 나뉜 답은 본문과 덧붙인 안내가 섞여 있다. [확인 필요] 표시가 가장 많은 조각을 본문으로 본다.
    parts = re.split(r"^---\s*$", reply, flags=re.M)
    if len(parts) >= 2:
        return max(parts, key=lambda x: (x.count("[확인 필요"), len(x)))
    return reply


def file_checks(ext, tmp, vals, chars, kind):
    """문서 파일을 만들어 달라는 케이스. 파일을 만들었는지, 그 파일을 check 에 넘겼는지 보고, 파일에서 뽑은 글을 잰다."""
    proj = tmp / "proj"
    made = sorted((f for f in proj.rglob(f"*{ext}") if not {".agents", ".claude"} & set(f.parts)),
                  key=lambda f: f.stat().st_mtime)
    if not made:
        return [("file", False, f"{ext} 파일을 만들지 않았다")]
    calls = read_calls(tmp) + read_calls(tmp, "calls-2.jsonl")
    passed = [c[1] for c in calls if c[:1] == ["check"] and len(c) > 1 and c[1].endswith(ext)]
    out = [("file", bool(passed), f"{made[-1].name} 를 check 에 넘김" if passed else f"{made[-1].name} 를 check 에 넘기지 않았다")]
    try:
        text, _ = suit.doc_file_text(made[-1])
    except ValueError as e:
        return out + [("file", False, f"파일을 읽지 못했다: {e}")]
    # 엔진의 check 처럼 문서 파일은 마크다운 기호가 새어 나올 일이 없어 출력 형식을 재지 않는다
    return out + suit.check_doc(text, {k: v for k, v in vals.items() if k != "markup"}, chars, kind, th)


def facts_kept(case, doc):
    """(남은 수, 빠진 사실). 띄어쓰기와 대소문자는 가리지 않는다. 짧고 깔끔해졌어도 준 사실이 빠졌으면 나아진 글이 아니다."""
    flat = re.sub(r"\s+", "", doc).lower()
    missing = [f if isinstance(f, str) else f[0] for f in case.get("facts", [])
               if not any(re.sub(r"\s+", "", x).lower() in flat for x in ([f] if isinstance(f, str) else f))]
    return len(case.get("facts", [])) - len(missing), missing


def doc_summary(checks):
    if checks is None:
        return "본문 없음"
    if not checks:
        return "잴 거리 없음"
    bad = [f"{suit.check_label(th, axis)} ({got})" for axis, ok, got in checks if not ok]
    return "맞음" if not bad else "틀림: " + ", ".join(bad)


# ---------------------------------------------------------------- 실행
def invoke(agent, ask, tmp, proj, env, model, session=None, keep=False, files=False):
    try:
        p = subprocess.run(AGENTS[agent]["cmd"](ask, tmp, model, session, keep, files), cwd=proj, env=env,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=900)
        return p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        out = e.stdout or ""
        return (out.decode() if isinstance(out, bytes) else out), "시간 초과"


def prepare(agent, item, base):
    """케이스 하나의 임시 폴더. 스킬, 시험 프로필, 폴더 파일, 지침 파일을 두고 suit.py 에 넘길 환경 변수를 돌려준다."""
    tmp = base / item["id"]
    proj = tmp / "proj"
    proj.mkdir(parents=True)
    skill = proj / AGENTS[agent]["skill"]
    skill.parent.mkdir(parents=True)
    skill.write_text(suit.skill_text(th), encoding="utf-8")
    for name, text in item.get("files", {}).items():
        (proj / name).write_text(text, encoding="utf-8")
    prof = tmp / "profile.yaml"
    if item.get("profile", True):
        prof.write_text(suit.dump_yaml(PROFILE), encoding="utf-8")
    if item.get("folder"):
        suit.write_folder(item["folder"], proj)
    if item.get("samples"):
        shutil.copytree(HERE / "samples", proj / "samples")
    # serve 가 브라우저를 열면 돌리는 사람 화면에 탭이 뜬다. webbrowser 는 BROWSER 의 명령을 먼저 쓰므로 true 로 막는다.
    env = dict(os.environ, DOCS_SUIT_PROFILE=str(prof), DOCS_SUIT_HOME=str(tmp / "conf"),
               DOCS_SUIT_LOG=str(tmp / "calls.jsonl"), BROWSER="true")
    return tmp, proj, env


def stop_servers(proj):
    """에이전트가 --detach 로 띄운 화면 서버를 끈다. 뒤에서 도는 서버는 --cwd 에 작업 폴더의 절대 경로를 받는다.
    macOS 는 임시 폴더 앞에 /private 가 붙기도 해서 기록 폴더 이름부터 맞춘다."""
    tail = "/".join(proj.parts[-3:])
    subprocess.run(["pkill", "-f", f"suit.py serve .*{tail}"], capture_output=True)


def read_calls(tmp, name="calls.jsonl"):
    log = tmp / name
    return [json.loads(x)["argv"] for x in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


def finish_meta(agent, tmp, transcripts, ok):
    metas = [AGENTS[agent]["meta"](t) for t in transcripts]
    meta = dict(metas[-1]) if metas else AGENTS[agent]["meta"]("")
    meta["skills"] = [s for m in metas for s in m["skills"]]
    meta["denied"] = sum(m["denied"] for m in metas)
    meta["cost"] = sum(m["cost"] for m in metas)
    meta["sec"] = sum(m.get("sec", 0) for m in metas)
    err = (tmp / "stderr.txt").read_text(encoding="utf-8") if (tmp / "stderr.txt").exists() else ""
    seen = err + "".join(transcripts).replace('": "', '":"')
    meta["unmeasured"] = "" if ok else next((why for why, signs in UNMEASURED if any(k in seen for k in signs)), "")
    skill = tmp / "proj" / AGENTS[agent]["skill"]
    meta["skill"] = hashlib.sha1(skill.read_bytes()).hexdigest()[:8] if skill.exists() else "없음"
    return meta


def load_case(agent, case, base):
    """지난 실행의 기록으로 다시 채점한다. 기대값만 고쳤을 때 에이전트를 다시 부르지 않는다."""
    tmp = base / case["id"]
    transcripts = [(tmp / name).read_text(encoding="utf-8") for name in ("transcript.jsonl", "transcript-2.jsonl")
                   if (tmp / name).exists()]
    said = AGENTS[agent]["meta"](transcripts[0]) if transcripts else {}
    reply = said.get("said") or said.get("reply", "")
    graded = read_calls(tmp) + (read_calls(tmp, "calls-2.jsonl") if case.get("expect") == "conflict" else [])
    ok, shown, why, vals, chars = grade(case, graded, reply, read_calls(tmp))
    meta = finish_meta(agent, tmp, transcripts, ok)
    meta["followup"] = len(transcripts) > 1
    # check 에 넘긴 본문이 있으면 그것을 잰다. 없으면 답에서 뽑되, 재촉했으면 두 답 가운데 본문이 더 긴 쪽을 쓴다.
    # 첫 답에 본문을 쓰고 둘째 답은 안내만 하는 경우가 있다.
    replies = [AGENTS[agent]["meta"](t)["reply"] for t in transcripts] or [meta["reply"]]
    doc = (checked_body(transcripts)
           or max((doc_text(r, tmp / "proj") for r in replies), key=lambda d: len(suit.body_lines(d)))) if vals else ""
    kind = compose_args(next(c for c in reversed(read_calls(tmp)) if c[:1] == ["compose"] and "--help" not in c)).kind if vals else None
    meta["doc"] = None if not vals else suit.check_doc(doc, vals, chars, kind, th) if doc else None
    if vals and case.get("file"):
        meta["doc"] = file_checks(case["file"], tmp, vals, chars, kind)
    meta["facts"] = facts_kept(case, doc) if doc and case.get("facts") else None
    # 본문을 다 쓴 뒤 check 로 성장 기록을 남겼는지는 기록 파일로 본다. 빈 본문으로 부른 check 는 기록을 남기지 않는다.
    # 프로필 없이 시작한 케이스는 슬롯이 없어 기록이 남지 않으므로 호출만 본다. 재촉한 턴의 호출은 calls-2.jsonl 에 있다.
    calls = read_calls(tmp) + read_calls(tmp, "calls-2.jsonl")
    meta["checked"] = (bool(suit.read_growth(tmp / "profile.growth.jsonl")) if case.get("profile", True)
                       else any(c[:1] == ["check"] for c in calls))
    return case, ok, shown, why, meta


def run_case(agent, case, base, model):
    tmp, proj, env = prepare(agent, case, base)
    t0 = time.time()
    out, err = invoke(agent, case["ask"], tmp, proj, env, model, keep=True, files=bool(case.get("file")))
    stop_servers(proj)
    (tmp / "transcript.jsonl").write_text(out, encoding="utf-8")
    (tmp / "stderr.txt").write_text(err or "", encoding="utf-8")
    first = AGENTS[agent]["meta"](out)
    vals = grade(case, read_calls(tmp))[3]
    made = case.get("file") and any(f for f in proj.rglob(f"*{case['file']}") if ".agents" not in f.parts)
    # 겹침 케이스는 질문을 마친 뒤 "답을 받으면 쓰겠다" 로 끝내기도 해서, 첫 턴에 check 를 부르지 않았으면 재촉한다
    asked = not doc_text(first["reply"], proj) or (case.get("expect") == "conflict" and not wrote_first(read_calls(tmp)))
    if vals and first["session"] and not made and asked:
        env2 = dict(env, DOCS_SUIT_LOG=str(tmp / "calls-2.jsonl"))
        out2, err2 = invoke(agent, FOLLOWUP, tmp, proj, env2, model, first["session"], keep=True,
                            files=bool(case.get("file")))
        (tmp / "transcript-2.jsonl").write_text(out2, encoding="utf-8")
        (tmp / "stderr.txt").write_text((err or "") + "\n" + (err2 or ""), encoding="utf-8")
    case, ok, shown, why, meta = load_case(agent, case, base)
    meta["sec"] = round(time.time() - t0)
    return case, ok, shown, why, meta


# ---------------------------------------------------------------- 여러 턴 흐름
def dig(data, path):
    for key in path.split("."):
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def same(got, want):
    if isinstance(want, list):
        return isinstance(got, list) and set(want) <= set(got)
    return isinstance(got, str) and got.replace(" ", "") == str(want).replace(" ", "")


def grade_flow(flow, tmp):
    """흐름이 끝난 뒤 프로필과 폴더 파일이 기대대로 남았는지 본다."""
    files = {"profile": suit.read_slot(tmp / "profile.yaml"), "folder": suit.read_folder(tmp / "proj" / suit.FOLDER_FILE)}
    why = []
    for where, want in flow["expect"].items():
        if where == "anywhere":
            # 축 값을 기본값에 남겼든 독자별로 남겼든 맞다
            places = [files["profile"].get("defaults") or {}] + list((files["profile"].get("audiences") or {}).values())
            why += [f"프로필 어디에도 {axis}={value} 가 없다" for axis, value in want.items()
                    if not any(isinstance(p, dict) and p.get(axis) == value for p in places)]
            continue
        if where == "voice":
            voice = tmp / "profile.voice.md"
            if not voice.exists():
                why.append("내 문체 문서를 남기지 않았다")
            else:
                text = voice.read_text(encoding="utf-8")
                why += [f"내 문체 문서에 샘플의 {w} 가 샜다" for w in want.get("leak", []) if w in text]
            continue
        if where == "absent":
            why += [f"프로필에 {p} 가 남았다" for p in want if dig(files["profile"], p) is not None]
            continue
        for path, value in want.items():
            got = dig(files[where], path)
            if not same(got, value):
                why.append(f"{'프로필' if where == 'profile' else '폴더 파일'}의 {path} 가 {got} 이다")
    return not why, ", ".join(why)


def load_flow(agent, flow, base):
    tmp = base / flow["id"]
    ok, why = grade_flow(flow, tmp)
    transcripts = [(tmp / f"transcript-{i}.jsonl").read_text(encoding="utf-8")
                   for i in range(1, len(flow["turns"]) + 1) if (tmp / f"transcript-{i}.jsonl").exists()]
    calls = read_calls(tmp)
    shown = "; ".join(describe(c) for c in calls
                      if c[:1] in (["bootstrap"], ["set"], ["profile"], ["learn"], ["voice"]) and len(c) > 1) or "-"
    return flow, ok, shown, why, finish_meta(agent, tmp, transcripts, ok)


def run_flow(agent, flow, base, model):
    tmp, proj, env = prepare(agent, flow, base)
    session, errs, t0 = None, [], time.time()
    for i, ask in enumerate(flow["turns"], 1):
        out, err = invoke(agent, ask, tmp, proj, env, model, session, keep=True)
        (tmp / f"transcript-{i}.jsonl").write_text(out, encoding="utf-8")
        errs.append(err or "")
        session = AGENTS[agent]["meta"](out)["session"] or session
        if not session:
            break
    (tmp / "stderr.txt").write_text("\n".join(errs), encoding="utf-8")
    flow, ok, shown, why, meta = load_flow(agent, flow, base)
    meta["sec"] = round(time.time() - t0)
    return flow, ok, shown, why, meta


# ---------------------------------------------------------------- 보고
def expected(case):
    expect = case.get("expect", "compose")
    if expect == "skip":
        return "부르지 않음"
    if expect == "serve":
        pages = case["page"] if isinstance(case["page"], list) else [case["page"]]
        return f"serve --detach, 탭 {' 또는 '.join(pages)}" + (f", 종류 {case['serve_kind']}" if case.get("serve_kind") else "")
    if expect == "call":
        return " ".join([case["call"]] + case.get("args", [])) + ", 대시보드 띄우지 않음" + (", 대시보드 권함" if case.get("offer") else "")
    kinds =case["kind"] if isinstance(case["kind"], list) else [case["kind"]]
    parts = [" 또는 ".join(k or "종류 없음" for k in kinds)]
    if case.get("audience"):
        parts.append(f"독자 {case['audience']}")
    parts += [f"{k}={v}" for k, v in case.get("want", {}).items()]
    if case.get("chars"):
        parts.append(f"{case['chars']}자")
    if case.get("revise"):
        parts.append("다듬기")
    if case.get("file"):
        parts.append(f"{case['file']} 파일")
    if expect == "conflict":
        parts.append("쓰기 전에 고르게 함")
    return ", ".join(parts)


def flow_expected(flow):
    parts = [f"{'프로필' if w == 'profile' else '폴더 파일'} {p}={v}"
             for w, want in flow["expect"].items() if w in ("profile", "folder") for p, v in want.items()]
    parts += [f"프로필 어딘가에 {p}={v}" for p, v in flow["expect"].get("anywhere", {}).items()]
    if "voice" in flow["expect"]:
        parts.append("내 문체 문서, 샘플 이름과 수치 새지 않음")
    parts += [f"프로필에 {p} 없음" for p in flow["expect"].get("absent", [])]
    return ", ".join(parts)


def verdict(ok, why, m):
    return "맞음" if ok else f"재지 못함: {m['unmeasured']}" if m["unmeasured"] else f"틀림: {why}"


def report(agent, results, flows, version, model=None):
    every = results + flows
    models = sorted({m["model"] for *_, m in every if m["model"]}) or ([model] if model else [])
    unmeasured = sum(1 for *_, m in results if m["unmeasured"])
    docs = [m["doc"] for *_, m in results if m.get("doc")]
    written = [m for *_, m in results if m.get("doc") is not None]
    doc_ok = sum(1 for d in docs if all(ok for _, ok, _ in d))
    flow_unmeasured = sum(1 for *_, m in flows if m["unmeasured"])
    cost = sum(m["cost"] for *_, m in every)
    lines = [f"# 동작 테스트: {agent}", "",
             f"- 날짜: {date.today().isoformat()}",
             f"- 에이전트: {version}",
             "- 스킬 자리: 임시 작업 폴더",
             f"- SKILL.md 지문: {', '.join(sorted({m['skill'] for *_, m in every if m['skill']})) or '알 수 없음'}",
             f"- 모델: {', '.join(models) or '알 수 없음'}",
             *([f"- 요금제: {AGENTS[agent]['plan']() or '알 수 없음'}"] if AGENTS[agent].get("plan") else []),
             f"- 고르기: {sum(1 for _, ok, *_ in results if ok)}/{len(results) - unmeasured} 맞음"
             + (f" (재지 못한 {unmeasured}건 제외)" if unmeasured else ""),
             f"- 본문 검사: {doc_ok}/{len(docs)} 맞음. 어법, 문체, 분량, 강조를 어림 기준으로 잰다",
             *([f"- 사실 보존: 요청에 준 사실 {sum(len(c.get('facts', [])) for c, *_, m in results if m.get('facts'))}개 가운데 "
                f"{sum(m['facts'][0] for *_, m in results if m.get('facts'))}개가 본문에 남았다. 본문 검사의 맞음에는 넣지 않는다"]
              if any(m.get("facts") for *_, m in results) else []),
             f"- 검사 기록: 본문을 쓴 {len(written)}건 가운데 {sum(1 for m in written if m.get('checked'))}건이 check 로 성장 기록을 남겼다",
             *([f"- 여러 턴 흐름: {sum(1 for _, ok, *_ in flows if ok)}/{len(flows) - flow_unmeasured} 맞음"
                + (f" (재지 못한 {flow_unmeasured}건 제외)" if flow_unmeasured else "")] if flows else []),
             f"- 사용료: {cost:.2f}달러" if cost else "- 사용료: 에이전트가 알려 주지 않음",
             *([f"- 한계: {AGENTS[agent]['note']}"] if AGENTS[agent].get("note") else [])]
    if results:
        lines += ["", "## 요청 하나", "", "| 케이스 | 기대 | 에이전트가 부른 것 | 판정 | 본문 검사 | 비고 | 초 |",
                  "|---|---|---|---|---|---|---|"]
        for case, ok, shown, why, m in results:
            lines.append(f"| {case['id']} | {expected(case)} | `{shown}` | {verdict(ok, why, m)} | "
                         f"{doc_summary(m['doc']) if ok and case.get('expect', 'compose') in ('compose', 'conflict') else '-'} | {note(m)} | {m['sec']} |")
    if flows:
        lines += ["", "## 여러 턴 흐름", "", "| 흐름 | 기대 | 에이전트가 부른 것 | 판정 | 비고 | 초 |", "|---|---|---|---|---|---|"]
        for flow, ok, shown, why, m in flows:
            lines.append(f"| {flow['id']} | {flow_expected(flow)} | `{shown}` | {verdict(ok, why, m)} | {note(m)} | {m['sec']} |")
    return "\n".join(lines) + "\n"


def note(m):
    others = sorted({s for s in m["skills"] if s and s != "docs-suit"})
    return ", ".join(([f"같이 불린 스킬 {', '.join(others)}"] if others else [])
                     + ([f"거절된 도구 {m['denied']}건"] if m["denied"] else [])
                     + ([f"빠진 사실 {', '.join(m['facts'][1])}"] if m.get("facts") and m["facts"][1] else [])
                     + (["먼저 질문해 한 번 더 재촉함"] if m.get("followup") else [])
                     + (["check 를 부르지 않음"] if m.get("doc") is not None and not m.get("checked") else []))


def main():
    ap = argparse.ArgumentParser(description="docs-suit 동작 테스트")
    ap.add_argument("--agent", required=True, choices=list(AGENTS))
    ap.add_argument("--only", help="케이스나 흐름 id 를 쉼표로 잇는다")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--model", help="에이전트에 넘길 모델. 주지 않으면 에이전트 기본값")
    ap.add_argument("--record", action="store_true", help="tests/agent/results/<agent>.md 에 남긴다")
    ap.add_argument("--regrade", metavar="기록 폴더", help="에이전트를 부르지 않고 지난 실행의 기록으로 다시 채점한다")
    ap.add_argument("--into", metavar="기록 폴더", help="고른 케이스만 지난 실행의 기록 폴더에 다시 돌려 넣는다. 뒤이어 --regrade 로 채점한다")
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    cases = [c for c in CASES if not only or c["id"] in only]
    flows = [f for f in FLOWS if not only or f["id"] in only]
    if a.into and not only:
        ap.error("--into 는 --only 로 고른 케이스만 다시 돌릴 때 쓴다")
    if a.record and (only or a.into):
        ap.error("--record 는 케이스 전체를 돌릴 때만 쓴다")
    version = subprocess.run(AGENTS[a.agent]["version"], capture_output=True, text=True).stdout.strip()
    if a.regrade:
        base = Path(a.regrade)
        results = [load_case(a.agent, c, base) for c in cases if (base / c["id"]).exists()]
        flow_results = [load_flow(a.agent, f, base) for f in flows if (base / f["id"]).exists()]
    else:
        base = Path(a.into) if a.into else Path(tempfile.mkdtemp(prefix=f"docs-suit-agent-{a.agent}-"))
        for item in (cases + flows) if a.into else []:
            shutil.rmtree(base / item["id"], ignore_errors=True)
        print(f"{a.agent} {version}, 케이스 {len(cases)}건, 흐름 {len(flows)}건, 기록은 {base}", file=sys.stderr)
        with ThreadPoolExecutor(a.jobs) as ex:
            flow_jobs = [ex.submit(run_flow, a.agent, f, base, a.model) for f in flows]
            results = list(ex.map(lambda c: run_case(a.agent, c, base, a.model), cases))
            flow_results = [j.result() for j in flow_jobs]
    for item, ok, shown, why, m in results + flow_results:
        print(f"{'맞음' if ok else '틀림'} {item['id']}: {shown}" + (f" ({why})" if why else ""), file=sys.stderr)
    text = report(a.agent, results, flow_results, version, a.model)
    print(text)
    if a.record:
        out = HERE / "results" / f"{a.agent}.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return 0 if all(ok or m["unmeasured"] for _, ok, *_, m in results + flow_results) else 1


if __name__ == "__main__":
    sys.exit(main())
