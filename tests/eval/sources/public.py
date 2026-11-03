#!/usr/bin/env python3
"""docs-suit 평가용으로 사람이 쓴 한국어 공공 문서를 모으는 어댑터.

어댑터는 두 가지이고 둘 다 표준 라이브러리만 쓴다(Python 3.9).

  fetch_kdca_health(out_dir, want=30)   국가건강정보포털의 환자 안내문
  fetch_seoul_report(out_dir, want=30)  서울 정보소통광장 결재문서 가운데 보고서 서식의 계획·검토 보고

문서 한 편은 <id>.md 와 <id>.json 두 파일로 남는다. <id>.md 에는 제목과 다듬은 마크다운 본문을 쓴다.
<id>.json 에는 kind, label, source, date, date_basis, url, license 를 쓴다.
받은 응답은 ~/.cache/docs-suit-eval/raw/<source>/ 에 담아 두어서 다시 돌려도 서버를 또 부르지 않는다.
실행 보고(받은 문서와 건너뛴 후보, 그 까닭)는 그 캐시 옆에 _report.json 으로 쓴다.

2022-11-30(ChatGPT 공개일) 전에 쓴 글만 남긴다.
"""
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser

CUTOFF = '2022-11-30'           # 글은 이 날보다 앞서야 한다
CDX_TO = '20221129'             # Wayback 사본은 이 날까지만 받는다
RAW_DIR = os.path.expanduser('~/.cache/docs-suit-eval/raw')   # 출처마다 하위 폴더를 하나씩 둔다
UA = 'Mozilla/5.0 (compatible; docs-suit-eval/0.1; research sample, low rate)'
MIN_CHARS, MAX_CHARS, MIN_SENTENCES = 300, 3000, 5

KOGL4 = '공공누리 제4유형(출처표시+상업적 이용금지+변경금지)'


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- 받기

