#!/usr/bin/env python3
"""GitHub 에서 ChatGPT 공개 전에 사람이 쓴 한국어 글을 모으는 어댑터.

- fetch_github_pr: 한국어 PR 설명. 문서 종류 pr, 이름표 "PR 설명".
- fetch_github_readme: 한국어 README. 문서 종류 guide, 이름표 "가이드·README·위키".

거르는 기준은 두 어댑터가 같다.
- 저장소 라이선스(.license.spdx_id)가 MIT 나 Apache-2.0 이다.
- 2022-11-30(UTC) 전에 쓴 글이다. PR 은 created_at, README 는 그 날 전 마지막 커밋의 판을 읽는다.
- 코드 블록과 인라인 코드, 주소를 걷은 본문에서 한글 음절이 글자(한글+로마자)의 50% 이상이다.
- 그 본문이 300~3000자이고, 목록과 제목을 뺀 줄글 줄에 다/요/까/죠/네/시오 로 끝나는 문장이 세 개 이상이다.
- 저장소마다 두 편까지만 받고, 해(2016~2022)를 돌아가며 한 편씩 검색 순서대로 받는다.
- 포크 저장소의 PR 과 앞서 받은 글과 줄이 절반 넘게 겹치는 글은 뺀다.

사용자 이름과 @멘션, 메일, 전화번호, 작성자와 리뷰어 줄, 팀원과 라이선스 절은 걷고, 이름 뒤의 님은 ○○님으로 가린다.
저장소 이름은 메타의 url 에만 남기고, 파일 이름은 url 의 해시로 짓는다.
표준 라이브러리만 쓰고 GitHub API 는 로그인한 gh CLI 로 부른다.
"""
import base64
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from collections import Counter
from pathlib import Path

DATA = Path(os.environ.get("DOCS_SUIT_EVAL", Path.home() / ".cache" / "docs-suit-eval"))
CUTOFF = "2022-11-30T00:00:00Z"
YEARS = tuple(range(2016, 2023))
LICENSES = ("MIT", "Apache-2.0")
PER_REPO = 2
MIN_CHARS, MAX_CHARS = 300, 3000
MIN_HANGUL = 0.5
MIN_SENTENCES = 3
SEARCH_GAP = 2.2  # 검색 API 는 분당 30번이라 2초 넘게 띄운다

PR_QUERIES = (
    "수정했습니다 OR 추가했습니다 OR 변경했습니다 OR 구현했습니다 OR 해결했습니다",
    '"작업 내용" OR "변경 사항" OR "변경사항" OR "작업 사항"',
)
README_QUERIES = ('설치 OR 사용법 OR "사용 방법" in:readme',)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# --- GitHub API ---------------------------------------------------------------

_last_search = [0.0]


def _pause_for(resource, attempt):
    """한도에 걸리면 rate_limit 의 reset 까지 기다린다. 2차 한도는 reset 이 안 보여 점점 길게 쉰다."""
    p = subprocess.run(["gh", "api", "rate_limit"], capture_output=True, text=True, encoding="utf-8")
    wait = 60 * (attempt + 1)
    if p.returncode == 0:
        r = json.loads(p.stdout)["resources"].get(resource, {})
        if r.get("remaining", 1) == 0:
            wait = max(r.get("reset", 0) - time.time() + 3, 5)
    return min(wait, 900)


def gh(endpoint, params=None, search=False, tries=6):
    """GET 요청 한 번. 없는 자원(404, 409, 422, 451)이나 막힌 저장소는 None 이다."""
    cmd = ["gh", "api", "-X", "GET", endpoint]
    for k, v in (params or {}).items():
        cmd += ["-f", f"{k}={v}"]
    for attempt in range(tries):
        if search:
            gap = _last_search[0] + SEARCH_GAP - time.time()
            if gap > 0:
                time.sleep(gap)
            _last_search[0] = time.time()
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode == 0:
            return json.loads(p.stdout) if p.stdout.strip() else None
        err = p.stderr
        if "rate limit" in err.lower() or "HTTP 429" in err:
            wait = _pause_for("search" if search else "core", attempt)
            log(f"  한도에 걸려 {wait:.0f}초 쉰다: {endpoint}")
            time.sleep(wait)
            continue
        if re.search(r"HTTP 5\d\d", err) or "timeout" in err.lower() or "connection" in err.lower():
            time.sleep(5 * (attempt + 1))
            continue
        return None
    return None


_repos = {}


def repo_meta(full):
    """{license, owner, user_owner, name, fork}. 저장소마다 한 번만 부른다."""
    key = full.lower()
    if key not in _repos:
        r = gh(f"repos/{full}") or {}
        _repos[key] = {
            "license": (r.get("license") or {}).get("spdx_id"),
            "owner": (r.get("owner") or {}).get("login", full.split("/")[0]),
            "user_owner": (r.get("owner") or {}).get("type") == "User",
            "name": r.get("name", full.split("/")[-1]),
            "fork": bool(r.get("fork")),
        }
    return _repos[key]


# --- 본문 다듬기 ----------------------------------------------------------------

FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
LIST_LINE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
RULE = re.compile(r"^\s*(?:\|.*|[-=*_ :|]{3,})$")  # 표 줄과 구분 줄, 가로줄, setext 밑줄은 글자가 없어도 둔다
HTML_TAGS = ("a|abbr|article|b|big|blockquote|br|caption|center|code|col|colgroup|dd|del|details|div|dl|dt|em|"
             "figcaption|figure|font|h[1-6]|hr|i|iframe|img|input|ins|kbd|li|link|mark|meta|nobr|ol|p|path|picture|"
             "pre|s|section|small|source|span|strike|strong|sub|summary|sup|svg|table|tbody|td|th|thead|tr|tt|u|"
             "ul|video|wbr")
TAG = re.compile(rf"</?(?:{HTML_TAGS})\b[^>]*>", re.I)
URL = re.compile(r"(?:https?://|www\.)[^\s<>\"'\[\]()]+", re.I)
EMAIL = re.compile(r"(?<![\w.+-])(?!git@)[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}(?![\w.])")
PHONE = re.compile(r"(?<!\d)(?:\+?82[- ]?)?0\d{1,2}[- .]\d{3,4}[- .]\d{4}(?!\d)|(?<!\d)01[016789]\d{7,8}(?!\d)")
# 자바와 스위프트의 어노테이션처럼 @ 로 시작하지만 사용자가 아닌 낱말
NOT_USER = {
    "Override", "Transactional", "Entity", "Getter", "Setter", "Builder", "Component", "Service", "Repository",
    "Controller", "RestController", "Autowired", "Bean", "Configuration", "Test", "Before", "After", "Data", "Value",
    "Id", "Column", "Table", "Query", "Param", "RequestMapping", "GetMapping", "PostMapping", "PutMapping",
    "PatchMapping", "DeleteMapping", "RequestBody", "ResponseBody", "PathVariable", "RequestParam", "Valid",
    "NotNull", "NotBlank", "Nullable", "NonNull", "JsonProperty", "SpringBootTest", "ExtendWith", "DisplayName",
    "BeforeEach", "AfterEach", "Mock", "InjectMocks", "Slf4j", "AllArgsConstructor", "NoArgsConstructor",
    "RequiredArgsConstructor", "ManyToOne", "OneToMany", "OneToOne", "ManyToMany", "JoinColumn", "Enumerated",
    "Embedded", "Embeddable", "MappedSuperclass", "CreatedDate", "LastModifiedDate", "Profile", "Async",
    "Scheduled", "EventListener", "Published", "State", "Binding", "ObservedObject", "StateObject",
    "EnvironmentObject", "Environment", "MainActor", "objc", "escaping", "available", "IBOutlet", "IBAction",
    "discardableResult", "Composable", "Inject", "Singleton", "Module", "Provides", "Binds", "HiltViewModel",
    "AndroidEntryPoint", "Parcelize", "SerializedName", "Expose", "Keep", "JvmStatic", "JvmField", "Suppress",
    "Deprecated", "SuppressWarnings", "FunctionalInterface", "ControllerAdvice", "ExceptionHandler",
    "ResponseStatus", "Validated", "Email", "Size", "Pattern", "Modifying", "Lazy", "Primary", "Qualifier",
    "Retention", "Target", "Documented", "Inherited", "property", "staticmethod", "classmethod", "media",
    "import", "include", "mixin", "extend", "keyframes", "apply", "tailwind", "font-face", "param", "returns",
    "return", "throws", "type", "typedef", "deprecated", "see", "since", "version",
}
MENTION = re.compile(r"(?<![\w/.@`-])@([A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38})(?![\w@/-])"
                     r"(?:\s*(?:님께서|님께|님이|님은|님의|님|께서|께|에게))?")
META_LINE = re.compile(
    r"^(?:[-*+>]\s*)?(?:\*\*|__)?\s*(?:작성자|작성|담당자|담당|리뷰어|리뷰\s*요청|리뷰\s*요청자|reviewers?|assignees?|"
    r"authors?|co-authored-by|signed-off-by|cc|만든\s*사람|만든이|maintainers?|contact|연락처|이메일|e-?mail|"
    r"blog|블로그|github|깃허브|깃헙|닉네임|nickname)\s*(?:\*\*|__)?\s*[:：]", re.I)
SIGN_LINE = re.compile(r"^\s*(?:[-*+]\s*)?(?:co-authored-by|signed-off-by|made by|developed by|created by|written by|"
                       r"maintained by|copyright|ⓒ|©|\(c\))(?![\w])", re.I)
ISSUE_LINE = re.compile(
    r"^\s*(?:[-*+]\s*)?(?:\*\*)?\s*(?:(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|related(?:\s+to)?|refs?|issues?|"
    r"이슈(?:\s*번호)?|관련\s*이슈|연관\s*이슈|해결\s*이슈|해결한\s*이슈|관련\s*issue)\s*(?:\*\*)?\s*[:：]?\s*)?"
    r"(?:#\d+[\s,]*)+\.?\s*$", re.I)
