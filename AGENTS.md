# 이 저장소에서 일하는 법

docs-suit 를 고치는 사람과 AI 에이전트가 읽는 작업 규칙이다. 쓰는 법은 `README.md` 와 기능마다 자세히 적은 `GUIDE.md`, 앞으로 할 일은 `ROADMAP.md` 에 있다. 외부 기여자에게 보이는 안내는 `CONTRIBUTING.md`, 보안 신고는 `SECURITY.md`, 함께 넣은 파일의 라이선스 원문은 `THIRD_PARTY_NOTICES.md` 에 있다. 판정 규칙을 바꾸면 `GUIDE.md` 와 `CONTRIBUTING.md` 의 판정 설명도 같은 커밋에서 고친다.

## 구조

| 자리 | 내용 |
|---|---|
| `suit.py` | 엔진 한 파일. bootstrap, compose, check, review, card, look, preset, promote, status, widget, serve, export, bundle, selftest. 사람이 치는 줄임 명령 init, remove, update, link 도 있고, 맨 위 도움말의 묶음과 한 줄 설명은 `CLI_GROUPS` 와 `CLI_HELP` 에 둔다. 실행 권한을 두어 `link` 가 건 `docs-suit` 링크로 바로 불린다 |
| `themes/ko/` | 한국어 테마 팩. 축과 값은 `axes.yaml`, 독자와 문서 종류는 `defaults.yaml`, 클래스는 `classes/`, 페르소나 질문은 `persona.yaml` |
| `themes/ko/<축>/<값>.md` | 값마다 규칙 문서 한 장. 끝의 `## 보기` 절은 웹 카드에만 쓰고 지침에는 싣지 않는다 |
| `themes/ko/kinds/<종류>.md` | 문서 종류의 틀. 틀이 꼭 쓰라고 한 절은 `defaults.yaml` 의 `must` 에 낱말로 적는다 |
| `themes/ko/base.md` | 공통 바닥. 사실, 쓰기 전에, 문장, 상투 표현의 네 묶음이고 모든 지침의 맨 앞에 실린다 |
| `themes/ko/tells.yaml` | 본문 검사의 문장 규칙 패턴. `error` 는 ✗ 로 고쳐 쓰게 하고, `suggest` 는 △ 로 보이기만 한다 |
| `themes/ko/revise.md`, `review.md` | 다듬기 절과 검토 지침의 머리. `compose --revise` 와 `review` 가 싣는다 |
| `themes/ko/learn.md` | 예전 글에서 "내 문체" 문서를 쓰는 지침. `learn --guide` 가 낸다. 쓴 문서는 저장소 밖 `~/.config/docs-suit/voices/<슬롯>.md` 에 남는다 |
| `themes/ko/growth.yaml` | 캐릭터 성장 규칙. 문서 한 건이 받는 경험치와 레벨, 전직 문턱 |
| `themes/ko/look.yaml` | 기본 캐릭터와 머리 모양, 클래스마다 전직할 때 여는 꾸미기(`rewards`), 부품과 옷 색 목록 |
| `themes/ko/presets/<이름>.yaml` | 기여받은 테마 조합. 축 기본값과 독자별 값, 소개, 만든 사람 |
| `themes/ko/trials/<이름>.md` | 웹 판 써 보기 탭의 템플릿. 첫 줄은 이름, 빈 줄까지는 클래스와 문서 종류, 독자, 그 아래는 AI 에 보낼 예시 요청이다. 예시는 정류장 대기 시간 조사에서 지어낸 사실로만 쓰고, 클래스마다 하나 이상 둔다 |
| `themes/ko/sprites/<부위>/<값>.txt` | 도트 그림 부품. 기본 몸(`base`) 위에 옷(`top`), 머리(`hair`), 소품(`prop`) 순으로 겹친다. 모두 같은 크기다 |
| `tools/issue-key.py` | 관리자가 승급 키를 만드는 도구. 개인 키는 저장소 밖 `~/.config/docs-suit-admin/` 에 둔다 |
| `tools/contrib-eval.py` | 외부 기여 PR 을 판정하고 처리한다. `.github/workflows/contrib.yml` 이 main 의 코드로 부르고, PR 의 파일은 실행하지 않고 데이터로만 읽는다 |
| `tools/readme-art.py` | README 의 캐릭터 그림 `docs/readme/characters.svg` 를 엔진의 그림 함수로 다시 그린다. 부품이나 `look.yaml` 의 보상을 바꾸면 돌린다 |
| `docs/` | 웹 화면. 대시보드(`index.html`, `dashboard.js`)가 캐릭터(`character.html`, `character.js`)와 캐릭터 설정(`create.html`, `create.js`), 테마 설정(`theme.html`, `app.js`) 세 탭을 품는다. 웹 판에서는 `index.html` 이 대시보드 대신 써 보기(`try.html`, `try.js`)로 바로 넘기고, 써 보기는 옛 게임 풍 모양(`retro.css`)과 머리 맵(`map.js`), 제목 글꼴(`fonts/`)을 더 얹는다. 화면은 모두 `style.css` 를 함께 쓴다. `core.js` 가 조립과 캐릭터 그림, 슬롯 파일 쓰기를 하고 `themes.json` 은 `suit.py bundle` 이 만든다. `local.js` 는 `suit.py serve` 로 띄웠을 때만 켜져 바로 적용하게 한다 |
| `tests/parity.js` | 웹과 엔진의 조립 결과를 견준다 |
| `tests/agent/` | 실제 에이전트에 요청을 넣는 동작 테스트. 케이스는 `cases.py`, 에이전트별 결과는 `results/`, 문체 배우기 흐름의 지어낸 샘플은 `samples/` |
| `tests/eval/` | 글 평가 실행기. docs-suit 를 켜고 쓴 글과 끄고 쓴 글, 사람 글과 연구 데이터를 엔진의 `measure` 로 재서 견준다. 글은 저장소 밖 `~/.cache/docs-suit-eval/` 에 두고, 잰 수치로 만든 보고서만 `results/` 에 남긴다 |

