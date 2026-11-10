# 기여하는 법

docs-suit 는 새 문서 종류와 테마 조합, 문장 규칙처럼 테마를 넓히는 PR 을 받습니다. PR 은 자동 판정이 먼저 보고, 검사를 다 통과한 PR 만 관리자가 검토해 머지합니다. 머지된 기여에는 캐릭터의 3차나 4차 전직을 여는 승급 키를 드립니다.

작업 규칙은 [AGENTS.md](AGENTS.md) 에, 기능마다 쓰는 법은 [GUIDE.md](GUIDE.md) 에 있습니다. 보안 취약점은 PR 이나 이슈 대신 [SECURITY.md](SECURITY.md) 의 비공개 신고로 보내 주세요.

## 이런 기여를 받습니다

| 기여 | 더하거나 고칠 파일 | 함께 할 일 |
|---|---|---|
| 테마 조합 | `themes/ko/presets/<이름>.yaml` | `python3 suit.py preset export <이름> --by <GitHub 아이디> --desc "쓰임새 한 줄"` 로 지금 내 설정을 뽑아 넣습니다. `by` 는 PR 을 올린 계정과 같아야 하고, 소개는 어떤 글에 쓰는 조합인지 말해야 합니다. 기본 어법이 평어체인 조합은 상사와 다른 팀처럼 합쇼체로 받는 독자의 어법을 `audiences` 에 합쇼체로 적어야 selftest 가 통과합니다 |
| 새 문서 종류 | `themes/ko/kinds/<종류>.md` | `defaults.yaml` 의 `kinds` 에 종류를 더하고, 틀이 꼭 쓰라고 한 절은 `must` 에 낱말로 적습니다. 어느 클래스의 주력 문서에 넣어야 selftest 가 통과하고, `tests/agent/cases.py` 에도 케이스를 하나 더합니다 |
| 새 값 | `themes/ko/<축>/<값>.md` | `axes.yaml` 에 한 줄을 더합니다. 끝의 `## 보기` 는 다른 값과 견줄 수 있게 정류장 대기 시간 조사 예문으로 씁니다 |
| 써 보기 템플릿 | `themes/ko/trials/<이름>.md` | 웹 판 써 보기에 뜨는 예시 요청입니다. 정류장 대기 시간 조사에서 지어낸 사실로만 씁니다 |
| 도트 부품 | `themes/ko/sprites/<부위>/<값>.txt` | `look.yaml` 에 한 줄을 더합니다. 다른 그림을 옮기지 않고 새로 그립니다 |
| 문장 규칙 | `themes/ko/tells.yaml` | `error` 층에는 틀린 꼴이 정해진 문형만 넣고, 사람 글에도 흔한 표현은 `suggest` 층에 둡니다 |
| 클래스 | `themes/ko/classes/<id>.yaml` | 있는 클래스의 주력 문서 목록에 종류를 더하는 것은 자동 판정이 봅니다. 새 클래스는 성장과 화면까지 바꿔서 관리자가 직접 봅니다 |
| 문서 고침 | `README.md`, `GUIDE.md`, `ROADMAP.md` | 오탈자와 틀린 설명을 고칩니다. 크게 고칠 일은 이슈로 먼저 의논합니다 |

`defaults.yaml` 과 `axes.yaml`, `look.yaml`, `tells.yaml` 은 여러 기여가 함께 쓰는 파일이라 줄을 더하기만 합니다. 기존 항목을 고치거나 지울 일이 있으면 이슈로 먼저 의논해 주세요.

엔진 `suit.py` 와 웹 화면 `docs/` 의 코드를 고친 PR 도 받습니다. 다만 자동 검사로 옳고 그름을 가리지 못해서 관리자가 직접 보고, 시간이 더 걸립니다. 조립 함수를 고치면 `docs/core.js` 도 같은 PR 에서 고쳐 두 쪽의 출력을 맞춥니다.

규칙과 예문에는 회사 이름과 내부 정보, 실제 사람의 이름과 연락처를 넣지 않습니다. 공개 저장소라서 한 번 머지되면 기록에서 지우기 어렵기 때문입니다. 사람이 나와야 하는 예문은 "김사원", "박대리" 처럼 직급으로 씁니다.

## PR 을 올리기 전에 세 가지 검사를 돌립니다

```sh
python3 suit.py bundle      # 웹 묶음 docs/themes.json 과 화면의 주소 해시를 다시 만든다
python3 suit.py selftest    # 데이터 정합과 값 정하는 순서, 보기 예문
node tests/parity.js        # 웹과 엔진이 같은 지침을 내는지
```

`bundle` 이 바꾼 `docs/themes.json` 과 `docs/*.html` 도 PR 에 함께 넣습니다. 이 파일이 테마와 다르면 selftest 가 실패합니다. PR 설명에는 무엇을 왜 더했는지 한두 줄 적어 주세요.