# 이 이름의 절은 사람 이름과 연락처가 몰려 있어 통째로 걷는다. 제목에서 기호와 빈칸을 뺀 이름과 견준다
DROP_SECTION = re.compile(
    r"(?:팀원|팀원소개|팀소개|팀구성|팀|팀명|멤버|멤버소개|구성원|만든사람|만든사람들|만든이|만든이들|개발자|개발자소개|"
    r"개발자들|개발팀|기여자|기여자들|컨트리뷰터|contributors?|members?|team|teammembers?|theteam|ourteam|authors?|"
    r"maintainers?|contacts?|연락처|문의|문의하기|credits?|licen[sc]e|라이선스|라이센스|copyright|저작권|역할분담|"
    r"sponsors?|후원|acknowledge?ments?|감사의말|감사|thanks|specialthanks|whoami|aboutme|madeby|developers?|"
    r"developedby|reviewers?|리뷰어|assignees?|담당자|작성자)")
# 프로필 사진과 프로필 링크가 든 표는 팀원 표라 통째로 걷는다
PEOPLE = re.compile(r"avatars\.githubusercontent|github\.com/[A-Za-z0-9-]+/?(?=[)\s\"'>|]|$)|팀원|닉네임|nickname", re.I)
TEAM_HEADER = re.compile(r"팀원|멤버|member|contributor|닉네임|nickname|깃허브|github", re.I)
# "용석님" 처럼 이름에 붙은 님. 역할 이름은 두고 사람 이름만 ○○ 로 가린다
NIM = re.compile(r"(?<![가-힣])([가-힣]{2,3})님")
ROLE_NIM = set("""고객 사용자 회원 선생 관리자 멘토 리뷰어 개발자 팀장 부장 과장 차장 대리 사원 대표 교수 선배 후배 부모 하느 하나
사장 작가 기자 강사 코치 리더 매니저 디자이너 기획자 담당자 운영자 판매자 구매자 작성자 질문자 팀원 조교 원장 실장 이사 회장
총장 조장 반장 크루 운영진 주인 스승 아버 어머 할머 할아버 의사 간호사 기사 스님 수녀 신부 목사 감독 셰프 마스터 오너 호스트
게스트 방문자 참가자 지원자 신청자 응답자 고수 천재 손 형 누 언니 오빠 선임 책임 수석 파트장 그룹장 센터장 본부장 상무 전무
메인테이너 기여자 컨트리뷰터 리뷰어분 모든 여러""".split())


def _owner_scrub(text, owner):
    """github.com/<owner> 꼴의 소유자 이름을 OWNER 로 바꾼다. 코드 안에도 쓴다."""
    o = re.escape(owner)
    text = re.sub(rf"(?i)(github\.com[/:]|githubusercontent\.com/){o}(?![\w-])", r"\1OWNER", text)
    text = re.sub(rf"(?i)(?<![\w.@/-]){o}/(?=[\w.-])", "OWNER/", text)  # npm i owner/repo 따위. @scope/ 는 둔다
    return re.sub(rf"(?i)(?<![\w-]){o}\.github\.io", "OWNER.github.io", text)


# 코드 속 주소에서 사람을 가리키는 자리. 코드 블록은 그대로 두되 이 자리만 OWNER 로 바꾼다
CODE_HANDLES = (
    (re.compile(r"(?i)((?:github\.com|gitlab\.com|bitbucket\.org)[/:])(?!OWNER\b)[\w.-]+"), r"\1OWNER"),
    (re.compile(r"(?i)(githubusercontent\.com/)(?!OWNER\b)[\w.-]+"), r"\1OWNER"),
    (re.compile(r"(?i)(?<![\w.-])(?!OWNER\.)[\w-]+\.(github\.io|tistory\.com|blogspot\.com|wordpress\.com)"), r"OWNER.\1"),
    (re.compile(r"(?i)((?:velog\.io|medium\.com)/)@[\w.-]+"), r"\1@OWNER"),
    (re.compile(r"(?i)((?:blog\.naver\.com/|brunch\.co\.kr/@?))(?!OWNER\b)[\w.-]+"), r"\1OWNER"),
)


def _code_scrub(line, owner, people=()):
    """코드 줄은 그대로 두되 메일과 주소 속 로그인, 개인 블로그 이름만 가린다."""
    line = EMAIL.sub("", line)
    for name in ([owner] if owner else []) + list(people):
        line = _owner_scrub(line, name)
    for rx, to in CODE_HANDLES:
        line = rx.sub(to, line)
    return line