## 고친 뒤에는 세 가지를 돌린다

```sh
python3 suit.py bundle      # 테마나 웹 화면을 고쳤으면 웹 묶음과 화면의 주소 해시를 다시 만든다
python3 suit.py selftest    # 데이터 정합과 값 정하는 순서, bootstrap, export 계약
node tests/parity.js        # 웹과 엔진이 같은 지침을 내는지
```

판정 스크립트나 기여를 받는 자리를 바꿨으면 `python3 tools/contrib-eval.py selftest` 도 돌린다. 지어낸 PR 로 판정이 맞는지 재고, 지금 저장소의 테마와 문서가 공격 패턴에 걸리지 않는지도 잰다. 테마나 문서에 새 글을 더했는데 이 검사가 실패하면 패턴이 너무 넓은 것이라 패턴을 좁힌다.

CI 가 같은 검사를 돌린다. `docs/themes.json` 이 테마와 다르거나, 웹 화면이 부르는 CSS 와 JS 의 `?v=` 해시가 파일과 다르면 selftest 가 실패한다. 해시는 GitHub Pages 의 10분 캐시 때문에 새 HTML 과 옛 CSS 가 섞이지 않게 붙인다.

## 요청을 고르는 단계는 동작 테스트로 본다

selftest 와 parity 는 문서 종류와 독자를 넘겨받은 뒤의 조립만 잰다. 요청 문장을 보고 종류와 독자를 고르는 일은 SKILL.md 를 읽은 에이전트가 하므로, 실제 에이전트에 요청을 넣어 확인한다.

```sh
python3 tests/agent/run.py --agent claude             # 케이스와 여러 턴 흐름 전체
python3 tests/agent/run.py --agent antigravity --only sns  # 몇 건만
python3 tests/agent/run.py --agent claude --record    # 결과를 tests/agent/results/ 에 남긴다
python3 tests/agent/run.py --agent claude --regrade <기록 폴더>  # 에이전트를 부르지 않고 다시 채점
```

채점은 세 가지를 본다.
- 고르기: 에이전트가 넘긴 compose 인자로 조립한 값이 기대와 같은지 본다.
- 본문 검사: 쓴 본문이 어법, 문체, 분량, 강조, 출력 형식, 틀의 필수 절, 문장 규칙을 지켰는지 어림 기준으로 잰다. 표에는 ✗ 층만 남기고 △ 제안은 세지 않는다. 틀이 정한 문서는 골격이 문체보다 앞서서 문체를 재지 않는다. 틀림이 나오면 본문을 직접 읽어 확인한다.
- 여러 턴 흐름: 세션을 이어 가며 대화로 bootstrap 하고, 말투를 바꿔 저장하고, 이 폴더에서만 저장한 뒤 프로필과 폴더 파일에 남은 값을 본다.

자료가 모자라 에이전트가 질문만 하고 멈추면, 실제 사용자처럼 모르는 곳은 비워 두고 지금 쓰라고 한 번 더 재촉해 본문을 받는다. 고르기 채점은 첫 턴 기록만 쓴다.

SKILL.md 문구나 문서 종류, 독자를 바꿨으면 돌리고 `--record` 로 결과를 갱신한다. 새 문서 종류를 더하면 `cases.py` 에도 케이스를 하나 더한다. 에이전트 로그인이 필요하고 돌릴 때마다 사용료가 들어서 CI 에는 넣지 않는다.

