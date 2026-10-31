"""웹 조립(core.js)과 비교할 조립 결과를 suit.py 로 만들어 JSON 으로 낸다. tests/parity.js 가 부른다."""
import importlib.util
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("suit", ROOT / "suit.py")
suit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suit)
th = suit.Themes(ROOT / "themes" / suit.DEFAULT_LANG)

profiles = [
    {},
    {"persona": {"call": "민수 님", "affiliation": "백엔드, 2년 차", "facts": "지도 시각화를 좋아한다", "docs": ["pr"]},
     "defaults": {"register": "haeyo", "exposure": "team"}, "audiences": {"professor": {"skeleton": "pcs"}},
     "kinds": {"work-report": {"voice": "prose", "exposure": "public"}, "report": {"skeleton": "chrono", "length": "brief"}},
     "words": {"어플": "앱", "로그 인": "로그인"}},
]
extras = [
    {"sets": {}, "chars": None, "fmt": "prompt", "revise": False, "voice": None},
    {"sets": {"register": "polite", "exposure": "submit", "visual-deck": "contrast", "markup": "html"}, "chars": 800,
     "fmt": "output-style", "revise": True,
     "voice": "- 문장은 결론으로 열고 근거를 뒤에 붙인다.\n- 목록 끝은 다음에 할 일로 맺는다.\n\n> 평균 대기 시간은 7분이었다."},
]
aud_ids = list(th.audiences)
cases = []
for i, (cls, kind) in enumerate(itertools.product([None] + list(th.classes), [None] + list(th.kinds))):
    # 종류 없는 글은 대화로 정하는 조립과 슬롯 전체의 테마를 보이는 조립을 둘 다 견준다
    for prof, ex, talk in itertools.product(profiles, extras, [False, True] if kind is None else [False]):
        auds = [] if (i + len(cases)) % 3 else [aud_ids[i % len(aud_ids)]]
        text, _ = suit.compose(th, kind, auds or None, ex["sets"], prof, cls, ex["chars"], ex["fmt"], ex["revise"],
                               talk=talk, voice=ex["voice"])
        rv = suit.review(th, kind, auds or None, ex["sets"], prof, cls, ex["chars"], talk=talk, voice=ex["voice"])
        cases.append({"cls": cls, "kind": kind, "auds": auds, "profile": prof, **ex, "talk": talk, "expected": text,
                      "review": rv})
# 슬롯 파일에 constructor 같은 이름이 와도 웹은 파이썬의 dict 처럼 제 키만 본다. in 으로 견주면 물려받은 속성을 값으로 받는다
odd = {"defaults": {"register": "constructor", "voice": "toString"}, "kinds": {"email": {"length": "hasOwnProperty"}}}
cases.append({"cls": None, "kind": "email", "auds": [], "profile": odd, **extras[0], "talk": False,
              "expected": suit.compose(th, "email", None, {}, odd)[0], "review": suit.review(th, "email", None, {}, odd)})
# 웹 캐릭터 만들기가 내려받게 하는 슬롯 파일. suit.py 가 읽는 꼴과 같아야 한다.
slots = [
    {"profile": {"class": "office", "lang": "ko", "agents": ["claude", "codex"]},
     "persona": {"call": '민수 "님"', "affiliation": "백엔드, 2년 차: 결제", "goal": " 앞뒤 공백 ", "facts": "#1 은 [지도]",
                 "docs": ["work-report", "email"]},
     "look": {"hair": "long"}, "defaults": {"register": "polite", "length": "brief"},
     "audiences": {"manager": {"register": "haeyo"}}},
    {"profile": {"class": "student", "lang": "ko"}, "persona": {}, "defaults": {}},
]
slot_cases = [{"data": d, "expected": suit.dump_yaml(d)} for d in slots]
# 웹이 그리는 캐릭터. 기본 몸에 옷, 머리, 소품을 겹치고, 클래스가 그 차수까지 열지 않은 꾸미기는 기본값으로 둔다.
office = {"class": "office"}
looks = [({}, None), ({"look": {"base": "b"}}, 0), ({"look": {"color": "wine", "hair": "bangs"}}, 1),
         ({"profile": office, "look": {"top": "suit", "prop": "tie", "color": "navy", "hair": "short"}}, 4),
         ({"profile": office, "look": {"top": "suit", "prop": "tie", "color": "navy"}}, 2),
         ({"profile": {"class": "researcher"}, "look": {"top": "coat", "prop": "flask", "color": "ivory"}}, 4),
         ({"profile": {"class": "student"}, "look": {"top": "uniform", "prop": "backpack", "hair": "long"}}, 3),
         ({"profile": {"class": "developer"}, "look": {"prop": "laptop", "top": "hoodie"}}, 4),
         ({"profile": {"class": "planner"}, "look": {"prop": "clipboard", "top": "blazer", "color": "mustard"}}, 4),
         ({"profile": {"class": "creator"}, "look": {"prop": "camera", "top": "stripe", "color": "pink"}}, 4),
         ({"profile": {"class": "creator"}, "look": {"prop": "tie"}}, 4), ({"look": {"top": "nope"}}, 4),
         ({"profile": {"class": "student"}}, 4), ({"profile": office}, 1),
         ({"profile": {"class": "researcher"}, "look": {"prop": "glasses", "color": "none"}}, 4),
         ({"profile": {"class": "planner"}, "look": {"prop": "none"}}, 3)]
looks.append(({"look": {"base": "constructor", "top": "toString", "prop": "valueOf", "color": "hasOwnProperty"}}, 4))
look_cases = [{"slot": slot, "tier": tier, "look": suit.look_of(th, slot, tier),
               "expected": suit.look_grid(th, suit.look_of(th, slot, tier))} for slot, tier in looks]
json.dump({"compose": cases, "slots": slot_cases, "looks": look_cases}, sys.stdout, ensure_ascii=False)