def _fence_indented(lines):
    """빈 줄 뒤에 네 칸 들여 쓴 덩어리는 옛 마크다운의 코드 블록이라 ``` 로 감싼다.
    목록 뒤의 들여쓰기는 목록에 이어진 줄이라 둔다. 이미 ``` 안에 든 줄은 건드리지 않는다."""
    out, last, fence, i = [], "", None, 0
    ind = lambda s: s.startswith("    ") or s.startswith("\t")
    while i < len(lines):
        ln = lines[i]
        m = FENCE.match(ln)
        if fence is not None or m:
            if fence is None:
                fence = m.group(1)[0]
            elif m and m.group(1)[0] == fence and not ln.strip().lstrip(fence):
                fence = None
            out.append(ln)
            last = ln
            i += 1
            continue
        if ln.strip() and ind(ln) and (not out or not out[-1].strip()) and not LIST_LINE.match(last) and not ind(last):
            block = []
            while i < len(lines) and (ind(lines[i]) or not lines[i].strip()) and not FENCE.match(lines[i]):
                block.append(lines[i])
                i += 1
            tail = []
            while block and not block[-1].strip():
                tail.append("")
                block.pop()
            out += ["```"] + [b[4:] if b.startswith("    ") else b[1:] if b.startswith("\t") else b for b in block]
            out += ["```"] + tail
            last = "```"
            continue
        out.append(ln)
        if ln.strip():
            last = ln
        i += 1
    return out


def _drop_people_tables(lines):
    """마크다운 표 가운데 프로필 사진이나 프로필 링크가 든 표를 걷는다. 링크를 걷기 전에 봐야 해서 맨 먼저 한다."""
    out, fence, i = [], None, 0
    while i < len(lines):
        ln = lines[i]
        m = FENCE.match(ln)
        if fence is None and not m and ln.lstrip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1
            if not PEOPLE.search("\n".join(block)):
                out += block
            continue
        if m and fence is None:
            fence = m.group(1)[0]
        elif m and m.group(1)[0] == fence and not ln.strip().lstrip(fence):
            fence = None
        out.append(ln)
        i += 1
    return out


def _clean_text(chunk, owner, people):
    """코드 밖 글 한 줄을 다듬는다. <br> 과 <h1> 이 줄을 더 낼 수 있어 줄바꿈이 든 문자열로 낸다."""
    codes = []

    def keep(m):
        codes.append(_code_scrub(m.group(0), owner, people))
        return f"\x00{len(codes) - 1}\x00"

    t = re.sub(r"``[^\n]+?``|`[^`\n]+`", keep, chunk)
    t = re.sub(r"(?is)<h([1-6])[^>]*>(.*?)</h\1>", lambda m: "\n" + "#" * int(m.group(1)) + " " + m.group(2) + "\n", t)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = TAG.sub("", t)
    t = html.unescape(t).replace("\xa0", " ")
    t = re.sub(r"!\[[^\]\n]*\]\([^)\n]*\)|!\[[^\]\n]*\]\[[^\]\n]*\]", "", t)
    t = re.sub(r"\[\s*\]\([^)\n]*\)", "", t)  # 그림을 걷고 남은 배지 링크
    t = re.sub(r"\[([^\]\n]+)\]\((?:[^()\s]|\([^)\s]*\))*(?:\s+[\"'][^\n]*?[\"'])?\)", r"\1", t)
    t = re.sub(r"\[([^\]\n]+)\]\[[^\]\n]*\]", r"\1", t)
    t = re.sub(r"^\s*\[[^\]\n]+\]:\s*\S+.*$", "", t)
    t = re.sub(r"<(?:https?://|mailto:)[^>\s]+>", "", t)
    t = URL.sub(lambda m: re.search(r"[.,;:!?]*$", m.group(0)).group(0), t)
    t = EMAIL.sub("", t)
    t = PHONE.sub("", t)
    t = MENTION.sub(lambda m: m.group(0) if m.group(1) in NOT_USER else "", t)
    t = re.sub(r"(?m)^[ \t]*(?:`@[A-Za-z0-9-]+`[ \t,]*)+$", "", t)  # 백틱으로 감싼 언급만 있는 줄
    if owner:
        t = re.sub(rf"(?i)(?<![\w/.@`-])@{re.escape(owner)}/[\w.-]+", "", t)  # 소유 조직의 팀 멘션
        t = _owner_scrub(t, owner)
    for name in people:
        if len(name) >= 3:
            t = re.sub(rf"(?i)(?<![\w-]){re.escape(name)}(?![\w-])(?:\s*님)?", "", t)
    t = NIM.sub(lambda m: m.group(0) if m.group(1) in ROLE_NIM else "○○님", t)
    t = re.sub(r"[“\"'‘][^”\"'’\n]{1,15}[”\"'’]\s*님", "○○님", t)  # “닉네임”님
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], t)


def _line(raw, piece):
    """다듬은 줄을 마저 손본다. 빼야 할 줄이면 None."""
    s = piece.rstrip()
    if META_LINE.match(s.strip()) or SIGN_LINE.match(s) or ISSUE_LINE.match(s):
        return None
    if s.strip() != raw.strip():  # 걷어낸 자리에 남은 빈칸
        s = re.sub(r"(\S)[ \t]{2,}", r"\1 ", s)
        s = re.sub(r"[ \t]+([.,!?)])", r"\1", s)
        s = re.sub(r"\([ \t]*\)", "", s)
        if not raw[:1].isspace():
            s = s.lstrip()
    if re.fullmatch(r"\s*([-*_])(?:\s*\1){2,}\s*", s):
        return "---"
    s = re.sub(r"^(\s*)[*+](\s+)", r"\1-\2", s)
    s = re.sub(r"^(#{1,6})([^#\s\d])", r"\1 \2", s)  # "#12" 는 이슈 번호라 둔다
    rest = re.sub(r"^\s*(?:[-*+]|\d+[.)])?\s*(?:\[[ xX]\])?\s*", "", s)
    if not re.search(r"\w", rest) and not RULE.match(s):
        return None  # 걷고 나니 기호만 남은 줄
    return s


