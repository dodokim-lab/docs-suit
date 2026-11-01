"""동작 테스트 케이스. tests/agent/run.py 가 읽는다.

expect 가 compose 이면 에이전트가 suit.py compose 를 불러야 한다. kind 는 기대하는 문서 종류이고, 여럿을 허용하면
목록으로, 종류 없이 조립해야 하면 빈 문자열로 쓴다. expect 가 serve 이면 suit.py serve 를 --detach 로 불러 대시보드의
page 탭을 띄워야 한다. page 가 auto 면 --page 를 빼고 엔진에 맡겨도 맞다. expect 가 call 이면 대시보드를 띄우지 않고
suit.py <call> <args> 를 불러야 하고, offer 가 True 면 답에서 대시보드를 권해야 한다. want 는 조립 결과에서 이 값이어야 하는 축이다. audience 는 실제로
쓰인 독자에 들어 있어야 하는 키다. revise 가 True 면 --revise 를 붙여야 하고, 아니면 붙이지 않아야 한다. expect 가 skip 이면 suit.py 를 부르지 않아야 한다. profile 이 False 이면 프로필 없이
시작한다. facts 는 요청에 준 사실 가운데 본문에 남아야 하는 말이고, 목록 안의 목록은 그 가운데 하나만 있으면 된다. folder 는 작업 폴더에 둘 .docs-suit.yaml 이고, files 는 작업 폴더에 둘 다른 파일이다.
expect 가 conflict 이면 files 의 에이전트 지침 파일이 docs-suit 와 다른 값을 정해 둔 것이다. 첫 답에서 쓰기 전에 mention 가운데 하나를
들어 어느 쪽을 따를지 물어야 하고, 재촉받은 뒤에는 want 의 값으로 조립해야 한다. 어느 케이스든 사용자의 답 없이 bootstrap 으로 프로필을 저장하면
틀린다.
"""

# 시험 프로필. bootstrap 이 만드는 것과 같은 꼴이다.
PROFILE = {
    "profile": {"class": "office", "lang": "ko"},
    "persona": {"call": "지수 님", "affiliation": "플랫폼팀 백엔드 3년 차", "goal": "보고와 공유 문서를 빨리 끝낸다",
                "dislikes": "과장된 마케팅 말투", "docs": ["work-report", "email", "minutes"]},
}

