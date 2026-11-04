# 동작 테스트: codex

- 날짜: 2026-11-04
- 에이전트: codex-cli 0.166.0
- 스킬 자리: 임시 작업 폴더
- SKILL.md 지문: 177c506b
- 모델: gpt-6.1-sol
- 요금제: plus
- 고르기: 50/50 맞음
- 본문 검사: 40/40 맞음. 어법, 문체, 분량, 강조를 어림 기준으로 잰다
- 사실 보존: 요청에 준 사실 36개 가운데 36개가 본문에 남았다. 본문 검사의 맞음에는 넣지 않는다
- 검사 기록: 본문을 쓴 40건 가운데 40건이 check 로 성장 기록을 남겼다
- 여러 턴 흐름: 5/5 맞음
- 사용료: 에이전트가 알려 주지 않음

## 요청 하나

| 케이스 | 기대 | 에이전트가 부른 것 | 판정 | 본문 검사 | 비고 | 초 |
|---|---|---|---|---|---|---|
| report | report | `compose --kind report --audience professor` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 126 |
| slides | slides | `compose --kind slides --audience listener` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 86 |
| minutes | minutes, 독자 teammate | `compose --kind minutes --audience teammate` | 맞음 | 맞음 |  | 26 |
| email | email, 독자 professor | `compose --kind email --audience professor --set markup=plain` | 맞음 | 맞음 |  | 20 |
| resume | resume | `compose --kind resume --audience recruiter` | 맞음 | 맞음 |  | 52 |
| cover-letter | cover-letter, 700자 | `compose --kind cover-letter --audience recruiter --set markup=plain --chars 700` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 36 |
| portfolio | portfolio | `compose --kind portfolio` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 34 |
| interview | interview | `compose --kind interview --audience recruiter` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 41 |
| abstract | abstract | `compose --kind abstract --audience reviewer` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 35 |
| proposal | proposal | `compose --kind proposal` | 맞음 | 맞음 |  | 142 |
| design-doc | design-doc | `compose --kind design-doc --audience peer-dev` | 맞음 | 맞음 |  | 103 |
| pr | pr | `compose --kind pr --audience peer-dev` | 맞음 | 맞음 |  | 25 |
| postmortem | postmortem | `compose --kind postmortem` | 맞음 | 맞음 |  | 55 |
| spec | spec | `compose --kind spec` | 맞음 | 맞음 |  | 60 |
| biz-report | biz-report, 독자 manager | `compose --kind biz-report --audience manager` | 맞음 | 맞음 |  | 91 |
| work-report | work-report, 독자 manager | `compose --kind work-report --audience manager` | 맞음 | 맞음 |  | 34 |
| blog | blog | `compose --kind blog --audience reader` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 46 |
| newsletter | newsletter | `compose --kind newsletter --audience reader` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 47 |
| sns | sns, register=haeyo, length=brief | `compose --kind sns --set register=haeyo --set length=brief` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 26 |
| guide | guide | `compose --kind guide --audience peer-dev` | 맞음 | 맞음 |  | 26 |
| guide-steps | guide | `compose --kind guide --audience peer-dev` | 맞음 | 맞음 |  | 35 |
| notice | notice, 독자 stakeholder | `compose --kind notice --audience stakeholder` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 45 |
| press-release | press-release | `compose --kind press-release` | 맞음 | 맞음 |  | 29 |
| script | script, 1500자 | `compose --kind script --audience listener --chars 1500` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 69 |
| patient-guide | patient-guide, 독자 patient | `compose --kind patient-guide --audience patient` | 맞음 | 맞음 |  | 27 |
| opinion | opinion, 독자 client | `compose --kind opinion --audience client` | 맞음 | 맞음 |  | 86 |
| set-register | report, register=polite | `compose --kind report --audience professor --set register=polite` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 76 |
| conflict-guide | design-doc, register=polite, 쓰기 전에 고르게 함 | `compose --kind design-doc --audience peer-dev; compose --kind design-doc --audience peer-dev --set register=polite` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 101 |
| set-voice-length | postmortem, voice=prose, length=brief | `compose --kind postmortem --set voice=prose --set length=brief` | 맞음 | 맞음 |  | 37 |
| set-exposure | blog 또는 guide, exposure=team | `compose --kind blog --audience peer-dev --set exposure=team` | 맞음 | 맞음 |  | 51 |
| set-voice-gov | work-report, 독자 manager, voice=gov | `compose --kind work-report --audience manager --set voice=gov --set markup=plain` | 맞음 | 맞음 |  | 19 |
| set-markup | notice, markup=plain | `compose --kind notice --audience teammate --set markup=plain` | 맞음 | 맞음 | 먼저 질문해 한 번 더 재촉함 | 40 |
| audience-stakeholder | report, 독자 stakeholder | `compose --kind report --audience stakeholder` | 맞음 | 맞음 |  | 90 |
| folder-defaults | report, register=haeyo | `compose --kind report --audience professor` | 맞음 | 맞음 |  | 65 |
| revise-email | email, 독자 professor, 다듬기 | `compose --kind email --audience professor --set markup=plain --set length=brief --revise` | 맞음 | 맞음 |  | 23 |
| make-pptx | slides, .pptx 파일 | `compose --kind slides --audience listener; compose --kind script --audience listener --chars 1500` | 맞음 | 맞음 |  | 82 |
| make-docx | work-report, 독자 manager, .docx 파일 | `compose --kind work-report --audience manager` | 맞음 | 맞음 |  | 52 |
| toast | script 또는 종류 없음 | `compose --kind script --audience listener` | 맞음 | 맞음 |  | 37 |
| no-kind | 종류 없음 | `compose` | 맞음 | 맞음 |  | 36 |
| skip-code | 부르지 않음 | `부르지 않음` | 맞음 | - |  | 11 |
| skip-question | 부르지 않음 | `부르지 않음` | 맞음 | - |  | 7 |
| no-profile | work-report | `compose --kind work-report --audience manager` | 맞음 | 맞음 |  | 25 |
| screen-kind | serve --detach, 탭 theme, 종류 work-report | `serve --detach --page theme --kind work-report` | 맞음 | - |  | 15 |
| screen-theme | serve --detach, 탭 theme | `serve --detach --page theme` | 맞음 | - |  | 14 |
| screen-setup | serve --detach, 탭 setup 또는 auto | `serve --page setup --detach` | 맞음 | - |  | 16 |
| screen-character | serve --detach, 탭 character 또는 auto | `serve --detach --page character` | 맞음 | - |  | 14 |
| look-direct | look hair bob, 대시보드 띄우지 않음 | `look, look hair` | 맞음 | - |  | 18 |
| look-offer | look, 대시보드 띄우지 않음, 대시보드 권함 | `look` | 맞음 | - |  | 16 |
| growth-log | growth log, 대시보드 띄우지 않음 | `growth log` | 맞음 | - |  | 16 |
| word | word 어플 앱, 대시보드 띄우지 않음 | `word 어플` | 맞음 | - |  | 14 |