def _tables(rows):
    """표에서 빈 행을 걷고, 행이 다 비면 표를 통째로 걷는다. 머리에 팀원 낱말이 든 표도 걷는다."""
    out, i = [], 0
    while i < len(rows):
        ln, code = rows[i]
        if code or not ln.lstrip().startswith("|"):
            out.append((ln, code))
            i += 1
            continue
        block = []
        while i < len(rows) and not rows[i][1] and rows[i][0].lstrip().startswith("|"):
            block.append(rows[i][0])
            i += 1
        if TEAM_HEADER.search(block[0]):
            continue
        filled = [b for b in block if re.search(r"[^|\s:-]", b)]
        sep = [b for b in block if "-" in b and re.fullmatch(r"\s*\|?[\s|:-]+\|?\s*", b)]
        if len(filled) >= 2 and sep:
            out += [(filled[0], False), (sep[0], False)] + [(b, False) for b in filled[1:]]
    return out


def _sections(rows):
    """사람 이름이 몰린 절(팀원, 기여자, 라이선스 따위)을 다음 같은 수준 제목까지 걷는다."""
    out, skip = [], None
    for ln, code in rows:
        h = None if code else HEADING.match(ln)
        if h:
            level = len(h.group(1))
            if skip is not None and level <= skip:
                skip = None
            if skip is None and DROP_SECTION.fullmatch(re.sub(r"[^0-9a-z가-힣]", "", h.group(2).lower())):
                skip = level
        if skip is None:
            out.append((ln, code))
    return out


def _empty_headings(rows):
    """아래에 내용 없이 같은 수준 이상의 제목이나 글 끝이 오는 제목을 걷는다. 걷고 나서 다시 빈 제목이 생기면 또 걷는다."""
    while True:
        out = []
        for k, (ln, code) in enumerate(rows):
            h = None if code else HEADING.match(ln)
            if h:
                nxt = next(((x, c) for x, c in rows[k + 1:] if x.strip()), None)
                nh = None if nxt is None or nxt[1] else HEADING.match(nxt[0])
                if nxt is None or (nh and len(nh.group(1)) <= len(h.group(1))):
                    continue
            out.append((ln, code))
        if len(out) == len(rows):
            return out
        rows = out


def _setext(rows):
    """=== 와 --- 밑줄 제목을 # 제목으로 바꾼다."""
    out = []
    for ln, code in rows:
        prev = out[-1] if out else None
        if not code and prev and not prev[1] and re.fullmatch(r"\s*(=+|-+)\s*", ln) and prev[0].strip() \
                and not LIST_LINE.match(prev[0]) and not prev[0].lstrip().startswith(("#", "|", ">", "---")):
            out[-1] = (("# " if "=" in ln else "## ") + prev[0].strip(), False)
            continue
        out.append((ln, code))
    return out


def _spacing(rows):
    """제목과 코드 블록 앞뒤에 빈 줄을 두고, 이어진 빈 줄은 하나로 줄인다. 코드 안의 줄은 그대로 둔다."""
    out, inside = [], False
    blank = lambda: out and out[-1] != "" and out.append("")
    for ln, code in rows:
        if code:
            fence = bool(FENCE.match(ln))
            if fence and not inside:
                blank()
                inside = True
                out.append(ln)
            elif fence:
                inside = False
                out.append(ln)
                out.append("")
            else:
                out.append(ln)
        elif not ln.strip():
            blank()
        elif HEADING.match(ln):
            blank()
            out += [ln, ""]
        else:
            out.append(ln)
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


