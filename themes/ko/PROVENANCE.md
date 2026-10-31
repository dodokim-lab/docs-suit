# 받아 온 파일의 출처

테마 모음에 넣은 외부 파일의 출처와 해시다. CSS 와 라이선스 파일만 받고 스크립트는 받지 않는다. 두 CSS 모두 `url()` 과 `@import` 가 없어 렌더할 때 바깥에서 아무것도 받지 않는다. 받아 온 것들의 라이선스 원문은 저장소 맨 위의 `THIRD_PARTY_NOTICES.md` 에 모았다.

| 파일 | 원본 | 판 | 라이선스 | sha256 |
|---|---|---|---|---|
| `visual-doc/newcss/theme.css` | https://cdn.jsdelivr.net/npm/@exampledev/new.css@1.1.3/new.css | 1.1.3 | MIT | 3f23d324200cc0f408486ae90487df8fd5073992a7002bdc2e2c9cde560035d7 |
| `visual-doc/newcss/LICENSE` | https://cdn.jsdelivr.net/npm/@exampledev/new.css@1.1.3/LICENSE | 1.1.3 | MIT | 63878ab5877658b5e5f695ff29eefe3392474519dcf3d68e856c535ac0b62e5b |
| `visual-doc/sakura/theme.css` | https://cdn.jsdelivr.net/npm/sakura.css@1.5.0/css/sakura.css | 1.5.0 | MIT | c997043b8e58936644e2bd47acb561c2f997a1167daf5706ab6ad2ca4fe9629c |
| `visual-doc/sakura/LICENSE` | https://cdn.jsdelivr.net/npm/sakura.css@1.5.0/LICENSE.txt | 1.5.0 | MIT | 2b225c797073b287572ceefd27af71cf209d413c90938ddc87b5cb58b8e69209 |

`visual-doc/print/theme.css` 는 받아 온 파일이 아니라 이 저장소에서 새로 썼고, 저장소의 라이선스를 따른다.

웹 판 써 보기(`docs/try.html`)의 ChatGPT, Claude, Gemini 로고는 simple-icons 15.0.0 의 `openai.svg`, `claude.svg`, `googlegemini.svg` 에서 그림 경로만 옮겼다. 원본은 https://cdn.jsdelivr.net/npm/simple-icons@15.0.0/icons/ 아래에 있다. 그림 데이터는 CC0-1.0 이고 로고의 상표권은 각 회사에 있으며, 그 서비스를 여는 단추에만 쓴다.

웹 판 써 보기의 제목 띠와 이름표에 쓰는 글꼴은 Neo둥근모를 파일째 넣었다. 본문과 단추에는 쓰지 않는다.

| 파일 | 원본 | 판 | 라이선스 | sha256 |
|---|---|---|---|---|
| `docs/fonts/neodgm.woff2` | https://cdn.jsdelivr.net/gh/neodgm/neodgm-webfont@1.600/neodgm/neodgm.woff2 | 1.600 | SIL OFL 1.1 | 6a6f47f769d55dbf57c90c567d53d910d1aae944057802cd9e0824dd00e58a6f |
| `docs/fonts/neodgm-LICENSE.txt` | https://cdn.jsdelivr.net/gh/neodgm/neodgm-webfont@1.600/LICENSE.txt | 1.600 | SIL OFL 1.1 | 753c35320ea841d34234e0725f4474c6f90a6173c0b8deaafadab20cca89e784 |

머리 맵의 기와집과 돌담, 나무, 돌길 타일(`docs/map.js`)은 이 저장소에서 새로 그렸다.

## 본문 검사와 문장 규칙의 출처

`tells.yaml` 의 패턴과 `base.md` 의 문장 규칙, 상투 표현 규칙은 아래 공개 자료에서 아이디어를 빌려 새로 썼다. 문구와 정규식은 옮기지 않았다. 외부 자료끼리 판정이 엇갈리거나 사람 글에도 흔하다고 잰 표현은 `error` 에 넣지 않았다.

| 자료 | 빌린 것 | 라이선스 |
|---|---|---|
| im-not-ai, https://github.com/epoko77-ai/im-not-ai | 한국어 AI 말투의 분류와 사람 글 대비 빈도, 부정 대구와 분열문, 이중 조사, 피동 진행 같은 문형, 금지어로 두면 안 되는 표현과 오탐 사례 | MIT |
| patina, https://github.com/devswha/patina | 사람 글보다 자주 나오는 표현 목록, 단어만 고친 글에 AI 티가 남는다는 실험 | MIT |
| KatFishNet, https://arxiv.org/abs/2503.00032 | 연결어미 뒤 쉼표가 사람 글보다 LLM 글에 잦다는 측정 | 논문 CC BY-NC-ND 4.0 |
| Wikipedia: Signs of AI writing, https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing | 예고와 인사, 맺음 요약, 굵은 라벨 목록 같은 신호의 분류와 신호 하나로 판정하지 않는다는 원칙 | 위키백과 기본 CC BY-SA 4.0 |
| textlint-rule-preset-ai-writing, https://github.com/textlint-ja/textlint-rule-preset-ai-writing | 술어 뒤 쌍점, 기계적인 강조, 과장어 규칙 | MIT |
| vale-ai-tells, https://github.com/krishnasunkam/vale-ai-tells | 오류와 제안의 두 층, 깨끗한 글에서 걸리지 않는지 재는 방식 | MIT |
| blader/humanizer, https://github.com/blader/humanizer | 패턴 분류와 검출기를 피하려는 게 아니라 사람 독자를 위해 고친다는 목표 | MIT |
| ASD-STE100 Simplified Technical English, https://www.asd-ste100.org/ | 절차문을 설명문보다 짧게 쓰고, 단계 하나에 동작 하나, 조건과 주의는 동작 앞에 둔다는 규칙. 가이드 틀의 단계 규칙과 `check` 의 단계 검사가 이것을 빌렸다 | 표준 문서는 ASD 가 무료로 배포한다 |