class Fetcher:
    """서버에 부담을 덜 주는 GET/POST. 호스트마다 간격을 두고 robots.txt 를 따른다.
    실패하면 점점 길게 쉬었다가 다시 부르고, 받은 응답은 디스크에 담아 둔다."""

    def __init__(self, cache_dir, delays=None):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.delays = delays or {}
        self.last = {}
        self.robots = {}

    def _delay(self, host):
        return max(0.5, self.delays.get(host, 0.8))

    def allowed(self, url):
        p = urllib.parse.urlsplit(url)
        host = p.scheme + '://' + p.netloc
        if host not in self.robots:
            rp = urllib.robotparser.RobotFileParser(host + '/robots.txt')
            try:
                rp.read()          # 404 는 모두 허락하고 401/403 은 모두 막는다
            except Exception as e:  # robots.txt 를 못 읽으면 조심스럽게 모두 막는다
                log('robots.txt unreadable for', host, e)
                rp.disallow_all = True
            self.robots[host] = rp
        return self.robots[host].can_fetch(UA, url)

    def get(self, url, data=None, cache=True):
        key = hashlib.sha1((url + '\0' + (data or '')).encode()).hexdigest()
        path = os.path.join(self.cache_dir, key)
        if cache and os.path.exists(path):
            with open(path, 'rb') as f:
                return f.read()
        if not self.allowed(url):
            raise PermissionError('robots.txt disallows ' + url)
        host = urllib.parse.urlsplit(url).netloc
        body = data.encode() if data is not None else None
        for attempt in range(6):
            wait = self._delay(host) - (time.time() - self.last.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            req = urllib.request.Request(url, data=body, headers={'User-Agent': UA})
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    raw = r.read()
                self.last[host] = time.time()
                break
            except urllib.error.HTTPError as e:
                self.last[host] = time.time()
                if e.code == 429 or e.code >= 500:
                    pause = e.headers.get('Retry-After')
                    pause = int(pause) if pause and pause.isdigit() else 10 * 2 ** attempt
                    log('HTTP', e.code, 'backing off', pause, 's', url)
                    time.sleep(min(pause, 300))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                self.last[host] = time.time()
                log('network error, retrying', e, url)
                time.sleep(10 * 2 ** attempt)
        else:
            raise RuntimeError('gave up on ' + url)
        if cache:
            with open(path, 'wb') as f:
                f.write(raw)
        return raw

    def text(self, url, data=None):
        raw = self.get(url, data)
        for enc in ('utf-8', 'cp949'):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                pass
        return raw.decode('utf-8', 'replace')


# ---------------------------------------------------------------- 공통 다듬기

class BlockParser(HTMLParser):
    """HTML 을 (kind, text) 블록 목록으로 바꾼다. kind 는 'h', 'li', 'p' 가운데 하나다.

    표와 스크립트, 미디어, 입력 양식은 통째로 건너뛴다.
    """
    BLOCK = {'p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'tr', 'ul',
             'ol', 'dd', 'dt', 'dl', 'section', 'article', 'blockquote'}
    SKIP = {'script', 'style', 'table', 'object', 'noscript', 'iframe',
            'button', 'select', 'form', 'embed', 'video', 'audio', 'svg'}
    HEAD = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self.cur, self.kind, self.skip = [], [], 'p', 0

    def flush(self):
        t = ' '.join(''.join(self.cur).split())
        if t:
            self.blocks.append((self.kind, t))
        self.cur, self.kind = [], 'p'

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == 'br':
            self.flush()
        elif tag in self.BLOCK:
            self.flush()
            if tag in self.HEAD:
                self.kind = 'h'
            elif tag == 'li':
                self.kind = 'li'

    def handle_startendtag(self, tag, attrs):
        if tag == 'br' and not self.skip:
            self.flush()

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if not self.skip and tag in self.BLOCK:
            self.flush()

    def handle_data(self, d):
        if not self.skip:
            self.cur.append(d)


def html_blocks(fragment):
    p = BlockParser()
    p.feed(fragment)
    p.close()
    p.flush()
    return p.blocks


BULLET_RE = re.compile(r'^(?:[•·○◦◯●◎▪∙⦁▶▷►◆◇■√✓✔➢➤˚]|ㅇ(?=\s)|-(?=\s)|o(?=\s))\s*')
SENT_END_RE = re.compile(r'[가-힣\)][.!?](?=\s|$)')
PRED_END_RE = re.compile(r'(다|요|함|음|임|됨|짐|것|기|중|정|람|림|시오|세요)[.!?)]*$')


def md_line(kind, text, heading_prefix='### '):
    """블록 하나를 마크다운 한 줄로 바꾼다. 글머리 기호는 '- ' 로 맞춘다."""
    text = re.sub(r'\s+[˚•·○◦]$', '', text.strip())          # 줄 끝에 홀로 남은 글머리 기호를 걷는다
    if kind == 'h':
        return heading_prefix + text
    if text.startswith('□'):
        return text.lstrip('□ ').strip()
    m = BULLET_RE.match(text)
    if kind == 'li' or m:
        return '- ' + (text[m.end():] if m else text).lstrip('·•◦○˚ ').strip()
    return text


VERBAL_RE = re.compile(r'(하고|하여|하며|하는|하기|되어|되고|되는|되며|있는|있어|있고|없는|위해|위한|따라|통해|따른)(?![가-힣])')
REFERENCE_RE = re.compile(r'-\s?\d+\s?\(\s?\d{2,4}\.|호\s?[『「"“]|『[^』]*』\s*$')


def count_sentences(lines):
    """줄글 문장 수에 문장 구실을 하는 목록 항목 수를 더해 센다.

    문장 부호로 끝나지 않는 줄은 두 경우에 한 번 센다. 하나는 서술어(…함, …임, …다)로 끝나는 줄이다.
    다른 하나는 …하여, …위한, …따라 같은 동사 꼴이 든 다섯 낱말 이상의 개조식 항목이다.
    제목과 다른 문서를 가리키는 줄("○○과-1234(2022.3.2.)호 『…』")은 세지 않는다.
    """
    n = 0
    for ln in lines:
        if ln.startswith('#'):
            continue
        body = ln[2:] if ln.startswith('- ') else ln
        if REFERENCE_RE.search(body):
            continue
        hits = len(SENT_END_RE.findall(body))
        if hits:
            n += hits
        elif len(body.split()) >= 4 and PRED_END_RE.search(body):
            n += 1
        elif len(body.split()) >= 5 and VERBAL_RE.search(body):
            n += 1
    return n


def body_len(lines):
    return sum(len(ln) for ln in lines)


# --- 개인정보
SURNAMES = set('김이박최정강조윤장임한오서신권황안송류전홍고문양손배백허유남심노하곽성차주우구민진나지엄채원천방공현함변염여추도소석선설마길연위표명기반라왕금옥육인맹제모탁국어은편용예경봉사부')
RANK = (r'주무관|실무관|사무관|서기관|부이사관|이사관|주사보?|서기보?|팀장|과장|국장|실장|본부장|단장|센터장|'
        r'소장|대장|반장|부장|차장|원장|관장|담당관|담당자|담당|작성자|보고자|기안자|검토자|결재자|협조자|'
        r'소방[정령경위장교사]|소방관|대원|구청장|부구청장|시장|부시장|의원|위원장|위원|교수|박사|전문의|간호사|'
        r'참석자|발표자|강사|사회자|진행자|면담자|대상자|대표이사|이사장|사장|대표')
STOP_NAMES = {'관련', '결과', '계획', '보고', '추진', '현황', '예정', '실시', '운영', '사업', '정책', '전체', '기타',
              '주관', '협조', '시행', '접수', '공개', '부분', '방침', '문서', '결재', '일자', '번호', '대상', '조사',
              '점검', '관리', '지원', '확인', '검토', '회의', '교육', '훈련', '예방', '대응', '안전', '소방', '총무',
              '행정', '도시', '주택', '교통', '환경', '복지', '문화', '경제', '재정', '정보', '홍보', '시민', '서울',
              '장비', '구급', '구조', '진압', '상황', '전산', '통신', '자원', '기획', '감사', '인사', '조직', '법무',
              '기전', '도로', '시설', '공원', '수도', '상수', '하수', '건설', '설계', '공사', '감독', '평가', '심사',
              '각', '및', '등', '외', '전', '후', '내', '중', '이상', '이하', '미만', '초과', '포함', '제외', '해당',
              '명', '이외', '참석', '참여', '주재', '당직', '비번', '근무', '전원', '인원', '직원', '전담', '전문',
              '신규', '기존', '연장', '변경', '정상', '비상', '긴급', '임시', '일반', '특별', '방문', '현장', '자체',
              '기준', '구성', '구분', '시간', '지역', '정도', '정기', '조치', '이후', '이전', '이내', '연간', '연도',
              '신청', '성과', '주요', '우수', '방안', '대책', '공지', '공문', '장소', '일시', '내용', '기간', '목적',
              '방법', '개요', '배경', '필요', '효과', '문제', '향후', '차기', '금년', '전년', '추가', '진행', '완료',
              '표준', '사용', '소요', '예산', '비용', '금액', '인력', '장애', '노인', '아동', '청년', '여성', '가족',
              '주민', '구민', '구청', '시청', '본청', '차량', '전화', '명단', '위탁', '민간', '공공', '국가', '지방',
              '정부', '국비', '시비', '구비', '경찰', '보건', '의료', '병원', '학교', '유관', '관계', '기관', '단체',
              '협회', '위원회', '위원', '전달', '통보', '공유', '안내', '홍보물', '제출', '요청', '협의', '조정',
              '하는', '하여', '하게', '하고', '하며', '하기', '하면', '하지', '해야', '한다', '함께', '한편', '하나',
              '하반기', '상반기', '분기', '연말', '연초', '금일', '익일', '전일', '당일', '주간', '야간', '오전', '오후'}
PARTICLE_END = re.compile(r'[을를에의와과만께로]$')
PHONE_RE = re.compile(r'\(?\s*☎?\s*0\d{1,2}\s*[)\-.]\s*\d{3,4}\s*[-.]\s*\d{4}\s*\)?|☎\s*[\d\-]{3,}|'
                      r'(?:전화|전송|팩스|FAX|Tel|TEL)\s*[:：]?\s*[\d\-()\s]{7,}')
EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')



def _looks_like_name(tok, text, end):
    return (tok[0] in SURNAMES and tok not in STOP_NAMES and not re.fullmatch(RANK, tok)
            and not PARTICLE_END.search(tok) and not re.match(r'\s*-\s*\d', text[end:end + 4]))


NAME = r'([가-힣]{2,3})(?![가-힣])'
DATE_MD = r'(?<![\d/.])\d{1,2}/\d{1,2}(?![\d/])'


def find_names(text, approval_block=False):
    """결재문서에 든 사람 이름을 찾는다.

    어디서나 직급이나 역할 낱말의 바로 뒤나 바로 앞에 붙은 이름을 잡는다.
    결재 칸과 발신 꼬리말에서는 세 가지를 더 잡는다. 결재 날짜 옆의 이름("06/30 홍길동", "홍길동 06/30")과
    代(대결) 뒤의 이름, 이미 찾은 이름에 이어 나오는 이름이다. 결재자는 한 줄에 나란히 적힌다.
    """
    # 결재 칸 밖에서는 세 음절 이름만 잡는다. 거기서 걸리는 두 음절 낱말은
    # 대개 안건 명사다("위원장 선출", "위원 소개").
    nm = NAME if approval_block else r'([가-힣]{3})(?![가-힣])'
    pats = [r'(?:%s)(?:\s*[:：]\s*|\s+)(?:%s\s+)?(?:代\s*)?%s' % (RANK, DATE_MD, nm),
            r'(?<![가-힣])%s\s+(?:%s)(?![가-힣])' % (nm, RANK)]
    if approval_block:
        pats += [r'%s\s+(?:代\s*)?%s' % (DATE_MD, NAME),
                 r'(?<![가-힣])%s\s+%s' % (NAME, DATE_MD),
                 r'代\s*%s' % NAME]
    text = re.sub(r'(대|작|담|보|참)\s(상|성|당|고|석)\s자', r'\1\2자', text)
    found = set()
    for p in pats:
        for m in re.finditer(p, text):
            if _looks_like_name(m.group(1), text, m.end(1)):
                found.add(m.group(1))
    # 찾은 이름 옆에 나열된 이름도 잡는다. "홍길동, 김철수 의원" 꼴이나 한 줄에 나란히 적힌 결재자다
    sep = r'\s+(?:代\s*)?' if approval_block else r'\s*[,·]\s*'
    for _ in range(3):
        more = set()
        for nm in found:
            for p in (r'(?<![가-힣])%s%s([가-힣]{3})(?![가-힣])' % (re.escape(nm), sep),
                      r'(?<![가-힣])([가-힣]{3})%s%s(?![가-힣])' % (sep, re.escape(nm))):
                for m in re.finditer(p, text):
                    if _looks_like_name(m.group(1), text, m.end(1)):
                        more.add(m.group(1))
        if more <= found:
            break
        found |= more
    return found


def scrub(text, names=()):
    """전화번호와 메일 주소, 넘겨받은 사람 이름을 지운다."""
    text = EMAIL_RE.sub('', text)
    text = PHONE_RE.sub('', text)
    for nm in sorted(set(names), key=len, reverse=True):
        text = re.sub(r'(?<![가-힣])%s(?![가-힣])' % re.escape(nm), '', text)
    text = re.sub(r'\(\s*[,/]?\s*\)', '', text)
    text = re.sub(r'\(\s*[,·]?\s*', '(', text)              # 이름을 지운 자리에 남은 "(, 의원)" 의 쉼표를 걷는다
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return re.sub(r'\s+([,.)])', r'\1', text).strip()


def write_doc(out_dir, doc_id, title, lines, meta):
    os.makedirs(out_dir, exist_ok=True)
    paras = []
    for ln in lines:
        # 블록 사이에는 빈 줄을 두되, 이어진 목록 항목은 붙여 둔다
        if paras and ln.startswith('- ') and paras[-1].startswith('- '):
            paras[-1] += '\n' + ln
        else:
            paras.append(ln)
    md = '# %s\n\n%s\n' % (title.strip(), '\n\n'.join(paras))
    with open(os.path.join(out_dir, doc_id + '.md'), 'w', encoding='utf-8') as f:
        f.write(md)
    with open(os.path.join(out_dir, doc_id + '.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
        f.write('\n')


def passes(lines):
    n = body_len(lines)
    return MIN_CHARS <= n <= MAX_CHARS and count_sentences(lines) >= MIN_SENTENCES


# ---------------------------------------------------------------- kdca-health

KDCA_NEW_PATH = 'healthinfo/biz/health/gnrlzHealthInfo/gnrlzHealthInfo/gnrlzHealthInfoView.do'
KDCA_OLD_PATH = 'health/HealthInfoArea/HealthInfo/View.do'
# 환자나 보호자에게 하는 안내로 읽히는 절 이름이다.
GUIDE_RE = re.compile(r'예방|관리|주의|생활|병원|대처|실천|응급|비약물|정기 ?진찰|수칙|가이드|자가|권장|올바른')
NOT_GUIDE_RE = re.compile(r'질병관리청|참고문헌|연관|주제어|통계|지원체계')


def _cdx(fetcher, url, prefix=True):
    q = {'url': url, 'to': CDX_TO, 'output': 'json', 'filter': 'statuscode:200',
         'fl': 'timestamp,original,mimetype', 'limit': '20000'}
    if prefix:
        q['matchType'] = 'prefix'
    rows = json.loads(fetcher.text('https://web.archive.org/cdx/search/cdx?' + urllib.parse.urlencode(q)) or '[]')
    return [dict(zip(rows[0], r)) for r in rows[1:]] if rows else []


def _kdca_candidates(fetcher):
    """2022-11-29 또는 그 전의 Wayback 사본이 있는 페이지를 낸다. id 마다 가장 새 사본부터 늘어놓는다.

    2020-2022 판 화면을 먼저 콘텐츠 id 순으로 낸다. 이 판은 health.kdca.go.kr 과
    그 전 도메인인 health.cdc.go.kr 에서 찾는다. 그다음 같은 포털의 2017-2020 판 화면을 콘텐츠 id 순으로 낸다.
    """
    pools = []
    for host, path, key, layout in (
            ('health.kdca.go.kr', KDCA_NEW_PATH, 'cntnts_sn', 'new'),
            ('health.cdc.go.kr', KDCA_NEW_PATH, 'cntnts_sn', 'new'),
            ('health.cdc.go.kr', KDCA_OLD_PATH, 'idx', 'old')):
        snaps = {}
        for r in _cdx(fetcher, host + '/' + path):
            if r.get('mimetype') != 'text/html':
                continue
            m = re.search(r'[?&;]%s=(\d+)' % key, r['original'].replace('&amp;', '&'))
            if not m:
                continue
            snaps.setdefault(m.group(1), []).append(r)
        pools.append((host, layout, snaps))
    seen, out = set(), []
    new_ids = {}
    for host, layout, snaps in pools:
        if layout == 'new':
            for cid, rows in snaps.items():
                new_ids.setdefault(cid, []).extend((host, r) for r in rows)
    for cid in sorted(new_ids, key=int):
        rows = sorted(new_ids[cid], key=lambda hr: hr[1]['timestamp'], reverse=True)
        out.append(('new', cid, rows))
    for host, layout, snaps in pools:
        if layout == 'old':
            for cid in sorted(snaps, key=int):
                rows = sorted(((host, r) for r in snaps[cid]), key=lambda hr: hr[1]['timestamp'], reverse=True)
                out.append(('old', cid, rows))
    return out


def _kdca_parse_new(h):
    title = re.search(r'id="subContentSj">([^<]*)<', h)
    if not title:
        return None
    upd = re.search(r'업데이트\s*:\s*(?:</strong>)?\s*(\d{4}-\d{2}-\d{2})', h)
    names = dict((d, n.strip()) for n, d in re.findall(r"menuClick\(\s*'([^']*)'\s*,\s*'(contentsDiv\d+)'", h))
    starts = [(m.start(), m.group(1)) for m in re.finditer(r'<div id="(contentsDiv\d+)"', h)]
    end_all = len(h)
    for marker in ('<ul class="rating"', 'class="open-box"', 'id="footer"', '<!-- //print-content'):
        i = h.find(marker, starts[-1][0] + 1 if starts else 0)
        if i > 0:
            end_all = min(end_all, h.rfind('<', 0, i + 1))     # 그 태그가 시작하는 자리에서 자른다
    sections = []
    for i, (pos, div) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else end_all
        frag = h[pos:end]
        head = re.search(r'<h3>([^<]*)</h3>', frag)
        name = names.get(div) or (head.group(1).strip() if head else '')
        if head:
            frag = frag[:head.start()] + frag[head.end():]
        sections.append((name, html_blocks(frag)))
    return {'title': html.unescape(title.group(1)).strip(), 'date': upd.group(1) if upd else None,
            'sections': sections}


def _kdca_parse_old(h):
    title = re.search(r'<meta property="og:title" content="([^"]*)"', h)
    upd = re.search(r'alt="수정일"\s*/?>\s*(\d{4}-\d{2}-\d{2})', h)
    start = h.find('class="sub01_01"')
    if not title or start < 0:
        return None
    end = h.find('btn_listview', start)
    end = h.rfind('<div style="text-align:center', start, end) if end > 0 else len(h)
    body = h[start:end if end > start else len(h)]
    body = re.sub(r'<h4>\s*연관 검색어\s*</h4>[^<]*', '', body)
    chunks = re.split(r"<div id\s*=\s*'tagID\d+'\s*>\s*</div>", body)[1:]
    sections = []
    for frag in chunks:
        head = re.search(r'<h2>(.*?)</h2>', frag, re.S)
        name = re.sub(r'<[^>]+>|\s+', ' ', head.group(1)).strip() if head else ''
        if head:
            frag = frag[:head.start()] + frag[head.end():]
        sections.append((name, html_blocks(frag)))
    return {'title': html.unescape(title.group(1)).strip(), 'date': upd.group(1) if upd else None,
            'sections': sections}


def _kdca_lines(blocks):
    lines = []
    for kind, text in blocks:
        text = scrub(text)
        if not text or re.fullmatch(r'[\W\d_]*', text):
            continue
        if re.search(r'작성 및 감수|^출처\s*:|^참고\s*:|^자료\s*:', text):
            continue
        lines.append(md_line(kind, text))
    return lines


def _kdca_doc(parsed):
    """안내 절을 페이지 순서대로 고른다. 절은 통째로만 담고, 모두 합쳐 MAX_CHARS 까지 담는다."""
    picked, names = [], []
    for name, blocks in parsed['sections']:
        if not name or not GUIDE_RE.search(name) or NOT_GUIDE_RE.search(name):
            continue
        sec = _kdca_lines(blocks)
        if body_len(sec) < 80:
            continue
        sec = ['## ' + re.sub(r'\s*-\s*', ' - ', name).strip()] + sec
        if body_len(picked) + body_len(sec) > MAX_CHARS:
            continue
        picked += sec
        names.append(name)
    return picked, names


def _norm_title(t):
    return re.sub(r'\([^)]*\)|\s+', '', t)


def fetch_kdca_health(out_dir, want=30, fetcher=None):
    """국가건강정보포털의 환자 안내 페이지를 2022-11-30 전에 뜬 사본으로 모은다."""
    f = fetcher or Fetcher(os.path.join(RAW_DIR, 'kdca-health'),
                           delays={'web.archive.org': 1.5, 'health.kdca.go.kr': 1.0})
    got, seen_titles, report, manifest = 0, set(), [], []
    for layout, cid, rows in _kdca_candidates(f):
        if got >= want:
            break
        parsed, snap = None, None
        for host, r in rows[:3]:          # 기준일 전 사본 가운데 쓸 수 있는 가장 새 것을 고른다
            arch = 'https://web.archive.org/web/%sid_/%s' % (r['timestamp'], r['original'])
            try:
                h = f.text(arch)
            except Exception as e:
                log('kdca skip capture', cid, e)
                continue
            parsed = _kdca_parse_new(h) if layout == 'new' else _kdca_parse_old(h)
            if parsed and parsed['sections']:
                snap = (host, r)
                break
        if not parsed or not snap:
            report.append((cid, 'no parsable capture'))
            continue
        key = _norm_title(parsed['title'])
        if key in seen_titles:
            report.append((cid, 'duplicate title ' + parsed['title']))
            continue
        lines, secs = _kdca_doc(parsed)
        if not passes(lines):
            report.append((cid, 'filtered (%d chars, %d sentences) %s' % (
                body_len(lines), count_sentences(lines), parsed['title'])))
            continue
        host, r = snap
        ts = r['timestamp']
        snap_day = '%s-%s-%s' % (ts[:4], ts[4:6], ts[6:8])
        page_day = parsed['date'] if parsed['date'] and parsed['date'] < CUTOFF else None
        label = '업데이트' if layout == 'new' else '수정일'
        basis = 'Wayback capture %s (before 2022-11-30); text taken from that capture' % snap_day
        if page_day:
            basis += ', which shows %s %s' % (label, page_day)
        doc_id = ('%s-%s' % ('cntnts' if layout == 'new' else 'idx', cid))
        meta = {
            'kind': 'patient-guide', 'label': '환자 안내문', 'source': 'kdca-health',
            'date': page_day or snap_day, 'date_basis': basis,
            'url': 'https://web.archive.org/web/%s/%s' % (ts, r['original']),
            'license': _kdca_license(f, cid if layout == 'new' else None),
        }
        write_doc(out_dir, doc_id, parsed['title'], lines, meta)
        manifest.append({'id': doc_id, 'title': parsed['title'], 'sections': secs, 'host': host,
                         'date': meta['date'], 'chars': body_len(lines), 'sentences': count_sentences(lines)})
        seen_titles.add(key)
        got += 1
        log('kdca %2d/%d %s %s [%s]' % (got, want, doc_id, parsed['title'], ', '.join(secs)))
    return got, report, manifest


def _kdca_license(f, cntnts_sn):
    """보관된 사본에는 라이선스 표시가 없다. 같은 id 의 현재 페이지에는 있어서 그것을 본다."""
    if cntnts_sn:
        try:
            h = f.text('https://health.kdca.go.kr/' + KDCA_NEW_PATH + '?cntnts_sn=' + cntnts_sn)
            m = re.search(r'alt="(공공누리 제\d유형[^"]*)"', h)
            if m:
                return m.group(1) + ' (shown on the live page for this cntnts_sn; the archived capture has no badge)'
        except Exception as e:
            log('kdca licence check failed', cntnts_sn, e)
        return KOGL4 + (' (shown on all current portal content pages; the live page for this cntnts_sn '
                        'is gone and the archived capture has no badge)')
    return KOGL4 + ' (shown on all current portal content pages; this 2017-2020 capture has no badge)'


# ---------------------------------------------------------------- seoul-report

SEOUL = 'https://opengov.seoul.go.kr'
# 인사와 급여, 지출 서식은 건너뛴다. 개인에 관한 사고와 민원 문서도 건너뛴다.
# 둘 다 줄글이 적고 개인정보가 들었을 가능성이 높다.
SEOUL_TITLE_SKIP = re.compile(
    r'지급|지출|여비|수당|초과근무|휴가|휴직|복무|채용|임용|계약|구매|입찰|정산|납부|인사|전보|승진|포상|징계|'
    r'출장|당직|근무상황|임금|급여|사유|수리|폐기|출동|사고|민원|신고|고발|소송|과태료|체납|분실|운영일지|'
    r'직무대행|대직|연가|병가|명예퇴직|퇴직|재해|부상|면직|위촉|해촉|임명|선임|표창|연봉')
FIRE_RE = re.compile(r'소방|119|긴급구조|방재센터')
HIDDEN_RE = re.compile(r"<div style='visibility:hidden; height:0; width:0;'[^>]*>(.*?)</div>", re.S)


def _seoul_list(f, start, end, page, listing='mayor'):
    """목록 한 쪽을 [(nid, title, date, dept)] 로 낸다. 새 문서가 앞에 온다.

    listing='mayor'    부시장이상 결재문서(/mayor/list). 부시장 이상이 결재한 보고서 서식의 보고다.
    listing='sanction' 모든 결재문서(/sanction/list) 가운데 제목에 보고가 든 것이다.
    """
    q = {'rangeDate': 'custom', 'startDate': start, 'endDate': end,
         'items_per_page': '50', 'page': str(page)}
    if listing == 'sanction':
        q.update({'searchField': 'title', 'searchKeyword': '보고'})
    h = f.text('%s/%s/list?%s' % (SEOUL, listing, urllib.parse.urlencode(q)))
    return re.findall(
        r'<a href="/sanction/(\d+)(?:\?from=mayor)?"><strong class="element-invisible">제목 : </strong>'
        r'<span>([^<]*)</span>.*?등록일 : </strong>\s*([0-9-]+)</span>.*?부서 : </strong>\s*([^<]*)</span>',
        h, re.S)


def _field(h, name):
    m = re.search(r'<th scope="row"[^>]*>%s</th>\s*<td[^>]*>(.*?)</td>' % re.escape(name), h, re.S)
    return html.unescape(re.sub(r'<[^>]+>', ' ', m.group(1))).strip() if m else ''


def _consume_title(t, pos, title):
    """t[pos:] 에서 빈칸을 무시하고 `title` 을 맞춰 보고, 그 바로 뒤의 위치를 낸다."""
    want = re.sub(r'\s+', '', title)
    i, j = pos, 0
    while i < len(t) and t[i].isspace():
        i += 1
    while i < len(t) and j < len(want):
        if t[i].isspace():
            i += 1
        elif t[i] == want[j]:
            i += 1
            j += 1
        else:
            return None
    return i if j == len(want) else None


def _loose(s):
    """글자 사이의 빈칸을 무시하고 `s` 를 찾는 정규식을 낸다."""
    return r'\s*'.join(re.escape(c) for c in re.sub(r'\s+', '', s))


# 보고서 본문의 첫 절 표시는 Ⅰ, □, "1 추진개요" 가운데 하나다. □ 는 몇몇 페이지에서 ？？ 로 바뀐다.
SECTION_RE = re.compile(r'\s(?:[%s]\.?\s|□|？？|[1-9]\s(?=[가-힣]{2}))' % 'ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ')


def _seoul_split(t, title):
    """태그를 걷어 펼친 결재문서 글을 (body, header_and_footer) 로 나눈다. 못 나누면 (None, reason) 을 낸다.

    보고서 서식은 "문서번호 … 결재일자 … [이름이 든 결재 칸] <title>
    [협조 / 협의결과 칸] [표지: 날짜, 부서] <title 다시> <도입문> Ⅰ …" 꼴이다.
    본문은 도입문에 첫 절 표시부터 "붙임" 이나 "끝." 까지를 더한 것이다.
    시행문 서식은 "… 제목 <title> <body> 끝. [발신, 이름, 주소]" 꼴이다.
    """
    t = t.replace('\xa0', ' ')
    if re.match(r'\s*문서번호\s', t):                 # 보고서 서식은 결재 칸이 맨 위에 있다
        if re.search(r'목\s*차|사전\s*검토항목', t[:3000]):
            return None, 'cover page / table of contents'
        m = re.search(_loose(title), t[:2500])
        if not m:
            return None, 'report header not found'
        head, rest = t[:m.end()], t[m.end():]
        sec = SECTION_RE.search(rest)
        if not sec:
            return None, 'no section markers'
        words = title.split()
        tail = ' '.join(words[-2:]) if len(words) >= 2 else title
        starts = [x.end() for x in re.finditer(_loose(tail), rest[:sec.start()])]
        if starts:
            head += ' ' + rest[:starts[-1]]           # 협조 칸과 표지도 머리에 넣는다
            rest = rest[starts[-1]:]
        else:
            head += ' ' + rest[:sec.start()]
            rest = rest[sec.start():]
        body = re.split(r'\s붙\s*임\s*[:：]?\s', rest)[0]
        body = re.split(r'\s끝\s*\.', body)[0]
        return body, head
    m = re.search(r'제목\s', t[:600])                   # 시행문 서식은 "끝." 뒤에 이름이 온다
    if not m:
        return None, 'unknown form'
    k = _consume_title(t, m.end(), title)
    k = k if k is not None else m.end() + len(title)
    end = re.search(r'\s끝\s*\.', t[k:])
    if not end:
        return None, 'no 끝. marker'
    body = t[k:k + end.start()]
    body = re.split(r'\s붙\s*임\s', body)[0]
    return body, t[:m.start()] + ' ' + t[k + end.end():]


ROMAN = 'ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ'


def _seoul_segment(body):
    """서울시 보고서가 쓰는 표시 자리에 줄바꿈을 다시 넣는다."""
    s = ' ' + body + ' '
    # 글 변환기는 □ 를 "？？" 로 쓰고, 작은 글머리 기호와 가운뎃점은 "？" 로 쓴다
    s = s.replace('？？', '□')
    s = re.sub(r'(?<=\s)？(?=\s)', '◦', s)
    s = s.replace('？', '·')
    s = re.sub(r'(?<=\s)·\s', '\n◦ ', s)                                   # 홀로 남은 가운뎃점은 변환된 글머리 기호다
    s = re.sub(r'\s+(?=[%s]\.?\s)' % ROMAN, '\n', s)                        # Ⅰ Ⅱ 절 앞에서 줄을 바꾼다
    s = re.sub(r'\s([1-9])\s([가-힣][가-힣 ]{1,15}?)(?=\s□)', r'\n\1 \2', s)   # "1 추진개요" 꼴의 절 앞에서 줄을 바꾼다
    s = re.sub(r'\s+(?=[□■○◦◯●ㅇ※▶▷](?![○◯□]))', '\n', s)          # "○○구" 같은 가림 글자는 건드리지 않는다
    s = re.sub(r'\s+(?=-\s)', '\n', s)

    def numbered(m):
        before = s[max(0, m.start() - 12):m.start() + 1]
        if re.search(r'\d{2,4}\s?\.\s?\d{0,2}\s?\.?\s?$', before):           # 2022. 6. 30. 같은 날짜는 둔다
            return m.group(0)
        back = s[max(0, m.start() - 30):m.start() + 1]
        if back.count('(') > back.count(')') and m.group(1).endswith(')'):   # "(순찰차 1)" 처럼 괄호를 닫는 숫자는 둔다
            return m.group(0)
        return '\n' + m.group(1)
    s = re.sub(r'\s((?:\d{1,2}|[가나다라마바사아자차카타파하])[.)]\s)(?=[가-힣A-Za-z「『"“‘\'(\[]|\d{2,4}년)', numbered, s)
    return [ln.strip() for ln in s.split('\n') if ln.strip()]


COMMON_SINGLE = set('및등각시약총중더수그이또전후내외별간안상하제차년월일명건개곳회약')


def _tableish(seg, min_tokens=4):
    """펼쳐진 표 칸인지 본다. 숫자나 홀로 선 음절이 많고 서술어가 없으면 표 칸이다."""
    toks = seg.split()
    if len(toks) < min_tokens:
        return False
    if SENT_END_RE.search(seg) or PRED_END_RE.search(seg):
        return False
    if re.match(r'^[^:：]{1,12}[:：]\s*\S', seg) and len(toks) <= 12:   # "일 시 : 2022. 6. 29." 꼴의 항목은 표가 아니다
        return False
    # 어디에도 서술어가 없는 긴 줄은 펼쳐진 표나 사진 설명이다
    if len(toks) >= 14 and not VERBAL_RE.search(seg) and not re.search(r'(니다|하고|하여|하며|하는|되어|되는|있는|있어|으로써|함\.|임\.|음\.|됨\.|함$|임$|음$|됨$)', seg):
        return True
    num = sum(1 for x in toks if re.search(r'\d', x))
    # "구 분", "비 고", "내 용" 처럼 홀로 선 음절은 띄어 쓴 표 머리다
    single = sum(1 for x in toks if re.fullmatch(r'[가-힣]', x) and x not in COMMON_SINGLE)
    n = float(len(toks))
    return num / n >= 0.4 or single / n >= 0.25 or (num + single) / n >= 0.5


def _seoul_lines(body, names):
    raw = _seoul_segment(body)
    is_section = lambda ln: ln[0] in ROMAN or re.fullmatch(r'[1-9] [가-힣][가-힣 ]{1,15}', ln)
    has_roman = any(is_section(ln) for ln in raw)
    lines, dropped, kept = [], 0, 0
    for ln in raw:
        parts = re.split(r'\s{2,}', ln)          # 공백이 두 개 이상 이어진 곳이 표 칸의 경계다
        keep = [parts[0]]
        for p in parts[1:]:
            if _tableish(p):
                break
            keep.append(p)
        dropped += sum(len(p) for p in parts[len(keep):])
        ln = ' '.join(keep)
        if _tableish(ln.lstrip('□○◦ㅇ-※ '), min_tokens=6):
            dropped += len(ln)
            continue
        ln = scrub(ln, names)
        if not ln or re.fullmatch(r'[\W\d_]*', ln):
            continue
        kept += len(ln)
        if is_section(ln):
            lines.append('## ' + ln)
        elif ln.startswith('□'):
            txt = ln.lstrip('□ ').strip()
            if len(txt) <= 30 and not SENT_END_RE.search(txt) and not re.search(r'[:：]', txt):
                lines.append(('### ' if has_roman else '## ') + txt)
            else:
                lines.append(txt)
        elif ln.startswith('※'):
            lines.append(ln)
        else:
            lines.append(md_line('p', ln))
    return _drop_empty_headings(_drop_empty_labels(lines)), dropped, kept


def _drop_empty_labels(lines):
    """값이 표 칸이라 비어 버린 "항목 :" 줄을 걷는다. 밑에 하위 항목이 이어지면 둔다."""
    out = []
    for i, ln in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ''
        if re.fullmatch(r'(?:- )?[^:：]{1,30}[:：]', ln) and not nxt.startswith('- '):
            continue
        out.append(ln)
    return out


def _drop_empty_headings(lines):
    """밑에 아무것도 없는 제목을 걷는다. 가려졌거나 표만 있던 절의 제목이다."""
    while True:
        out = []
        for i, ln in enumerate(lines):
            if ln.startswith('#'):
                level = len(ln) - len(ln.lstrip('#'))
                nxt = lines[i + 1] if i + 1 < len(lines) else None
                if not re.search(r'[가-힣A-Za-z]', ln) or nxt is None or (
                        nxt.startswith('#') and len(nxt) - len(nxt.lstrip('#')) <= level):
                    continue
            out.append(ln)
        if len(out) == len(lines):
            return out
        lines = out


def _seoul_doc(f, nid, title):
    h = f.text('%s/sanction/%s' % (SEOUL, nid))
    m = HIDDEN_RE.search(h)
    if not m:
        return None, 'no text rendering'
    flat = html.unescape(re.sub(r'<[^>]+>', ' ', m.group(1)))
    body, rest = _seoul_split(flat, title)
    if body is None:
        return None, rest
    # 본문 안의 연락처 칸을 걷는다. "작 성 자 ○○과장: 이름 ☎1234 담당: 이름 ☎5678" 꼴이다
    body = re.sub(r'작\s?성\s?자\s+(?:\S+\s*[:：]\s*[가-힣]{2,4}\s*☎\s*[\d\-]+\s*)+', ' ', body)
    writer = _field(h, '작성자(전화번호)')
    # 이름은 떼어 낸 결재 칸과 발신 꼬리말, 작성자 칸, 본문의 직급 낱말 옆에서 모은다.
    # 모은 이름은 모두 본문에서 지운다.
    names = find_names(rest, approval_block=True) | find_names(body)
    names |= {w for w in re.findall(r'[가-힣]{2,4}', writer) if w[0] in SURNAMES}
    lines, dropped, kept = _seoul_lines(body, names)
    if dropped > 0.35 * (dropped + kept):
        return None, 'mostly tables'
    leftover = find_names('\n'.join(lines))
    if leftover:
        return None, 'possible personal names left: %s' % len(leftover)
    lic = re.search(r'alt="(공공누리[^"]*)"', h)
    meta = {
        'produced': _field(h, '생산일자'),
        'approved': (re.search(r'결재일자\s*([\d.\s]+\.)', flat) or [None, None])[1],
        'dept': _field(h, '부서명'),
        'open': _field(h, '공개구분'),
        'license': lic.group(1) if lic else '',
        'names': names,
    }
    return (lines, meta), None


def _clean_title(title):
    """제목에 남은 변환기 흔적을 되돌린다. 따옴표나 가운뎃점 자리에 든 '？' 를 고치고 '- 부제 -' 꼴의 감싸기를 푼다."""
    t = re.sub(r'(?<=[가-힣A-Za-z0-9])？(?=[가-힣A-Za-z0-9])', '·', title)
    t = t.replace('？', ' ')
    if t.lstrip().startswith('-'):
        t = re.sub(r'^\s*-\s*|\s+-\s*', ' ', t)
    return ' '.join(t.split())


def _months(first='2020-01', last='2022-11'):
    y, m = map(int, first.split('-'))
    ly, lm = map(int, last.split('-'))
    while (y, m) <= (ly, lm):
        nd = [31, 29 if y % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
        end = '%04d-%02d-%02d' % (y, m, nd)
        yield '%04d-%02d-01' % (y, m), min(end, '2022-11-29')
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch_seoul_report(out_dir, want=30, fetcher=None, per_month_scan=12, listing='mayor'):
    """서울 정보소통광장의 보고서 서식 결재문서를 2020-01..2022-11 의 여러 달에 고루 나눠 모은다.

    기본 목록은 부시장이상 결재문서다. 결재 칸과 도입문, Ⅰ/□/○ 절을 갖춘 보고서 서식의 보고가 든다.
    일반 결재문서 목록을 제목에 보고가 든 것으로 거르면 대개 소방서의 정형 공문이 나온다.
    이 목록에서는 열두 편에 한 편꼴로만 거르기를 통과한다. 이 목록을 쓰려면 listing='sanction' 을 넘긴다.

    달은 돌아가며 하나씩 본다. 한 달 안에서는 새 문서부터 목록을 차례로 훑어 거르기를 처음 통과한 문서를 받는다.
    부서마다 한 편, 상위 조직마다 두 편까지 받고, 소방 쪽 문서는 표본의 5분의 1까지만 받는다.
    """
    f = fetcher or Fetcher(os.path.join(RAW_DIR, 'seoul-report'), delays={'opengov.seoul.go.kr': 1.0})
    months = list(_months())
    months = months[::2] + months[1::2]      # 첫 바퀴에서 이미 기간 전체를 훑는다
    cursor = {mo: [1, 0, []] for mo in months}       # 쪽 번호, 쪽 안의 위치, 그 쪽의 항목이다
    seen_dept, top_count, fire, got, report, manifest = set(), {}, 0, 0, [], []
    fire_cap = max(1, want // 5)
    for rnd in range(4):
        for mo in months:
            if got >= want:
                return got, report, manifest
            cur = cursor[mo]
            scanned = 0
            while scanned < per_month_scan:
                if cur[1] >= len(cur[2]):
                    if cur[0] > 4:
                        break
                    cur[2] = _seoul_list(f, mo[0], mo[1], cur[0], listing)
                    cur[0], cur[1] = cur[0] + 1, 0
                    if not cur[2]:
                        cur[0] = 99
                        break
                nid, title, day, dept = cur[2][cur[1]]
                cur[1] += 1
                title, dept = html.unescape(title).strip(), dept.strip()
                top = dept.split()[0] if dept else ''
                is_fire = bool(FIRE_RE.search(dept))
                if (SEOUL_TITLE_SKIP.search(title) or dept in seen_dept or top_count.get(top, 0) >= 2
                        or (is_fire and fire >= fire_cap) or day >= CUTOFF):
                    continue
                scanned += 1
                try:
                    res, why = _seoul_doc(f, nid, title)
                except Exception as e:
                    res, why = None, 'error %s' % e
                if res is None:
                    report.append((nid, why))
                    continue
                lines, meta = res
                if not passes(lines):
                    report.append((nid, 'filtered (%d chars, %d sentences)' % (body_len(lines), count_sentences(lines))))
                    continue
                produced = meta['produced'] or day
                if produced >= CUTOFF:
                    continue
                approved = meta['approved']
                basis = '생산일자 %s in the document-information table of the page' % produced
                if approved:
                    basis += ' (결재일자 %s in the document header)' % ' '.join(approved.split())
                write_doc(out_dir, nid, _clean_title(title), lines, {
                    'kind': 'biz-report', 'label': '사업 계획·실적 보고서', 'source': 'seoul-report',
                    'date': produced, 'date_basis': basis,
                    'url': '%s/sanction/%s' % (SEOUL, nid),
                    'license': meta['license'],
                })
                manifest.append({'id': nid, 'title': title, 'dept': meta['dept'], 'disclosure': meta['open'],
                                 'date': produced, 'chars': body_len(lines),
                                 'sentences': count_sentences(lines), 'names_removed': len(meta['names'])})
                seen_dept.add(dept)
                top_count[top] = top_count.get(top, 0) + 1
                fire += is_fire
                got += 1
                log('seoul %2d/%d %s %s %s | %s' % (got, want, nid, produced, dept, title))
                break
    return got, report, manifest


# ---------------------------------------------------------------- main

def main():
    base = os.path.expanduser('~/.cache/docs-suit-eval/human')
    which = sys.argv[1:] or ['kdca-health', 'seoul-report']
    for src in which:
        out = os.path.join(base, src)
        fn = fetch_kdca_health if src == 'kdca-health' else fetch_seoul_report
        got, report, manifest = fn(out, want=30)
        log('== %s: %d documents in %s' % (src, got, out))
        # 실행 보고는 원본 캐시 옆에 두어 문서 폴더에는 문서만 남긴다
        with open(os.path.join(RAW_DIR, src, '_report.json'), 'w', encoding='utf-8') as fp:
            json.dump({'documents': manifest, 'skipped': report}, fp, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