def clean_markdown(text, owner=None, people=()):
    """GitHub 마크다운을 다듬어 본문을 낸다. owner 는 저장소 소유자, people 은 본문에서 지울 로그인이다.
    코드 블록은 두되 메일과 주소 속 로그인만 가린다."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("﻿", "")
    text = re.sub(r"[​‌‍⁠]", "", text)
    text = re.sub(r"(?s)<!--.*?(?:-->|$)", "", text)
    text = re.sub(r"(?is)<table\b.*?</table>", lambda m: "" if PEOPLE.search(m.group(0)) else m.group(0), text)
    text = re.sub(r"(?is)<pre\b[^>]*>(.*?)</pre>",
                  lambda m: "\n```\n" + html.unescape(TAG.sub("", m.group(1))).strip("\n") + "\n```\n", text)
    rows, fence = [], None
    for ln in _fence_indented(_drop_people_tables(text.split("\n"))):
        m = FENCE.match(ln)
        if fence is None and m:
            fence = m.group(1)[0]
            rows.append((re.sub(r"^(\s*)~{3,}", r"\1```", ln), True))
        elif fence is not None:
            if m and m.group(1)[0] == fence and not ln.strip().lstrip(fence):
                rows.append((re.sub(r"^(\s*)~{3,}", r"\1```", ln), True))
                fence = None
            else:
                rows.append((_code_scrub(ln, owner, people), True))
        elif not ln.strip():
            rows.append(("", False))
        else:
            for piece in _clean_text(ln, owner, people).split("\n"):
                s = _line(ln, piece)
                if s is not None:
                    rows.append((s, False))
    if fence is not None:
        rows.append(("```", True))
    return _spacing(_empty_headings(_sections(_tables(_setext(rows)))))


# --- 거르기 -------------------------------------------------------------------

SURNAMES = "김이박최정강조윤장임한오서신권황안송류유전홍고문양손배백허남심노하곽성차주우구민나진지엄채원천방공현함변염여추도소석선설마길연위표명기반라왕금옥육인맹제모탁국어은편용예경봉사부"
NAME_END = re.compile(rf"(?<=[\s,(/])([{SURNAMES}][가-힣]{{2}})\s*[),]?\s*$")


def roster(body):
    """목록 항목과 표 칸 끝에 붙은 세 글자 이름 후보. 담당자 이름을 줄 끝에 단 할 일 목록을 가린다.
    "안된다" 같은 낱말도 걸려서 서로 다른 후보가 세 개 이상일 때만 명단으로 본다."""
    names = set()
    for ln in body.splitlines():
        s = ln.strip()
        if not re.match(r"(?:[-*+]|\d+[.)])\s|\|", s):
            continue
        for cell in (s.strip("|").split("|") if s.startswith("|") else [s]):
            m = NAME_END.search(" " + cell.strip())
            if m:
                names.add(m.group(1))
    return names

ENDS = ("다", "요", "까", "죠", "네", "시오")


def prose_text(body):
    """코드 블록과 인라인 코드, 주소를 걷은 글. 길이와 한글 비율은 이것으로 잰다."""
    t = re.sub(r"(?ms)^\s*```.*?^\s*```[^\n]*$", "", body)
    t = re.sub(r"``[^\n]+?``|`[^`\n]+`", "", t)
    return URL.sub("", t).strip()


def hangul_ratio(text):
    h = len(re.findall(r"[가-힣]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return h / (h + latin) if h + latin else 0.0


def prose_sentences(text):
    """목록과 표, 제목, 인용을 뺀 줄글 줄에서 한국어 종결로 끝나는 문장 수."""
    n = 0
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith(("#", "|", ">", "---")) or LIST_LINE.match(s):
            continue
        for sent in re.split(r"(?<=[.!?])\s+", s):
            tail = re.sub(r"[^\w]+$", "", sent)
            tail = re.sub(r"[ㄱ-ㅎㅏ-ㅣ_]+$", "", tail)
            if len(sent) >= 8 and tail.endswith(ENDS):
                n += 1
    return n


def verdict(body):
    """통과하면 None, 아니면 떨어진 까닭."""
    text = prose_text(body)
    if not MIN_CHARS <= len(text) <= MAX_CHARS:
        return "length"
    if hangul_ratio(text) < MIN_HANGUL:
        return "hangul"
    if prose_sentences(text) < MIN_SENTENCES:
        return "sentences"
    if len(roster(body)) >= 3:
        return "names"
    return None


# --- 쓰기 ---------------------------------------------------------------------

def doc_id(prefix, url):
    return f"{prefix}-{hashlib.sha1(url.encode('utf-8')).hexdigest()[:10]}"


def clean_title(title, owner=None, people=()):
    """제목을 본문처럼 다듬는다. "[미션] 닉네임(이름) 제출" 과 "[12기 이름]" 꼴의 이름도 걷는다."""
    t = " ".join(_clean_text(title.replace("\n", " "), owner, people).split())
    t = re.sub(r"(\]\s*)[^\s()\[\]]{1,15}\([^\s()]{1,15}\)\s*", r"\1", t)
    t = re.sub(r"\[\s*\d+\s*기[^\]]*\]\s*", "", t)  # "[12기 이름]" 꼴의 기수와 이름
    return re.sub(r"^#+\s*", "", t).strip(" -:|")


def signature(body):
    """겹친 글을 가리는 지문. 줄글과 목록의 열 자 넘는 줄 모음이다."""
    lines = (re.sub(r"^\s*(?:[-*+]|\d+[.)])\s*", "", ln).strip() for ln in prose_text(body).splitlines())
    return {ln for ln in lines if len(ln) >= 10 and not ln.startswith("#")}


def is_dup(sig, sigs, limit=0.5):
    return any(sig and other and len(sig & other) / len(sig | other) >= limit for other in sigs)


def existing(out_dir):
    """이미 받은 글의 url 과 저장소별 개수, 지문. 다시 돌리면 이어서 받는다."""
    seen, per_repo, sigs = set(), Counter(), []
    for f in out_dir.glob("*.json"):
        url = json.loads(f.read_text(encoding="utf-8"))["url"]
        seen.add(url)
        per_repo["/".join(url.split("/")[3:5]).lower()] += 1
        sigs.append(signature(f.with_suffix(".md").read_text(encoding="utf-8").split("\n", 2)[-1]))
    return seen, per_repo, sigs


def write_doc(out_dir, did, title, body, meta):
    (out_dir / f"{did}.md").write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
    (out_dir / f"{did}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def round_robin(streams, want, have, take):
    """해마다 후보 흐름을 하나씩 두고 돌아가며 한 편씩 받는다. take(후보)가 참이면 받은 것이다."""
    active = list(streams.items())
    while have < want and active:
        for year, it in list(active):
            for cand in it:
                if take(cand):
                    have += 1
                    break
            else:
                active.remove((year, it))
            if have >= want:
                break
    return have


def searched(endpoint, queries, year, pages=10):
    """한 해의 검색 결과를 검색 순서대로 낸다. 쿼리 여럿이면 앞 쿼리부터 끝까지 본다."""
    end = "2022-11-29" if year == 2022 else f"{year}-12-31"
    for q in queries:
        for page in range(1, pages + 1):
            res = gh(endpoint, {"q": f"{q} created:{year}-01-01..{end}", "per_page": 100, "page": page}, search=True)
            items = (res or {}).get("items") or []
            for item in items:
                yield item
            if len(items) < 100:
                break


# --- PR 설명 -------------------------------------------------------------------

def pr_people(detail):
    """PR 에 이름이 걸린 로그인. 작성자, 브랜치 주인, 머지한 사람, 담당자, 리뷰 요청을 받은 사람이다."""
    users = [detail.get("user"), (detail.get("head") or {}).get("user"), detail.get("merged_by")]
    users += (detail.get("assignees") or []) + (detail.get("requested_reviewers") or [])
    return [u["login"] for u in users if u and u.get("login")]


def title_from_branch(title, detail):
    """제목이 한 낱말짜리 브랜치 이름을 그대로 옮긴 것인가. GitHub 는 PR 제목을 브랜치 이름으로 채우는데,
    "yhlee" 처럼 한 낱말짜리 브랜치 이름은 사람 이름이나 로그인인 경우가 있다. 여러 낱말이면 설명이라 둔다."""
    ref = (detail.get("head") or {}).get("ref", "")
    norm = lambda x: re.sub(r"[^0-9a-z가-힣]", "", x.lower())
    return bool(ref) and len(title.split()) == 1 and norm(title) in (norm(ref), norm(ref.split("/")[-1]))


def fetch_github_pr(out_dir=DATA / "human" / "github-pr", want=30):
    """한국어 PR 설명을 모은다. 검색 API 의 PR 본문을 그대로 쓰고, 본문을 통과한 PR 의 저장소만 라이선스를 본다."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seen, per_repo, sigs = existing(out_dir)
    drop = Counter()

    def take(item):
        url = item.get("html_url", "")
        if url in seen or "/pull/" not in url:
            return False
        seen.add(url)
        full = "/".join(url.split("/")[3:5])
        if per_repo[full.lower()] >= PER_REPO:
            drop["per-repo"] += 1
            return False
        user = item.get("user") or {}
        if user.get("type") == "Bot" or user.get("login", "").endswith("[bot]"):
            drop["bot"] += 1
            return False
        if not item.get("created_at", "9") < CUTOFF:
            drop["date"] += 1
            return False
        raw = item.get("body") or ""
        why = verdict(clean_markdown(raw))
        if why:
            drop[why] += 1
            return False
        meta = repo_meta(full)
        if meta["license"] not in LICENSES:
            drop["license"] += 1
            return False
        if meta["fork"]:  # 포크의 PR 은 원래 저장소의 PR 을 옮긴 것이 많다
            drop["fork"] += 1
            return False
        detail = gh(f"repos/{full}/pulls/{item['number']}") or {}
        people = [user.get("login", "")] + ([meta["owner"]] if meta["user_owner"] else []) + pr_people(detail)
        body = clean_markdown(raw, meta["owner"], people)
        why = verdict(body)
        if why:
            drop[why] += 1
            return False
        sig = signature(body)
        if is_dup(sig, sigs):
            drop["dup"] += 1
            return False
        title = "" if title_from_branch(item.get("title", ""), detail) else item.get("title", "")
        title = clean_title(title, meta["owner"], people) or "PR"
        did = doc_id("pr", url)
        write_doc(out_dir, did, title, body, {
            "kind": "pr", "label": "PR 설명", "source": "github-pr", "date": item["created_at"][:10],
            "url": url, "license": meta["license"]})
        per_repo[full.lower()] += 1
        sigs.append(sig)
        log(f"  PR {item['created_at'][:10]} {did} {len(prose_text(body))}자")
        return True

    streams = {y: searched("search/issues", [f"{q} is:pr is:merged" for q in PR_QUERIES], y) for y in YEARS}
    have = round_robin(streams, want, len(seen), take)
    log(f"github-pr: {have}편, 떨어진 까닭 {dict(drop)}")
    return have


