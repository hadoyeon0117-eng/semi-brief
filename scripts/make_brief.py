#!/usr/bin/env python3
"""매일 반도체 데일리 브리핑을 Claude API(웹 검색 포함)로 만들어 index.html에 심는다.

필요한 환경 변수: ANTHROPIC_API_KEY (GitHub 저장소 Secrets)
선택: CLAUDE_MODEL (비우면 최신 Sonnet 모델을 자동 선택)
"""
import json, os, re, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

API = "https://api.anthropic.com/v1"
KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "index.html")
BRIEF_DIR = os.path.join(ROOT, "briefs")


def call(path, body=None, retries=4):
    headers = {"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    for i in range(retries):
        req = urllib.request.Request(API + path, data=data, headers=headers, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            if e.code in (429, 500, 502, 503, 529) and i < retries - 1:
                time.sleep(30 * (i + 1)); continue
            sys.exit(f"API 오류 {e.code}: {msg}")
        except urllib.error.URLError as e:
            if i < retries - 1:
                time.sleep(30); continue
            sys.exit(f"네트워크 오류: {e}")


def pick_model():
    m = os.environ.get("CLAUDE_MODEL", "").strip()
    if m:
        return m
    models = call("/models?limit=100").get("data", [])
    for x in models:  # 최신순 정렬
        if "sonnet" in x["id"]:
            return x["id"]
    return models[0]["id"]


def prompt_for(today, weekday):
    return f"""오늘은 {today}({weekday}, 한국 시간)이다. 한국 개인투자자를 위한 '반도체 데일리 브리핑' 한 건을 만든다.

절차:
1. web_search로 다음 네 주제의 최신(지난 24시간) 한국어 뉴스를 각각 검색한다: (a) 반도체 시황·메모리(D램/HBM/낸드) 가격 (b) 뉴욕증시·세계 시장 전망(금리·유가·FOMC 등) (c) 코스피·국내 증시 마감 시황과 주식 뉴스 (d) SK하이닉스 뉴스·주가. 결과가 얇으면 추가 검색한다. 주말이면 주말·주간 전망 기사 위주로 정리한다.
2. 기사 문장을 그대로 베끼지 말고 자기 말로 요약한다. 각 항목은 3~5문장, 섹션당 2~4항목. source.url에는 실제로 검색에서 확인한 기사 주소만 넣는다.
3. 최종 답변은 아래 스키마의 JSON 객체 하나만 출력한다. 앞뒤에 설명·마크다운 코드블록을 붙이지 않는다.

{{
"date":"{today}",
"createdAt":"ISO 8601 (+09:00 오프셋)",
"summary":"오늘 하루를 3문장으로 요약(가장 중요한 흐름 + 하이닉스 + 오늘/내일 일정)",
"ticker":[{{"name":"코스피","value":"지수","chg":"+x.xx%"}}, {{"name":"코스닥",...}}, {{"name":"SK하이닉스","value":"종가 원","chg":"..."}}, {{"name":"삼성전자",...}}, {{"name":"필라델피아 반도체","value":"...","chg":"..."}}, {{"name":"나스닥",...}}, {{"name":"美 10년물 금리",...}}, {{"name":"WTI 유가",...}}],
"sections":[
{{"title":"반도체 시황","tag":"SEMI","items":[{{"head":"제목","body":"요약","source":{{"name":"매체명","url":"https://..."}}}}]}},
{{"title":"세계 시장 전망","tag":"GLOBAL","items":[...]}},
{{"title":"국내 증시 · 주식 뉴스","tag":"KOSPI","items":[...]}},
{{"title":"SK하이닉스","tag":"000660","items":[...]}}
],
"terms":{{"용어":"초보 투자자용 한두 문장 설명"}},
"committee":{{
"members":[ {{"name":"김버핏","role":"가치투자의 대가","stance":"매수|비중확대|분할 매수|보유|관망|중립|경계|비중축소 중 하나(짧게)","view":"오늘 뉴스를 근거로 3~5문장 의견"}}, ... 9명 전원 ],
"verdict":{{"result":"의결 결과 한 줄 (예: 보유 유지 + 실적 확인 후 분할 매수 (찬성 6 · 관망 2 · 반대 1))","tally":{{"매수·비중확대":0,"보유":0,"관망·중립":0,"경계·축소":0}},"summary":"의결 이유 3~4문장","conditions":"의결이 바뀔 조건·점검 포인트 ①②③④ 형식 + 마지막에 '(가상 인물의 토론이며 투자 권유가 아닙니다.)'"}}
}},
"quiz":[ {{"q":"오늘 뉴스 복습 문제","options":["보기1","보기2","보기3","보기4"],"answer":0,"explain":"정답 해설 1~2문장"}}, ... 정확히 5문제 ]
}}

committee의 9명은 반드시 아래 인물이며 이 순서로, 각자의 핵심 질문에 답하는 관점으로 오늘 뉴스를 해석한다(오늘 사실에 근거):
1 김버핏(가치투자의 대가: 내재가치·경제적 해자·경영진·현금창출력·안전마진. "10년 보유해도 괜찮은 기업인가? 지금 가격은 합리적인가?")
2 하젠슨(AI 산업의 미래학자: AI 인프라·GPU·HBM·데이터센터 수요·성장 단계. "AI 혁명은 몇 단계인가? 다음에 돈이 흘러갈 곳은?")
3 최보수(원금 보존 전문가: 최대 손실·신용융자·반대매매·유동성·최악 시나리오. "틀렸을 때 얼마나 잃고 견딜 수 있는가?")
4 레이달리(거시경제 전략가: 금리·유동성·달러·인플레이션·부채 사이클·지정학. "세계경제는 어느 사이클이고 자금은 어디로 가는가?")
5 반도체박(반도체 업황 분석가: DRAM/NAND 가격·HBM 계약·경쟁사 증설·재고·CAPEX·EPS. "슈퍼사이클은 초기·중기·후기 중 어디? 이익 정점은 언제?")
6 드러켄(시장 심리·수급 전략가: 기대·기관/외국인 수급·추세·포지셔닝·선반영. "좋은 뉴스에도 주가가 빠지는 이유는? 시장은 무엇을 이미 반영했나?")
7 하워드(시장 사이클·역발상: 공포와 탐욕·과열/과매도·신용 사이클·위험 대비 보상. "지금 시장은 지나치게 낙관적인가 비관적인가?")
8 윤팩트(회계·실적 검증: 공시·재무제표·컨센서스·보도 대조, 착시와 근거 없는 낙관 적발. "이 뉴스는 실제 실적을 바꾸는가? 확인된 사실인가 기대인가?")
9 강반대(악마의 대변인: 나머지 8명의 합의에 의무적으로 반대, 틀릴 수 있는 경로와 간과한 위험. "우리 모두가 틀렸다면 그 이유는?")
verdict는 9명의 stance를 집계해 다수 의견으로 정하되 소수 의견을 summary에 한 줄 남긴다.

"chg"는 상승이면 "+"로, 하락이면 "-"로 시작한다. "terms"에는 오늘 본문에 등장하는 어려운 용어 중 기본 사전에 없을 법한 것 6~12개를 넣는다(기본 사전: HBM, HBM4, HBM3E, D램, 범용 D램, 낸드, 메모리 슈퍼사이클, 영업이익, 영업이익률, 주주환원, 특별배당, 자사주 소각, 매수 사이드카, 외국인 순매수, 필라델피아 반도체지수, FOMC, PCE 물가, 10년물 금리, 하이일드 스프레드, 레버리지 ETF, 인버스 ETF, 소부장, 네오클라우드, AI 거품론, IPO, GDP, ASP, 계약가격, 피크아웃, 베이스다이, 적층, 키옥시아, CXMT, 빅테크, 데이터센터, 목표지수). 본문에 쓴 용어 표기와 terms의 키 표기가 정확히 같아야 한다. 퀴즈는 오늘 브리핑 본문에서 답을 찾을 수 있는 문제로만 낸다. 투자 권유 표현은 쓰지 않는다."""


def extract_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start = text.find("{")
    if start < 0:
        raise ValueError("JSON 시작을 찾지 못함")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return obj


def generate(today, weekday, model):
    messages = [{"role": "user", "content": prompt_for(today, weekday)}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 15,
              "user_location": {"type": "approximate", "country": "KR", "timezone": "Asia/Seoul"}}]
    for _ in range(6):
        res = call("/messages", {"model": model, "max_tokens": 32000, "tools": tools, "messages": messages})
        if res.get("stop_reason") == "pause_turn":
            messages.append({"role": "assistant", "content": res["content"]})
            continue
        break
    texts = [b["text"] for b in res["content"] if b.get("type") == "text"]
    # 마지막 텍스트 블록부터 JSON을 찾는다
    for t in reversed(texts):
        try:
            return extract_json(t)
        except Exception:
            pass
    return extract_json("".join(texts))


def validate(b, today):
    need = ["date", "summary", "ticker", "sections", "terms", "committee", "quiz"]
    miss = [k for k in need if k not in b]
    if miss:
        raise ValueError(f"빠진 항목: {miss}")
    b["date"] = today
    if len(b["committee"].get("members", [])) != 9:
        raise ValueError("위원회 인원이 9명이 아님")
    if not b["sections"]:
        raise ValueError("섹션이 비어 있음")


def embed(brief):
    s = open(INDEX, encoding="utf-8").read()
    a, z = "/*__BRIEFS__*/", "/*__END__*/"
    i, j = s.index(a) + len(a), s.index(z)
    arr = json.loads(s[i:j])
    arr = [x for x in arr if x.get("date") != brief["date"]] + [brief]
    arr.sort(key=lambda x: x["date"])
    payload = json.dumps(arr, ensure_ascii=False).replace("</", "<\\/")
    open(INDEX, "w", encoding="utf-8").write(s[:i] + payload + s[j:])


def main():
    if not KEY:
        sys.exit("ANTHROPIC_API_KEY가 설정되지 않았습니다 (저장소 Settings > Secrets > Actions).")
    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")
    weekday = "월화수목금토일"[now.weekday()] + "요일"
    model = pick_model()
    print("모델:", model, "날짜:", today)
    last = None
    for attempt in range(2):
        try:
            brief = generate(today, weekday, model)
            validate(brief, today)
            break
        except Exception as e:
            last = e
            print("재시도:", e)
    else:
        sys.exit(f"브리핑 생성 실패: {last}")
    os.makedirs(BRIEF_DIR, exist_ok=True)
    with open(os.path.join(BRIEF_DIR, today + ".json"), "w", encoding="utf-8") as f:
        json.dump(brief, f, ensure_ascii=False, indent=1)
    embed(brief)
    print("완료:", today, brief["summary"][:80])


if __name__ == "__main__":
    main()