실행기는 홈 폴더의 스킬과 프로필을 건드리지 않는다. 케이스마다 임시 폴더에 프로젝트 단위 스킬과 시험 프로필을 두고, `DOCS_SUIT_LOG` 로 suit.py 호출 인자를 모아 채점한다. Claude Code 는 사용자 설정과 개인 스킬, MCP 를 끄고 돌려서 처음 설치한 사람과 조건을 맞춘다. 평소에는 suit.py 호출과 읽기만 허락하고, pptx 나 docx 를 만들어 달라는 케이스에서만 파일 쓰기와 `python3`, `pandoc` 실행을 더 허락한다.

Antigravity CLI 는 한 번 실행 모드에서 확인 창을 띄우지 못해 명령을 거절하고, 작업 폴더 단위 설정이 없다. 그래서 `~/.gemini/antigravity-cli/settings.json` 의 `permissions.allow` 에 `command(python3 <suit.py 절대 경로>)` 를 더한 뒤 돌린다. Codex CLI 는 exec 모드가 샌드박스 안에서 확인 없이 돌아서 따로 설정하지 않는다. 다만 이 샌드박스는 포트 열기를 막아 화면 케이스에서 서버가 뜨지 않으므로, 화면 케이스는 알맞은 화면을 `--detach` 로 불렀는지만 잰다.

무료 요금제로 돌리면 사용 한도에 걸릴 수 있다. 한도나 연결 실패로 답 없이 끝난 건은 틀림이 아니라 재지 못함으로 표에 남고, 맞은 비율에서도 뺀다. 결과 머리의 SKILL.md 지문으로 어느 판의 SKILL.md 로 돌렸는지 가린다.

## 글이 나아졌는지는 글 평가로 본다

동작 테스트는 규칙을 지켰는지 재고, 글 평가는 그 규칙이 글을 사람 글 쪽으로 옮겼는지 잰다. 같은 요청을 docs-suit 를 켜고, 끄고 쓰게 해서 사람 글과 같은 수치로 견준다.

```sh
python3 tests/eval/run.py gen               # 케이스 묶음을 켜고 끄고 쓴다. 사용료가 든다
python3 tests/eval/run.py fetch katfish     # 연구 데이터를 받아 사람 글과 LLM 글로 나눈다
python3 tests/eval/run.py fetch korea-press # 정책브리핑의 2022년 보도자료를 받는다. 공공누리 제1유형이다
python3 tests/eval/run.py pairs korea-press # 사람 글의 사실로 같은 문서를 써 달라는 요청을 만든다. 사용료가 든다
python3 tests/eval/run.py gen --set pairs   # 짝 요청을 켜고 끄고 쓴다
python3 tests/eval/run.py measure           # 모은 글을 모두 잰다
python3 tests/eval/run.py report --record   # 보고서를 tests/eval/results/ 에 남긴다
```

- 사람 글은 2022년 11월 전에 쓴 공개 라이선스 글과 연구 데이터만 쓰고, 원문은 저장소에 넣지 않는다. 라이선스 파일이 없는 KatFish 는 로컬 검증에만 쓴다.
- 에이전트를 돌리는 작업 폴더는 시스템 임시 폴더에 둔다. 홈 폴더 아래에서 돌리면 Claude Code 가 상위 폴더의 `~/.claude/CLAUDE.md` 와 개인 스킬을 지침으로 실어, 끈 글까지 돌리는 사람의 문체 지침을 받고 쓴다. 실행기는 작업 폴더가 홈 폴더 아래에 생기면 멈춘다.
- 사용료는 `~/.cache/docs-suit-eval/spent.jsonl` 에 쌓이고, 합이 `--cap` 에 닿으면 새 글을 쓰지 않는다. 동작 테스트처럼 로그인과 사용료가 필요해 CI 에 넣지 않는다.
- 수치 하나로 글을 판정하지 않고, 사람처럼 보이려고 글을 나쁘게 만드는 쪽으로 규칙을 고치지 않는다. 띄어쓰기는 LLM 이 사람보다 잘 지키지만 틀리게 쓰라고 하지 않는다.
- 평가 수치는 성장 경험치에 넣지 않는다. 검증하지 않은 수치는 `check` 에 싣지 않는다.

## 지킬 것

