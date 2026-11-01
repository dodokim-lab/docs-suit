# 동작 테스트: claude

- 날짜: 2026-11-01
- 에이전트: 2.1.316 (Claude Code)
- 스킬 자리: 임시 작업 폴더
- SKILL.md 지문: c19f4df5
- 모델: claude-sonnet-5-5
- 고르기: 48/49 맞음
- 본문 검사: 37/39 맞음. 어법, 문체, 분량, 강조를 어림 기준으로 잰다
- 사실 보존: 요청에 준 사실 34개 가운데 34개가 본문에 남았다. 본문 검사의 맞음에는 넣지 않는다
- 검사 기록: 본문을 쓴 39건 가운데 39건이 check 로 성장 기록을 남겼다
- 여러 턴 흐름: 5/5 맞음
- 사용료: 9.13달러

## 요청 하나

| 케이스 | 기대 | 에이전트가 부른 것 | 판정 | 본문 검사 | 비고 | 초 |
|---|---|---|---|---|---|---|
| report | report | `compose --kind report --audience professor` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 63 |
| slides | slides | `compose --kind slides --audience listener` | 맞음 | 맞음 | 거절된 도구 2건, 먼저 질문해 한 번 더 재촉함 | 102 |
| minutes | minutes, 독자 teammate | `compose --kind minutes --audience teammate` | 맞음 | 맞음 |  | 29 |
| email | email, 독자 professor | `compose --kind email --audience professor --set markup=plain` | 맞음 | 맞음 |  | 30 |
| resume | resume | `compose --kind resume --audience recruiter` | 맞음 | 맞음 |  | 38 |
| cover-letter | cover-letter, 700자 | `compose --kind cover-letter --audience recruiter --set markup=plain --chars 700` | 맞음 | 맞음 |  | 36 |
| portfolio | portfolio | `compose --kind portfolio --audience recruiter` | 맞음 | 맞음 |  | 30 |
| interview | interview | `compose --kind interview --audience recruiter --set markup=plain` | 맞음 | 맞음 |  | 35 |
| abstract | abstract | `compose --kind abstract --audience reviewer` | 맞음 | 맞음 |  | 30 |
| proposal | proposal | `compose --kind proposal` | 맞음 | 맞음 |  | 60 |
| design-doc | design-doc | `compose --kind design-doc` | 맞음 | 맞음 | 거절된 도구 1건 | 54 |
| pr | pr | `compose --kind pr` | 맞음 | 맞음 |  | 27 |
| postmortem | postmortem | `compose --kind postmortem` | 맞음 | 맞음 |  | 35 |
| spec | spec | `compose --kind spec` | 맞음 | 맞음 |  | 41 |
| biz-report | biz-report, 독자 manager | `compose --kind biz-report --audience manager` | 맞음 | 맞음 |  | 41 |
| work-report | work-report, 독자 manager | `compose --kind work-report --audience manager` | 맞음 | 맞음 |  | 32 |
| blog | blog | `compose --kind blog --audience peer-dev` | 맞음 | 틀림: 분량 (1583자, 한도 1500자) | 먼저 질문해 한 번 더 재촉함 | 80 |
| newsletter | newsletter | `compose --kind newsletter --audience reader` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 47 |
| sns | sns, register=haeyo, length=brief | `compose --kind sns --audience reader --set register=haeyo --set length=brief` | 맞음 | 맞음 |  | 30 |
| guide | guide | `compose --kind guide --audience teammate,peer-dev --set exposure=team` | 맞음 | 맞음 |  | 39 |
| guide-steps | guide | `compose --kind guide --audience teammate` | 맞음 | 맞음 |  | 28 |
| notice | notice, 독자 stakeholder | `compose --kind notice --audience stakeholder` | 맞음 | 맞음 |  | 31 |
| script | script | `compose --kind script --audience listener` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 70 |
| patient-guide | patient-guide, 독자 patient | `compose --kind patient-guide --audience patient` | 맞음 | 맞음 |  | 27 |
| opinion | opinion, 독자 client | `compose --kind opinion --audience client` | 맞음 | 맞음 |  | 55 |
| set-register | report, register=polite | `compose --kind report --audience professor --set register=polite` | 맞음 | 맞음 | 거절된 도구 1건, 먼저 질문해 한 번 더 재촉함 | 68 |
| conflict-guide | design-doc, register=polite, 쓰기 전에 고르게 함 | `compose --kind design-doc --audience peer-dev --set register=polite` | 틀림: 쓰기 전에 지침 파일과 겹치는 값을 묻지 않았다 | - |  | 40 |
| set-voice-length | postmortem, voice=prose, length=brief | `compose --kind postmortem --set voice=prose --set length=brief` | 맞음 | 맞음 |  | 31 |
| set-exposure | blog 또는 guide, exposure=team | `compose --kind guide --audience peer-dev --set exposure=team` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 61 |
| set-voice-gov | work-report, 독자 manager, voice=gov | `compose --kind work-report --audience manager --set voice=gov --set markup=plain` | 맞음 | 맞음 |  | 28 |
| set-markup | notice, markup=plain | `compose --kind notice --audience teammate --set markup=plain` | 맞음 | 맞음 |  | 36 |
| audience-stakeholder | report, 독자 stakeholder | `compose --kind report --audience stakeholder` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 68 |
| folder-defaults | report, register=haeyo | `compose --kind report --audience professor` | 맞음 | 틀림: 어법 (합쇼체 12) | 먼저 질문해 한 번 더 재촉함 | 59 |
| revise-email | email, 독자 professor, 다듬기 | `compose --kind email --audience professor --set markup=plain --revise` | 맞음 | 맞음 |  | 27 |
| make-pptx | slides, .pptx 파일 | `compose --kind slides --audience listener` | 맞음 | 맞음 | 거절된 도구 1건 | 56 |
| make-docx | work-report, 독자 manager, .docx 파일 | `compose --kind work-report --audience manager` | 맞음 | 맞음 | 거절된 도구 1건 | 46 |
| toast | script 또는 종류 없음 | `compose --kind script --audience listener` | 맞음 | 맞음 |  | 37 |
| no-kind | 종류 없음 | `compose --set markup=plain --set register=haeyo --set voice=prose --set length=page` | 맞음 | 맞음 |  | 46 |
| skip-code | 부르지 않음 | `부르지 않음` | 맞음 | - |  | 10 |
| skip-question | 부르지 않음 | `부르지 않음` | 맞음 | - |  | 4 |
| no-profile | work-report | `compose --kind work-report --audience manager` | 맞음 | 맞음 |  | 29 |
| screen-kind | serve --detach, 탭 theme, 종류 work-report | `serve --detach --page theme --kind work-report` | 맞음 | - |  | 20 |
| screen-theme | serve --detach, 탭 theme | `serve --detach --page theme` | 맞음 | - |  | 19 |
| screen-setup | serve --detach, 탭 setup 또는 auto | `serve --page setup --detach` | 맞음 | - |  | 19 |
| screen-character | serve --detach, 탭 character 또는 auto | `serve --detach --page character` | 맞음 | - | 거절된 도구 3건 | 26 |
| look-direct | look hair bob, 대시보드 띄우지 않음 | `card --color, look, look hair` | 맞음 | - |  | 23 |
| look-offer | look, 대시보드 띄우지 않음, 대시보드 권함 | `look` | 맞음 | - |  | 23 |
| growth-log | growth log, 대시보드 띄우지 않음 | `growth log` | 맞음 | - | 거절된 도구 1건 | 23 |
| word | word 어플 앱, 대시보드 띄우지 않음 | `word 어플` | 맞음 | - |  | 17 |