## 여러 턴 흐름

| 흐름 | 기대 | 에이전트가 부른 것 | 판정 | 비고 | 초 |
|---|---|---|---|---|---|
| flow-bootstrap | 프로필 profile.class=office, 프로필 persona.call=지수 님, 프로필 persona.docs=['work-report', 'email'], 폴더 파일 profile=proj | `bootstrap --questions; bootstrap --profile proj --here --class office --call 지수 님 --affiliation 플랫폼팀 백엔드 3년 차 --goal 보고서를 빨리 끝내는 것 --docs work-report,email --facts  --dislikes  --yes` | 맞음 |  | 35 |
| flow-restyle | 프로필 audiences.manager.register=haeyo | `set register haeyo --audience manager` | 맞음 |  | 49 |
| flow-kind | 프로필 kinds.work-report.voice=prose, 프로필에 defaults.voice 없음 | `set voice prose --kind work-report` | 맞음 |  | 16 |
| flow-here | 폴더 파일 defaults.register=plain, 프로필에 defaults.register 없음 | `set register plain --here` | 맞음 |  | 18 |
| flow-learn | 프로필 어딘가에 register=polite, 내 문체 문서, 샘플 이름과 수치 새지 않음 | `learn samples/01-weekly.md samples/02-review.md samples/03-wrapup.md samples/04-request.md --human; learn --guide; set register polite --audience teammate; set voice prose --audience teammate; set emphasis none --audience teammate; voice set - --samples samples/01-weekly.md samples/02-review.md samples/03-wrapup.md samples/04-request.md` | 맞음 |  | 76 |