# --- README -------------------------------------------------------------------

def readme_at_cutoff(full):
    """(경로, 커밋 sha, 커밋 날짜, 본문, 커밋한 로그인). 2022-11-30 전 마지막 커밋의 README 를 읽는다. 없으면 None."""
    paths = ["README.md"]
    cur = gh(f"repos/{full}/readme")
    if cur and cur.get("path") and cur["path"] not in paths:
        paths.append(cur["path"])
    for path in paths:
        if not path.lower().endswith((".md", ".markdown")):
            continue
        commits = gh(f"repos/{full}/commits", {"path": path, "until": CUTOFF, "per_page": 1})
        if not commits:
            continue
        sha = commits[0]["sha"]
        day = commits[0]["commit"]["committer"]["date"]
        if not day < CUTOFF:
            continue
        blob = gh(f"repos/{full}/contents/{urllib.parse.quote(path)}", {"ref": sha})
        if not blob or blob.get("encoding") != "base64" or not blob.get("content"):
            continue
        data = base64.b64decode(blob["content"])
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:  # 옛 README 가운데 cp949 로 저장한 것이 있다
            text = data.decode("cp949", "replace")
        return path, sha, day, text, (commits[0].get("author") or {}).get("login", "")
    return None


def readme_title(body, name):
    """첫 줄이 제목이면 그 제목을 쓰고 본문에서 뺀다. 아니면 저장소 짧은 이름을 쓴다.
    글 중간의 제목을 끌어오면 그 절의 제목이 사라져서 첫 줄만 본다."""
    lines = body.split("\n")
    first = next((k for k, ln in enumerate(lines) if ln.strip()), None)
    pick = first if first is not None and HEADING.match(lines[first]) else None
    if pick is not None:
        title = HEADING.match(lines[pick]).group(2).strip() if HEADING.match(lines[pick]) else ""
        if re.search(r"[\w가-힣]", title):
            rest = lines[:pick] + lines[pick + 1:]
            while rest and not rest[0].strip():
                rest.pop(0)
            return title, "\n".join(rest)
    return name, body