## 여러 턴 흐름

| 흐름 | 기대 | 에이전트가 부른 것 | 판정 | 비고 | 초 |
|---|---|---|---|---|---|
| flow-bootstrap | 프로필 profile.class=office, 프로필 persona.call=지수 님, 프로필 persona.docs=['work-report', 'email'], 폴더 파일 profile=proj | `bootstrap --questions; bootstrap --profile proj --here --class office --call 지수 님 --affiliation 플랫폼팀 백엔드 3년 차 --goal 보고서를 빨리 끝내기 --docs work-report,email --yes` | 맞음 |  | 38 |
| flow-restyle | 프로필 audiences.manager.register=haeyo | `set register haeyo --audience manager` | 맞음 |  | 44 |
| flow-kind | 프로필 kinds.work-report.voice=prose, 프로필에 defaults.voice 없음 | `set voice prose --kind work-report` | 맞음 |  | 19 |
| flow-here | 폴더 파일 defaults.register=plain, 프로필에 defaults.register 없음 | `set register plain --here` | 맞음 |  | 18 |
| flow-learn | 프로필 어딘가에 register=polite, 내 문체 문서, 샘플 이름과 수치 새지 않음 | `learn --human samples/01-weekly.md samples/02-review.md samples/03-wrapup.md samples/04-request.md; learn --guide; set register polite; set voice prose; set emphasis none; voice set - --samples samples/01-weekly.md samples/02-review.md samples/03-wrapup.md samples/04-request.md` | 맞음 | 거절된 도구 1건 | 83 |