- `suit.py` 의 `resolve` 나 `compose`, `look_of`, `look_grid`, `dump_yaml` 을 고치면 `docs/core.js` 도 같은 커밋에서 고친다. 두 쪽의 출력은 글자 하나까지 같아야 하고, parity 가 조립한 지침과 캐릭터 그림, 슬롯 파일을 잰다.
- 표준 라이브러리만 쓰고 파이썬 3.9 문법 안에서 쓴다. 웹은 빌드 도구 없이 정적 파일로 둔다. 글 평가 실행기 `tests/eval` 만 예외로 형태소 분석기 Kiwi 를 선택 의존성으로 쓰고, 없으면 품사 수치만 건너뛴다. 엔진과 CI 가 도는 코드는 표준 라이브러리만 쓴다.
- 규칙 문서는 평어체로 쓴다. 한 문장에 한 맥락을 담고, 대시로 문장을 잇지 않고, 개수는 "세 가지" 처럼 단위 명사로 센다.
- 새 값의 `## 보기` 는 다른 값과 같은 예문인 정류장 대기 시간 조사로 쓴다. 같은 예문이어야 카드끼리 견줄 수 있다.
- `tells.yaml` 의 `error` 층에는 정해진 문형만 넣는다. 사람 글에도 흔한 표현은 `suggest` 에 두고 `min` 으로 밀도를 잰다. selftest 는 모든 값의 보기를 깨끗한 예문으로 보고 `error` 패턴이 걸리면 실패한다.
- 규칙과 예문에 특정 회사의 이름과 내부 정보, 실제 사람의 이름과 연락처를 넣지 않는다. 공개 저장소다.
- 도트 그림과 칭호는 새로 만든다. 다른 게임에서는 전직 단계 같은 구조와 느낌만 빌리고, 그림과 이름을 옮겨 오지 않는다. 부품을 더하면 `look.yaml` 에도 한 줄을 더하고, selftest 가 둘이 맞는지 잰다. 공개 저장소라 게임 이름도 적지 않는다.
- 승급 키의 개인 키는 저장소에 넣지 않는다. 키를 바꾸면 `PROMOTE_KEYS` 에 새 kid 를 더하고 지난 kid 는 남겨 둔다. 지난 키를 받은 사람의 전직이 풀리지 않게 하기 위해서다.
- 외부 PR 은 자동 판정이 먼저 본다. 숨은 문자와 특수 파일, 보호 경로의 코드처럼 명백히 해로운 변경만 닫고, 그 밖의 문제는 고칠 곳으로 댓글만 달고, 다 통과한 PR 만 관리자에게 리뷰를 요청한다. 90일 안에 자동으로 닫힌 PR 이 세 건이 되면 작성자를 차단한다. 판정 규칙을 넓힐 때는 selftest 에 시나리오를 먼저 더한다. 잘못 닫히면 정직한 기여자가 차단 횟수를 떠안기 때문이다.
- 차단 토큰 `BLOCK_TOKEN` 은 `moderation` 환경에만 두고, 이 환경은 main 브랜치에서만 쓴다. 판정 job 에는 비밀값을 주지 않는다. PR 을 읽는 job 이 비밀값을 가지면 PR 내용으로 토큰을 빼낼 길이 생기기 때문이다.
- 테마 조합 PR 은 축 값이 알려진 값인지, 소개가 쓰임새를 말하는지, 회사와 사람 이름이 없는지 보고 머지한다. 머지하면 `tools/issue-key.py issue --tier 4` 로 키를 만들어 PR 댓글로 준다.
- 성장 기록에는 본문과 파일 경로를 남기지 않는다. 같은 문서인지는 경로의 해시로만 가린다.
- 문체 배우기는 샘플 원문을 남기지 않는다. `learn` 은 재기만 하고, "내 문체" 문서는 사용자가 승인한 판만 `voice set` 으로 남긴다.
- 작업 폴더에 깐 스킬은 이 저장소의 `suit.py` 를 그대로 부른다. 기본 작업 트리에서 고치는 중에 `suit.py` 가 깨지면 사용자의 실제 세션과 상태 줄도 함께 깨지므로, 큰 작업은 `git worktree` 로 따로 연 작업 트리에서 하고 끝난 뒤 main 에 넣는다.
- 프로필은 `~/.config/docs-suit/` 에 두고 저장소에 넣지 않는다. export 를 시험할 때는 `--dest` 나 임시 작업 폴더에 쓰고, 사람이 쓰는 작업 폴더에 깔거나 거두는 일은 확인받은 뒤에 한다.
- 스킬은 글을 쓰는 작업 폴더에만 깔고 홈 폴더에는 깔지 않는다. 홈 폴더의 스킬은 모든 프로젝트에서 불려 다른 프로젝트의 문체 체계를 덮기 때문이다. `OLD_HOME_SKILLS` 는 예전 판이 깐 사본을 `export --remove --global` 로 거둘 때만 쓴다.