def fetch_github_readme(out_dir=DATA / "human" / "github-readme", want=30):
    """한국어 README 를 모은다. 저장소 검색 결과의 라이선스로 먼저 거르고, 2022-11-30 전 마지막 판을 읽는다.
    저장소는 만든 해로 나눠 돌아가며 받고, 판의 해마다 want/7 + 1 편까지만 받는다.
    언어별 README(README.ko.md 따위)는 번역일 수 있어 보지 않는다."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seen, per_repo, sigs = existing(out_dir)
    done_repos = set(per_repo)
    drop = Counter()
    # 활발한 저장소는 컷오프 전 마지막 판이 2022년에 몰려서, 판의 해마다 상한을 둔다
    cap = -(-want // len(YEARS)) + 1
    per_year = Counter(json.loads(f.read_text(encoding="utf-8"))["date"][:4] for f in out_dir.glob("*.json"))

    def take(repo):
        full = repo["full_name"]
        if full.lower() in done_repos or repo.get("fork"):
            return False
        done_repos.add(full.lower())
        lic = (repo.get("license") or {}).get("spdx_id")
        if lic not in LICENSES:
            drop["license"] += 1
            return False
        got = readme_at_cutoff(full)
        if not got:
            drop["no-readme-before-cutoff"] += 1
            return False
        path, sha, day, text, author = got
        if per_year[day[:4]] >= cap:
            drop["year-cap"] += 1
            return False
        owner = (repo.get("owner") or {}).get("login", full.split("/")[0])
        people = [author] + ([owner] if (repo.get("owner") or {}).get("type") == "User" else [])
        body = clean_markdown(text, owner, people)
        title, body = readme_title(body, repo.get("name", full.split("/")[1]))
        title = clean_title(title, owner, people) or repo.get("name", "")
        why = verdict(body)
        if why:
            drop[why] += 1
            return False
        sig = signature(body)
        if is_dup(sig, sigs):  # 템플릿을 그대로 쓴 README
            drop["dup"] += 1
            return False
        sigs.append(sig)
        url = f"https://github.com/{full}/blob/{sha}/{urllib.parse.quote(path)}"
        did = doc_id("readme", url)
        write_doc(out_dir, did, title, body, {
            "kind": "guide", "label": "가이드·README·위키", "source": "github-readme", "date": day[:10],
            "url": url, "license": lic})
        per_year[day[:4]] += 1
        log(f"  README {day[:10]} {did} {len(prose_text(body))}자 (저장소 {repo.get('created_at', '')[:4]})")
        return True

    streams = {y: searched("search/repositories", README_QUERIES, y) for y in YEARS}
    have = round_robin(streams, want, len(seen), take)
    log(f"github-readme: {have}편, 떨어진 까닭 {dict(drop)}")
    return have


if __name__ == "__main__":
    fetch_github_pr(DATA / "human" / "github-pr", want=30)
    fetch_github_readme(DATA / "human" / "github-readme", want=30)
