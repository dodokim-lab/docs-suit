# 보안 정책

docs-suit 의 보안 취약점은 공개 이슈 대신 GitHub 의 비공개 취약점 신고로 받습니다. 고치기 전에 내용이 공개되면 쓰는 사람이 그 틈에 그대로 드러나기 때문입니다.

## 비공개로 신고해 주세요

저장소의 Security 탭에서 "Report a vulnerability" 를 눌러 신고합니다. 바로 가는 주소는 https://github.com/dodokim-lab/docs-suit/security/advisories/new 입니다. 신고 내용은 관리자와 신고한 사람만 봅니다.

아래 내용을 적어 주시면 빨리 확인할 수 있습니다.
- 영향을 받는 자리와, 그 틈으로 무엇을 할 수 있게 되는지
- 재현 단계와 실행한 명령, 쓴 입력 파일
- 확인한 커밋과 OS, 파이썬 판

## 최신 main 만 고칩니다

고친 내용은 main 에 넣고, 지난 커밋이나 태그를 단 판에는 따로 고친 판을 내지 않습니다. 새 판을 받는 법은 GUIDE.md 의 "새 판으로 올리려면" 절에 있습니다.

## 이런 것을 받습니다

받는 것.
- 엔진 `suit.py` 가 문서 파일과 폴더 파일을 읽고, 프로필과 성장 기록을 쓰는 자리
- `suit.py serve` 로 띄우는 로컬 화면 서버
- 웹 판 https://dodokim-lab.github.io/docs-suit/ 와 `docs/` 의 화면
- 테마나 폴더 파일을 거쳐 에이전트에게 쓰는 사람이 원하지 않는 일을 시키는 길
- 외부 PR 을 판정하는 워크플로와 `tools/contrib-eval.py`
- 승급 키의 서명 확인

받지 않는 것.
- 내 컴퓨터의 엔진이나 성장 기록을 고쳐 전직하는 것. 모든 것이 내 컴퓨터에 있는 혼자 하는 게임이라 막지 않습니다.
- 에이전트가 조립한 지침을 따르지 않거나 틀린 글을 쓰는 것. 이런 일은 버그 신고 이슈로 보내 주세요.
- ChatGPT 와 Claude, Gemini 같은 바깥 서비스 자체의 문제

## 언제 답을 받나요

혼자 관리하는 저장소라 아래 기한은 어림입니다.
- 받았다는 답은 7일 안에 드립니다.
- 확인한 결과와 고칠 계획은 30일 안에 알려 드립니다.
- 고친 판을 main 에 넣은 뒤 보안 권고를 공개하고, 신고한 분이 원하면 이름을 함께 올립니다.

## In English

Please do not open public issues for security vulnerabilities. Report them privately through the Security tab of this repository ("Report a vulnerability", https://github.com/dodokim-lab/docs-suit/security/advisories/new). Only the latest `main` branch receives fixes. This is a one-person project, so the timelines above are best effort: an acknowledgement within 7 days and an assessment within 30 days.