## PR 은 자동 판정이 먼저 봅니다

판정은 main 의 코드로 돌고, PR 의 파일은 실행하지 않고 데이터로만 읽습니다. 결과는 한국어와 영어로 PR 댓글 하나에 달리고, 다시 push 하면 같은 댓글이 고쳐집니다.

| 판정 | 이럴 때 | 처리 |
|---|---|---|
| 검토 대기 | 검사를 모두 통과했습니다 | 관리자에게 리뷰를 요청합니다 |
| 고칠 곳이 있음 | 검사가 틀렸거나, 받는 자리 밖의 파일과 규칙에 맞지 않는 이름, 링크, 지침을 뒤집는 듯한 낱말처럼 닫을 만큼 명백하지 않은 문제가 있습니다. 파일을 지우거나 옮긴 것, 바이너리 파일, 너무 큰 파일, PR 설명이 비었거나 설명에 그런 낱말이 걸린 것도 여기 듭니다 | 닫지 않고 차단 횟수에도 넣지 않습니다. 고쳐서 push 하면 다시 판정합니다 |
| 닫음 | 아래 세 가지 가운데 하나입니다 | 바로 닫고 차단 횟수에 넣습니다 |

자동으로 닫는 경우는 세 가지뿐입니다.
- 눈에 보이지 않는 숨은 문자가 들어 있습니다. 읽는 사람과 AI 가 다른 글을 보게 만들 수 있어서입니다. 메모장 같은 편집기가 파일 맨 앞에 붙이는 BOM 한 개는 고칠 곳으로만 알립니다.
- 심볼릭 링크나 gitlink 처럼 일반 파일이 아닌 특수 파일이 있습니다.
- 보호한 자리의 코드를 고쳤습니다. 워크플로가 든 `.github/workflows/` 와 `.github/actions/`, 관리 도구가 든 `tools/`, `.gitattributes` 와 `.gitmodules`, 엔진에서 승급 키를 확인하는 코드, 동작 테스트 케이스 파일 `tests/agent/cases.py` 에 넣은 코드입니다. 이슈 양식처럼 `.github/` 아래의 다른 파일은 고칠 곳으로만 알립니다.

낱말과 링크 검사는 정상 글도 걸 수 있어서 닫지 않고 고칠 곳으로만 알립니다. 판정이 잘못 걸었거나 잘못 닫았다고 보면 PR 번호를 적어 이슈를 열어 주세요.

## 90일 안에 세 번 닫히면 차단합니다

90일 안에 자동으로 닫힌 PR 이 세 건이 되면 그 계정을 이 저장소에서 차단합니다. "고칠 곳이 있음" 으로 남은 PR 은 세지 않고, 닫힐 때마다 판정 댓글에 지금까지 몇 건인지 적습니다.

## 머지되면 승급 키를 드립니다

3차와 4차 전직은 이 저장소에 기여해야 열립니다.
- 3차 키는 종류를 가리지 않고 기여 한 건이 머지되면 드립니다. 오타 하나를 고친 PR 도 됩니다.
- 4차 키는 내가 만든 테마 조합이 머지되면 드립니다. 4차 키는 3차 조건도 함께 채웁니다.

테마 조합은 축 값이 알려진 값인지, 소개가 쓰임새를 말하는지, 회사와 사람 이름이 없는지 보고 머지합니다.

키는 관리자가 머지한 뒤 손으로 만들어 PR 댓글로 드려서, 받기까지 며칠 걸릴 수 있습니다. 받은 키는 `python3 suit.py promote <키>` 로 넣습니다. 레벨이 모자라도 미리 넣어 둘 수 있고, 3차는 Lv.30, 4차는 Lv.50 이 되면 전직합니다. 키에는 GitHub 아이디와 차수, 기여 링크가 들어 있어서 캐릭터 카드에 기여한 아이디가 붙습니다.

## In English

docs-suit accepts pull requests that add document kinds, theme presets, values, writing rules, try-it templates and pixel-art parts under `themes/ko/`. Run `python3 suit.py bundle`, `python3 suit.py selftest` and `node tests/parity.js` before opening a pull request.

An automated check reviews every pull request and comments in Korean and English. It closes a pull request only for hidden characters, special files such as symlinks or gitlinks, or changes to protected code: `.github/workflows/`, `.github/actions/`, `tools/`, `.gitattributes`, `.gitmodules`, the promotion-key check in the engine, and code in `tests/agent/cases.py`. A single byte order mark at the start of a file is not treated as a hidden character. Everything else that needs work is left open with a comment and is not counted. Accounts with three automatically closed pull requests within 90 days are blocked.

Merged contributions receive a promotion key for the in-app character. The maintainer issues keys by hand as a pull request comment, so it may take a few days. Report security issues privately as described in [SECURITY.md](SECURITY.md).