CASES = [
    # 문서 종류마다 하나
    {"id": "report", "facts": [["사흘", "3일"]], "kind": "report",
     "ask": "환경공학 수업 기말 레포트 써 줘. 주제는 우리 동네 정류장 대기 시간 조사고, 평일 아침 사흘 동안 재 봤어."},
    {"id": "slides", "kind": "slides",
     "ask": "다음 주 동아리 발표 자료 만들어 줘. 정류장 대기 시간을 조사한 결과를 10분 동안 발표해."},
    {"id": "minutes", "facts": ["결제 개선", "지수", "민호", "금요일"], "kind": "minutes", "audience": "teammate",
     "ask": "오늘 회의 내용을 팀 공유용으로 정리해 줘. 다음 스프린트는 결제 개선에 집중하고, 캐시는 지수, 모니터링은 민호가 맡고, 금요일까지 설계 초안을 낸다."},
    {"id": "email", "facts": ["화요일"], "kind": "email", "audience": "professor",
     "ask": "다음 주 화요일에 교수님 면담이 가능한지 여쭤보는 메일 써 줘. 졸업 논문 주제를 상담하려고 해."},
    {"id": "resume", "kind": "resume",
     "ask": "백엔드 개발자 신입 지원용 이력서 써 줘. 학교 프로젝트로 버스 도착 알림 앱을 만들었고 Spring 이랑 MySQL 을 썼어."},
    {"id": "cover-letter", "kind": "cover-letter", "chars": 700,
     "ask": "데이터 분석 직무 자기소개서의 지원 동기 항목 써 줘. 700자 이내로."},
    {"id": "portfolio", "kind": "portfolio",
     "ask": "디자인 포트폴리오에 넣을 프로젝트 소개 글 써 줘. 정류장 안내판을 다시 디자인한 프로젝트야."},
    {"id": "interview", "kind": "interview",
     "ask": "면접에서 가장 힘들었던 협업 경험을 물으면 할 답변 정리해 줘. 조별 과제에서 연락이 끊긴 조원이 있었어."},
    {"id": "abstract", "facts": ["20%"], "kind": "abstract",
     "ask": "학회에 낼 논문 초록 써 줘. 버스 정류장 대기 시간을 GPS 데이터로 예측하는 모델이고, 기존 방법보다 오차가 20% 줄었어."},
    {"id": "proposal", "kind": "proposal",
     "ask": "연구계획서 써 줘. 정류장 대기 시간이 대중교통 이용 만족도에 주는 영향을 설문으로 조사하려고 해."},
    {"id": "design-doc", "facts": ["지수 백오프", ["세 번", "3번", "3회", "세 차례"]], "kind": "design-doc",
     "ask": "알림 서비스 재시도 큐 설계 문서 써 줘. 지금은 발송에 실패하면 그냥 버리는데, 지수 백오프로 세 번까지 다시 보내려고 해."},
    {"id": "pr", "facts": [["세 번", "3번", "3회", "세 차례"], ["두 개", "2개", "두 건", "2건"]], "kind": "pr",
     "ask": "이 PR 설명 써 줘. 정산 배치가 실패하면 세 번까지 다시 시도하게 바꿨고 테스트를 두 개 더했어."},
    {"id": "postmortem", "facts": ["30분", "설정값", "롤백"], "kind": "postmortem",
     "ask": "어제 배포 후 30분 동안 로그인이 실패했던 건 회고 문서로 정리해 줘. 원인은 새 설정값 누락이었고 롤백으로 복구했어."},
    {"id": "spec", "facts": ["3분"], "kind": "spec",
     "ask": "정류장 도착 알림 기능 기획서 써 줘. 버스가 3분 안에 도착하면 푸시를 보내는 기능이야."},
    {"id": "biz-report", "facts": ["120억", "15%"], "kind": "biz-report", "audience": "manager",
     "ask": "대표님께 올릴 내년 매출 계획 보고서 써 줘. 올해 매출은 120억이고, 내년엔 온라인 채널을 늘려 15% 키우려고 해."},
    {"id": "work-report", "facts": ["커넥션 풀", "800ms", "200ms", "캐시"], "kind": "work-report", "audience": "manager",
     "ask": "팀장님께 올릴 이번 주 업무 보고 써 줘. 결제 API 가 느렸던 원인이 DB 커넥션 풀 고갈이었고, 풀 크기를 조정하고 캐시를 붙여서 p95 가 800ms 에서 200ms 로 줄었어."},
    {"id": "blog", "kind": "blog",
     "ask": "기술 블로그에 올릴 글 써 줘. 서비스에 Redis 캐시를 붙였다가 캐시 정합성 문제로 고생한 경험담이야."},
    {"id": "newsletter", "kind": "newsletter",
     "ask": "이번 달 구독자에게 보낼 뉴스레터 써 줘. 동네 버스 노선이 바뀐 소식이랑 정류장 대기 시간 조사 결과를 담을 거야."},
    {"id": "sns", "kind": "sns", "want": {"register": "haeyo", "length": "brief"},
     "ask": "주말에 다녀온 카페 인스타 후기 써 줘. 해요체로 짧게."},
    {"id": "guide", "facts": ["make run", "make test"], "kind": "guide",
     "ask": "우리 팀 저장소 README 써 줘. 로컬에서 서버 띄우는 법이랑 테스트 돌리는 법을 넣어야 해. 서버는 make run, 테스트는 make test 야."},
    # 주의와 조건을 동작 뒤에 섞어 말한다. 단계 하나에 동작 하나, 주의는 동작 앞이라는 틀을 지키는지 본다
    {"id": "guide-steps", "kind": "guide", "facts": ["make setup", ".env.example", "DB_URL", "make db", "make run", "8080", "make reset", "make test"],
     "ask": "팀 저장소 온보딩 가이드 써 줘. 처음 받으면 make setup 으로 의존성을 깔고, .env.example 을 .env 로 복사해서 DB_URL 을 채워야 해. make db 로 로컬 DB 를 띄운 다음 make run 하면 8080 에서 떠. 8080 을 다른 프로그램이 쓰고 있으면 안 떠. make reset 은 로컬 DB 데이터를 다 지우니까 조심해야 하고, 테스트는 make test 인데 DB 가 떠 있어야 돌아가."},
    {"id": "notice", "kind": "notice", "audience": "stakeholder",
     "ask": "다른 팀에 다음 주 API 변경을 알리는 공지 써 줘. 응답 필드 하나의 이름이 바뀌어."},
    {"id": "script", "kind": "script",
     "ask": "다음 주 동아리 발표 원고 써 줘. 정류장 대기 시간 조사 결과를 5분 동안 말로 발표할 거고, 슬라이드는 이미 만들어 뒀어."},
    {"id": "patient-guide", "facts": [["2시간", "두 시간"], ["사흘", "3일"]], "kind": "patient-guide", "audience": "patient",
     "ask": "임플란트 수술 받은 환자분께 드릴 주의 사항 안내문 써 줘. 수술 당일은 거즈를 2시간 물고 있어야 하고, 사흘 동안 술과 담배는 안 돼. 피가 멈추지 않으면 바로 전화하라고 해 줘."},
    {"id": "opinion", "facts": [["운행일지", "운행기록"]], "kind": "opinion", "audience": "client",
     "ask": "고객사 대표님이 법인 차를 개인 용도로도 쓰는데 차 관련 비용을 회사 비용으로 처리해도 되는지 물어보셨어. 자문 답변 써 줘. 운행일지는 안 쓰고 있대."},

    # 사용자가 축을 말한 요청
    {"id": "set-register", "kind": "report", "want": {"register": "polite"},
     "ask": "교수님께 낼 정류장 대기 시간 조사 보고서 써 줘. 이번에는 합쇼체로 써 줘."},
    # 작업 폴더의 지침 파일이 정한 어법이 docs-suit 의 값(동료 개발자에게 평어체)과 다르다. 쓰기 전에 고르게 해야 한다
    {"id": "conflict-guide", "kind": "design-doc", "expect": "conflict", "want": {"register": "polite"},
     "mention": ["합쇼체", "AGENTS.md", "CLAUDE.md", "polite"],
     "files": {name: "# 이 저장소에서 일하는 법\n\n- 설계 문서와 PR 설명은 합쇼체로 쓴다. 팀 문서의 말투를 맞추기 위해서다.\n"
                     "- 테스트는 make test 로 돌린다.\n" for name in ("AGENTS.md", "CLAUDE.md")},
     "ask": "알림 서비스 재시도 큐 설계 문서 써 줘. 지금은 발송에 실패하면 그냥 버리는데, 지수 백오프로 세 번까지 다시 보내려고 해."},
    {"id": "set-voice-length", "kind": "postmortem", "want": {"voice": "prose", "length": "brief"},
     "ask": "어제 캐시 서버가 30분 멈춘 건 회고 문서로 써 줘. 개조식 말고 줄글로, 짧게."},
    # 사내 위키에 올릴 글이라 가이드·README·위키로 골라도 맞다. 재는 것은 공개 범위다.
    {"id": "set-exposure", "kind": ["blog", "guide"], "want": {"exposure": "team"},
     "ask": "사내 위키에만 올릴 기술 글 써 줘. 밖에는 공개하지 않아. 주제는 로그 수집 파이프라인을 정리한 이야기야."},
    {"id": "set-voice-gov", "kind": "work-report", "audience": "manager", "want": {"voice": "gov"},
     "ask": "한글 파일 보고서에 붙일 거라 □ ○ 기호 쓰는 공문서식 개조식으로 팀장님께 업무 보고 써 줘. 결제 오류를 고쳤고 재발 방지 모니터링을 붙이는 중이야."},
    {"id": "set-markup", "kind": "notice", "want": {"markup": "plain"},
     "ask": "동아리 단톡방에 올릴 공지 써 줘. 다음 주 모임 장소가 정류장 앞 카페로 바뀌어. 단톡방이라 마크다운 기호는 그대로 보여."},
    {"id": "audience-stakeholder", "kind": "report", "audience": "stakeholder",
     "ask": "이번 분기 실험 결과 보고서를 다른 팀 사람들이 읽을 수 있게 써 줘. 추천 알고리즘을 바꿨더니 클릭률이 3% 올랐어."},

    # 폴더 파일이 프로필 값을 덮는다
    {"id": "folder-defaults", "kind": "report", "folder": {"defaults": {"register": "haeyo"}}, "want": {"register": "haeyo"},
     "ask": "교수님께 낼 정류장 대기 시간 조사 보고서 써 줘. 평일 아침 사흘 동안 재 봤어."},

    # 다듬기. 사용자가 원문을 주면 --revise 를 붙인다
    {"id": "revise-email", "kind": "email", "audience": "professor", "revise": True,
     "ask": "교수님께 보낼 메일인데 너무 장황해서 다듬어 줘.\n\n안녕하세요 교수님, 저는 공간정보공학과 3학년 김민수입니다. "
            "다름이 아니오라 이번 학기 기말 보고서와 관련하여 여쭤볼 것이 있어서 이렇게 메일을 드리게 되었습니다. "
            "제가 정류장 대기 시간을 주제로 조사를 하고 있는데, 데이터를 모으는 데 시간이 생각보다 오래 걸려서요, "
            "혹시 마감을 일주일 정도 연장해 주실 수 있을지 여쭙고 싶습니다. 바쁘신 와중에 죄송합니다. 감사합니다."},

    # 문서 파일. 만든 파일을 check 에 넘기는지 보고, 파일에서 뽑은 글을 잰다
    {"id": "make-pptx", "kind": "slides", "file": ".pptx",
     "ask": "동아리 발표 자료를 pptx 파일로 만들어 줘. 정류장 대기 시간을 평일 아침 사흘 동안 쟀더니 평균 7분이었고, "
            "출근 시간대가 가장 길었어. 5분 발표야."},
    {"id": "make-docx", "kind": "work-report", "audience": "manager", "file": ".docx",
     "ask": "팀장님께 올릴 주간 업무 보고를 워드 파일(docx)로 만들어 줘. 이번 주에는 로그인 오류를 고쳤고, 다음 주에는 알림 재시도를 붙여."},

    # 경계
    # 축사는 소리 내어 읽는 글이라 발표 원고로 골라도 맞다. 종류가 정말 없는 글은 손편지로 잰다.
    {"id": "toast", "kind": ["script", ""],
     "ask": "친구 결혼식 축사 써 줘. 대학 동아리에서 만난 친구야."},
    {"id": "no-kind", "kind": "",
     "ask": "부모님 결혼 30주년에 드릴 손편지 글 써 줘. 내가 대학 다니는 동안 뒷바라지하느라 고생 많으셨어."},
    {"id": "skip-code", "expect": "skip",
     "ask": "이 정규식이 왜 이메일 주소를 못 잡는지 설명해 줘: ^[a-z]+@[a-z]+$"},
    {"id": "skip-question", "expect": "skip",
     "ask": "정류장 대기 시간을 영어로 뭐라고 해?"},
    {"id": "no-profile", "kind": "work-report", "profile": False,
     "ask": "팀장님께 올릴 주간 업무 보고 써 줘. 이번 주에는 로그인 오류를 고쳤어."},

    # 대시보드. 사용자가 화면에서 하겠다고 하면 에이전트가 serve --detach 로 맞는 탭을 띄워 준다
    {"id": "screen-kind", "expect": "serve", "page": "theme", "serve_kind": "work-report",
     "ask": "업무 보고 말투를 카드 보면서 바꾸고 싶어. 화면 열어 줘."},
    {"id": "screen-theme", "expect": "serve", "page": "theme",
     "ask": "docs-suit 테마를 카드 보면서 직접 고르고 싶어. 화면 열어 줘."},
    {"id": "screen-setup", "expect": "serve", "page": ["setup", "auto"], "profile": False,
     "ask": "docs-suit 세팅해 줘. 질문에 하나씩 답하는 건 번거로우니까 화면에서 고를게."},
    {"id": "screen-character", "expect": "serve", "page": ["character", "auto"],
     "ask": "docs-suit 대시보드 열어 줘. 화면에서 캐릭터 옷 좀 갈아입힐래."},
    # 대시보드에서 하는 일은 대화로도 된다. 값을 정한 요청은 묻지 않고 바로, 정하지 않은 요청은 고를 것을 보이며 대시보드를 권한다
    {"id": "look-direct", "expect": "call", "call": "look", "args": ["hair", "bob"],
     "ask": "docs-suit 캐릭터 머리를 단발로 바꿔 줘."},
    {"id": "look-offer", "expect": "call", "call": "look", "offer": True,
     "ask": "docs-suit 캐릭터 꾸미고 싶어."},
    {"id": "growth-log", "expect": "call", "call": "growth", "args": ["log"],
     "ask": "docs-suit 성장 기록 보여 줘. 어떤 문서로 경험치를 받았는지 궁금해."},
    # 팀이 정한 표기는 폴더 용어집에 남긴다
    {"id": "word", "expect": "call", "call": "word", "args": ["어플", "앱"],
     "ask": "이 폴더에서 쓰는 문서는 앞으로 '어플' 말고 '앱'으로 써 줘. 팀 표기 규칙이야."},
]

# 여러 턴 흐름. 턴마다 같은 세션을 이어 가고, 끝난 뒤 프로필과 폴더 파일에 남은 값을 본다.
# expect 의 profile 과 folder 는 점으로 이은 경로의 값이고, absent 는 프로필에 없어야 하는 경로다.
FLOWS = [
    {"id": "flow-bootstrap", "profile": False,
     "turns": ["docs-suit 세팅해 줘.",
               "직장인이야. 호칭은 지수 님, 소속은 플랫폼팀 백엔드 3년 차, 목표는 보고서를 빨리 끝내는 거야. "
               "자주 쓰는 문서는 업무 보고랑 메일이고, 나머지 질문은 건너뛸게."],
     # 캐릭터는 폴더마다 자란다. 새로 세팅하면 폴더 이름(proj)의 슬롯을 만들어 이 폴더에 이어야 한다
     "expect": {"profile": {"profile.class": "office", "persona.call": "지수 님", "persona.docs": ["work-report", "email"]},
                "folder": {"profile": "proj"}}},
    {"id": "flow-restyle",
     "turns": ["팀장님께 올릴 주간 업무 보고 써 줘. 이번 주에는 로그인 오류를 고쳤고, 다음 주에는 알림 재시도를 붙여.",
               "말투가 너무 딱딱해. 해요체로 바꿔 줘. 앞으로 팀장님께 쓰는 글은 계속 해요체로 해 줘."],
     "expect": {"profile": {"audiences.manager.register": "haeyo"}}},
    {"id": "flow-kind",
     "turns": ["앞으로 업무 보고는 개조식 말고 줄글로 써 줘. 다른 문서는 지금처럼 두고."],
     "expect": {"profile": {"kinds.work-report.voice": "prose"}, "absent": ["defaults.voice"]}},
    {"id": "flow-here",
     "turns": ["이 폴더에서는 앞으로 문서를 평어체로 써 줘. 다른 폴더는 지금처럼 두고."],
     "expect": {"folder": {"defaults.register": "plain"}, "absent": ["defaults.register"]}},
    # samples 폴더의 글은 지어낸 이름과 수치를 담았다. 내 문체 문서에 이것이 새면 틀린다.
    {"id": "flow-learn", "samples": True,
     "turns": ["예전에 내가 쓴 글 네 편을 samples 폴더에 넣어 뒀어. 이걸로 내 글쓰기 스타일을 맞춰 줘. "
               "모두 내가 직접 쓴 글이고 팀에 공유한 글이야.",
               "좋아, 제안한 값은 다 남겨 줘. 내 문체 문서는 초안을 보여 줘.",
               "그대로 저장해 줘."],
     "expect": {"anywhere": {"register": "polite"}, "voice": {"leak": ["솔밭", "모락", "윤하", "12분", "15분", "서른 건", "열에 하나"]}}},
]
