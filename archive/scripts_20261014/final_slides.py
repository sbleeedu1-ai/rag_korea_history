"""최종 발표 구글 슬라이드 설계도와 발표 스크립트를 한곳에서 만든다(2026-10-12, 작업기록 [407]).

실행: python scripts/final_slides.py <출력 폴더>
  → <출력 폴더>/spec.json  : google-workspace 스킬의 slides_helper.py build 입력(인치 단위)
  → <출력 폴더>/extra.json : build가 못 하는 요청(배경색, 표 강조 칸, 표 첫 열 굵게)
  → docs/기록/제출/최종발표_스크립트_20261012.md : 장마다 할 말 + 예상 질문(발표자 노트에도 같은 글)
슬라이드는 강사 안내 0-10 순서(docs/기록/제출/최종발표_요구사항.md), 숫자는 10-08 최종 측정 그대로.
글은 짧게 두고 설명은 스크립트로 옮긴다(사용자 10-12 "텍스트는 적당히 간결하게 … 스크립트는 따로").
"""
import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tmp_slides"
SCRIPT_MD = ROOT / "docs/기록/제출/최종발표_스크립트_20261012.md"

INK, MUTED, RED, TEAL, GOLD = "#1B2433", "#5B6B7A", "#A2412F", "#2D6B5C", "#B8913F"
NIGHT, CARD, RED_TINT, TEAL_TINT, PAPER = "#0F1B2A", "#F1F2F4", "#F6E3DF", "#E4EFEB", "#FAFAFA"
HEAD, BODY = "Gowun Batang", "Noto Sans KR"
W, H = 10.0, 5.625

slides, extra, notes = [], [], []


def t(id_, x, y, w, h, text, size=16, **kw):
    if "\n" not in text:   # 한 줄 글은 위아래 여백까지 들어갈 최소 높이를 보장
        h = max(h, round(size * 1.2 / 72 + 0.22, 2))
    el = {"id": id_, "type": "text", "x": x, "y": y, "w": w, "h": h, "text": text, "size": size,
          "color": kw.pop("color", INK), "font": kw.pop("font", BODY)}
    el.update(kw)
    return el


def box(id_, x, y, w, h, fill, kind="round_rect", **kw):
    el = {"id": id_, "type": kind, "x": x, "y": y, "w": w, "h": h, "fill": fill}
    if "text" in kw:
        kw.setdefault("font", BODY)
    el.update(kw)
    return el


def content(n, title, label, els, note, bg=PAPER):
    """내용 장: 왼쪽 위 인주 도장(번호) + 제목. 도장은 앱의 '史錄' 도장에서 온 반복 모양."""
    sid = f"s{n:02d}_slide"
    head = [box(f"s{n:02d}_seal", 0.5, 0.4, 0.48, 0.48, RED, "rect", text=str(label), size=15, bold=True,
                color="#FFFFFF", font=HEAD, align="CENTER"),
            t(f"s{n:02d}_title", 1.05, 0.3, 8.45, 0.7, title, 26, bold=True, font=HEAD)]
    slides.append({"id": sid, "layout": "BLANK", "elements": head + els})
    extra.append(bg_req(sid, bg))
    notes.append((sid, title, note))
    return sid


def bg_req(sid, color):
    h = color.lstrip("#")
    rgb = {k: int(h[i:i + 2], 16) / 255 for k, i in (("red", 0), ("green", 2), ("blue", 4))}
    return {"updatePageProperties": {"objectId": sid, "pageProperties": {
        "pageBackgroundFill": {"solidFill": {"color": {"rgbColor": rgb}}}}, "fields": "pageBackgroundFill.solidFill.color"}}


def foot(n, text, y=5.0):
    return t(f"s{n:02d}_foot", 0.5, y, 9.0, 0.56, text, 10, color=MUTED)


# ---------- 0. 표지 ----------
slides.append({"id": "s00_slide", "layout": "BLANK", "elements": [
    box("s00_seal", 0.7, 1.2, 0.6, 0.6, RED, "rect", text="史", size=22, bold=True, color="#FFFFFF", font=HEAD, align="CENTER"),
    t("s00_title", 0.7, 1.95, 8.6, 1.0, "역사 취재록", 44, bold=True, color="#FFFFFF", font=HEAD),
    t("s00_sub", 0.7, 2.95, 8.6, 0.55, "조선왕조실록 원문으로 답하는 역사 인물 인터뷰 챗봇", 20, color="#E9DDC2"),
    t("s00_line", 0.7, 3.5, 8.6, 0.5, "실록에 적힌 것만 말하고, 없는 것은 없다고 합니다", 16, color="#B8C0CA"),
    t("s00_by", 0.7, 4.5, 6.0, 0.45, "이성빈 · 2026년 10월", 16, color=GOLD),
]})
extra.append(bg_req("s00_slide", NIGHT))
notes.append(("s00_slide", "표지", "안녕하세요, 이성빈입니다. 제가 만든 것은 '역사 취재록'입니다. 조선왕조실록 원문을 직접 번역한 자료로 답하는 챗봇이고, "
              "실록에 적힌 것만 말하고 없는 것은 없다고 하는 것을 목표로 했습니다. 결과물은 사건 속 인물을 취재하는 학습 서비스입니다."))

# ---------- 1. 문제 ----------
cols = [("누가", "한국사를 공부하는 학생, 한능검 수험생"),
        ("어떤 상황에서", "실록 속 사건과 인물을 AI에게 물어 공부할 때"),
        ("무엇이 곤란한가", "답이 기록인지 지어낸 말인지 구별할 수 없다")]
els = []
for i, (head, body) in enumerate(cols):
    x = 0.5 + i * 3.075
    els += [box(f"s01_card{i}", x, 1.35, 2.85, 2.5, CARD),
            box(f"s01_num{i}", x + 0.25, 1.6, 0.45, 0.45, TEAL, "ellipse", text=str(i + 1), size=16, bold=True, color="#FFFFFF", align="CENTER"),
            t(f"s01_head{i}", x + 0.2, 2.15, 2.45, 0.45, head, 17, bold=True, color=RED),
            t(f"s01_body{i}", x + 0.2, 2.6, 2.45, 1.15, body, 17)]
els += [box("s01_need", 0.5, 4.15, 9.0, 0.85, NIGHT, "rect", text="필요한 답: 실록에 있는 것만, 없으면 없다고, 근거 기사와 함께", size=18, bold=True, color="#FFFFFF")]
content(1, "AI가 답한 실록, 진짜인지 알 수 없다", 1, els,
        "한국사를 공부하는 학생이나 한능검 수험생이 실록 속 사건을 AI에게 물어 공부하는 경우를 생각했습니다. AI는 날짜, 숫자, 사람 이름까지 그럴듯하게 답합니다. "
        "그런데 그게 실록에 실제로 있는 말인지 확인할 방법이 없습니다. 원문은 한문이고, 번역문은 찾아서 하나하나 대조하기 어렵습니다. "
        "그래서 필요한 것은 실록에 있는 것만 말하고, 없으면 없다고 하고, 근거 기사를 바로 보여 주는 답이라고 봤습니다.")

# ---------- 2. GPT 빈손 사례 ----------
rows = [("《삼강행실도》 효자·충신·열녀는 각각 몇 명?", "각 35명", "각 110명"),
        ("숙종 때 금위영에 따로 둔 대장은 누구?", "신여철", "따로 두지 않음")]
els = []
for i, (q, gpt, real) in enumerate(rows):
    y = 1.3 + i * 1.85
    els += [box(f"s02_card{i}", 0.5, y, 5.7, 1.7, CARD),
            t(f"s02_q{i}", 0.7, y + 0.1, 5.3, 0.45, q, 15, color=MUTED),
            t(f"s02_gl{i}", 0.7, y + 0.55, 2.6, 0.38, "GPT 빈손", 14, bold=True, color=RED),
            t(f"s02_gv{i}", 0.7, y + 0.95, 2.6, 0.62, gpt, 24, bold=True, color=RED),
            t(f"s02_rl{i}", 3.35, y + 0.55, 2.75, 0.38, "실록 기록", 14, bold=True, color=TEAL),
            t(f"s02_rv{i}", 3.35, y + 0.95, 2.75, 0.62, real, 24, bold=True, color=TEAL)]
els += [box("s02_shot", 6.45, 1.3, 3.05, 3.55, "#E6E8EB", "rect", text="ChatGPT 화면 캡처\n(같은 조건으로 다시 물어 넣기)", size=14, color=MUTED, align="CENTER"),
        foot(2, "ChatGPT 무료(GPT-5.6 Luna, Think), 웹 검색 끔, 2026-10-08 · 실록: 세종 14년(1432) 6월 9일, 숙종 11년(1685) 7월 23일 기사")]
content(2, "GPT는 그럴듯하게 틀린다", 2, els,
        "실제 사례입니다. 10월 8일에 ChatGPT 무료판에 웹 검색을 끄고 물었습니다. 《삼강행실도》를 처음 엮을 때 효자·충신·열녀를 몇 명씩 골랐느냐고 물으면 '각 35명'이라고 답합니다. "
        "실록에는 각각 110명으로 나옵니다(세종 14년 6월 9일 기사). 두 번째는 함정 질문입니다. 숙종 때 금위영에 대장을 따로 두기로 했다던데 누구를 임명했냐고 물으면 '신여철'이라는 이름을 댑니다. "
        "실록에서는 대장을 따로 두지 않고 병조판서가 겸하게 했습니다. 질문 속 틀린 전제를 그대로 따라가서 이름을 지어낸 것입니다. 오른쪽 캡처는 같은 조건으로 다시 물어 받은 화면입니다.")

# ---------- 3. 데이터 ----------
stats = [("132건", "실록 기사"), ("803개", "번역한 조각"), ("4,512개", "쉬운 말 풀이")]
els = []
for i, (num, lab) in enumerate(stats):
    x = 0.5 + i * 3.075
    els += [box(f"s03_card{i}", x, 1.3, 2.85, 1.5, CARD),
            t(f"s03_num{i}", x, 1.42, 2.85, 0.78, num, 34, bold=True, color=RED, font=HEAD, align="CENTER"),
            t(f"s03_lab{i}", x, 2.2, 2.85, 0.45, lab, 16, color=MUTED, align="CENTER")]
els.append(t("s03_flowlab", 0.5, 3.0, 9.0, 0.4, "자르는 순서 · 뜻이 끊기는 곳은 사람이 경계를 정함", 14, bold=True, color=TEAL))
for i, step in enumerate(["기사", "문단", "말한 사람", "시점", "400자"]):
    els.append(box(f"s03_step{i}", 0.5 + i * 1.86, 3.42, 1.55, 0.55, TEAL_TINT, text=step, size=16, bold=True, color=TEAL, align="CENTER"))
els += [t("s03_meta", 0.5, 4.08, 9.0, 0.72, "조각마다 말한 사람과 그 일을 알게 된 날짜를 붙여, 인물이 모르는 미래 기사는 검색에서 뺀다", 15),
        foot(3, "출처: 국사편찬위원회 조선왕조실록 원문(공공누리 1유형) · 기사 선정: 한능검 심화 65-79회 조선 문항 주제 · "
                "번역: 한문 원문만 보고 직접(AI 초안, 일부 사람 검수), 국역은 쓰지 않음")]
content(3, "실록 원문을 직접 번역해 803조각으로", 3, els,
        "데이터는 국사편찬위원회의 조선왕조실록 원문입니다. 공공누리 1유형이라 자유롭게 쓸 수 있습니다. 기사는 한능검 심화 15회분의 조선 문항 148개를 주제별로 세어, "
        "자주 나온 주제의 기사 132건을 골랐습니다. 국역 번역문은 저작권이 있어 쓰지 않고, 한문 원문만 보고 직접 번역했습니다. AI가 초안을 쓰고 일부를 사람이 검수했습니다. "
        "기사를 문단, 말한 사람, 시점이 바뀌는 곳, 400자 순서로 잘라 803개 조각을 만들었고, 뜻이 끊기는 곳은 사람이 경계를 정했습니다. "
        "조각마다 말한 사람과 그 일을 알게 된 날짜를 붙였습니다. 인물과 대화할 때 그 인물이 아직 모르는 미래 기사를 검색에서 빼기 위해서입니다. "
        "또 강사님 의견에 따라 어려운 용어 4,512개에 쉬운 말 풀이를 붙였습니다.")

# ---------- 4. 평가셋 ----------
cards = [("개발 문항 · 고치는 데 씀", "67 + 50턴", "단발 질문 67개, 역할 대화 5장면 50턴\n비교용 20개는 홀드아웃과 같은 구성", CARD, TEAL),
         ("홀드아웃 · 봉인, 한 번만", "20문항", "9-30에 재료 봉인 → 10-08에 한 번 실행\n결과를 보고 문항·코드를 고치지 않음", RED_TINT, RED)]
els = []
for i, (lab, big, det, fill, col) in enumerate(cards):
    x = 0.5 + i * 4.65
    els += [box(f"s04_card{i}", x, 1.3, 4.35, 2.25, fill),
            t(f"s04_lab{i}", x + 0.25, 1.42, 3.9, 0.42, lab, 16, bold=True, color=col),
            t(f"s04_big{i}", x + 0.25, 1.85, 3.9, 0.72, big, 30, bold=True, font=HEAD),
            t(f"s04_det{i}", x + 0.25, 2.55, 3.9, 0.92, det, 14)]
els += [t("s04_traplab", 0.5, 3.72, 9.0, 0.4, "함정 문항 예시", 14, bold=True, color=RED),
        t("s04_trap0", 0.5, 4.1, 9.0, 0.45, "틀린 전제 · “금위영에 따로 둔 대장은 누구?” → 따로 둔 적 없음", 15),
        t("s04_trap1", 0.5, 4.55, 9.0, 0.45, "말한 사람 바꾸기 · “최만리가 말을 바꾼 것 아닙니까?” → 바꾼 사람은 김문", 15)]
content(4, "고치는 데 쓴 문항, 봉인한 문항", 4, els,
        "평가셋은 두 가지입니다. 개발 문항은 고치는 동안 계속 보면서 쓴 문항입니다. 단발 질문 67개와, 인물과 이어지는 역할 대화 5장면 50턴입니다. "
        "고치면서 본 문항이라 점수가 잘 나오는 게 당연하니, 따로 홀드아웃을 두었습니다. 9월 30일에 한능검 재료의 절반을 봉인해 두고, 고치는 동안 한 번도 쓰지 않은 그 절반으로 "
        "20문항을 만들어, 잠근 뒤 10월 8일에 딱 한 번 돌렸습니다. 결과를 보고 문항도 코드도 고치지 않았습니다. "
        "함정 문항을 예로 들면, '금위영에 따로 둔 대장은 누구냐'는 질문은 전제가 틀렸습니다. 따라가면 없는 사람을 지어내게 됩니다. "
        "역할 대화에서는 세종에게 '최만리가 말을 바꾼 것 아니냐'고 묻는데, 실제로 말을 바꾼 사람은 김문입니다. 맞장구치면 틀립니다.")

# ---------- 5. 숫자 표 ----------
els = [t("s05_lab1", 0.5, 1.15, 9.0, 0.38, "답 채점 · 부분 정답은 세지 않음", 14, bold=True, color=TEAL),
       {"id": "s05_tab1", "type": "table", "x": 0.5, "y": 1.52, "w": 9.0, "size": 14, "header": True,
        "rows": [["문항", "GPT 빈손 유료", "GPT 빈손 무료", "고치기 전", "고친 후"],
                 ["개발 단발 20 · AI 채점", "13/20", "10/20", "12/20", "20/20"],
                 ["개발 역할 대화 10 · AI 채점", "7/10", "5/10", "6/10", "10/10"],
                 ["홀드아웃 20 · 처음 보는 문항", "8/20 AI", "6/20 AI", "없음", "17/20 사람 · 18/20 AI"]],
        "col_widths": [2.75, 1.4, 1.4, 1.15, 2.3], "col_align": ["START", "END", "END", "END", "END"]},
       t("s05_lab2", 0.5, 3.28, 6.0, 0.38, "검색 적중 · 정답 조각이 최종 자료에 들었나", 14, bold=True, color=TEAL),
       {"id": "s05_tab2", "type": "table", "x": 0.5, "y": 3.7, "w": 5.4, "size": 14, "header": True,
        "rows": [["문항", "고치기 전", "고친 후"], ["개발 단발 17", "12/17", "17/17"], ["홀드아웃 17", "없음", "16/17"]],
        "col_widths": [2.6, 1.4, 1.4], "col_align": ["START", "END", "END"]},
       box("s05_note", 6.2, 3.7, 3.3, 1.1, CARD, text="고친 후 개발은 같은 설정 3회\n단발 20·20·20, 대화 10·10·9", size=14, color=INK),
       foot(5, "답변 모델: 고치기 전 gpt-4o-mini, 고친 후 gpt-6-luna · GPT 빈손: ChatGPT 웹 검색 끔(유료 GPT-6 Sol 생각 High, 무료 GPT-5.6 Luna Think) · "
               "AI 채점: Claude, 미리 합의한 기준표")]
content(5, "처음 보는 문항 8/20 → 17/20", 5, els,
        "결과입니다. 맨 아래 줄이 핵심입니다. 처음 보는 홀드아웃 20문항에서 ChatGPT 유료판은 웹 검색 없이 8개, 우리는 사람 채점으로 17개를 맞혔습니다. AI 채점으로는 18개입니다. "
        "부분 정답은 세지 않았습니다. 개발 문항은 고치기 전 12개에서 20개가 됐습니다. 다만 고치기 전과 후는 답변 모델이 다릅니다. 고치기 전은 gpt-4o-mini, 고친 후는 gpt-6-luna입니다. "
        "아래 표는 검색 단계만 따로 센 것입니다. 정답 조각이 최종 자료 안에 들어왔는지를 프로그램이 셌고, 개발 12/17에서 17/17, 홀드아웃은 16/17입니다.")
# 고친 후 열에 옅은 강조, 첫 열 굵게(표 1·2)
def tint(table, ncols_row, col, nrows, color):
    h = color.lstrip("#")
    rgb = {k: int(h[i:i + 2], 16) / 255 for k, i in (("red", 0), ("green", 2), ("blue", 4))}
    return {"updateTableCellProperties": {"objectId": table, "tableRange": {"location": {"rowIndex": 0, "columnIndex": col},
            "rowSpan": nrows, "columnSpan": 1}, "tableCellProperties": {"tableCellBackgroundFill": {"solidFill": {"color": {"rgbColor": rgb}}}},
            "fields": "tableCellBackgroundFill.solidFill.color"}}
def bold_cell(table, r, c):
    return {"updateTextStyle": {"objectId": table, "cellLocation": {"rowIndex": r, "columnIndex": c}, "textRange": {"type": "ALL"},
                                "style": {"bold": True}, "fields": "bold"}}
extra += [tint("s05_tab1", 5, 4, 4, RED_TINT), tint("s05_tab2", 3, 2, 3, RED_TINT)]
extra += [bold_cell("s05_tab1", r, 0) for r in range(1, 4)] + [bold_cell("s05_tab2", r, 0) for r in range(1, 3)]
extra += [bold_cell("s05_tab1", 3, 4)]

# ---------- 6. 가장 효과 컸던 변경 ----------
steps = [("문제", "검색이 낱말만 겹치는 조각을 가져와, 정답 조각이 상위 4개에 못 들었다"),
         ("바꾼 것", "검색 후보 20개를 모델이 다시 읽고, 질문에 맞는 4개를 고르게 했다"),
         ("결과", "통과 47 → 56 / 67, 검색 적중 44 → 54 / 56")]
els = []
for i, (head, body) in enumerate(steps):
    y = 1.3 + i * 1.22
    col = RED if i == 2 else TEAL
    els += [box(f"s06_num{i}", 0.5, y + 0.05, 0.45, 0.45, col, "ellipse", text=str(i + 1), size=16, bold=True, color="#FFFFFF", align="CENTER"),
            t(f"s06_head{i}", 1.1, y, 4.2, 0.4, head, 17, bold=True, color=col),
            t(f"s06_body{i}", 1.1, y + 0.38, 4.2, 0.8, body, 15)]
base, scale = 4.4, 2.8 / 67
for i, (val, lab, fill) in enumerate([(47, "리랭커 없음", "#9AA3AD"), (56, "리랭커 추가", RED)]):
    x, hgt = 6.3 + i * 1.65, val * scale
    els += [box(f"s06_bar{i}", x, base - hgt, 1.15, hgt, fill, "rect"),
            t(f"s06_val{i}", x - 0.2, base - hgt - 0.6, 1.55, 0.58, str(val), 22, bold=True, color=fill if i else INK, align="CENTER"),
            t(f"s06_cat{i}", x - 0.3, base + 0.05, 1.75, 0.4, lab, 14, align="CENTER")]
els += [t("s06_charttitle", 5.9, 1.15, 3.6, 0.4, "단발 67문항 중 통과", 14, bold=True, color=MUTED, align="CENTER"),
        foot(6, "2026-09-29, 같은 67문항·같은 답변 모델(gpt-4o-mini)로 이것 하나만 바꿈 · 통과: AI(Claude) 채점, 적중: 프로그램 · 이후의 변경은 여러 개를 함께 바꿈")]
content(6, "리랭커 하나로 47 → 56", 6, els,
        "가장 효과가 컸던 변경은 리랭커입니다. 문제는 검색이 질문과 낱말만 겹치는 조각을 가져와서, 정답 조각이 최종 자료 4개 안에 못 드는 것이었습니다. "
        "그래서 검색 후보 20개를 모델이 다시 읽고 질문에 맞는 4개를 고르게 했습니다. 같은 67문항, 같은 답변 모델로 이것 하나만 바꿨을 때 통과가 47개에서 56개로, "
        "검색 적중이 44에서 54로 올랐습니다. 그 뒤의 변경, 즉 답변 모델 교체와 최종 자료 6개, 전제 판정은 여러 개를 한꺼번에 바꿔서 하나씩의 효과는 말씀드리지 않겠습니다.")

# ---------- 7. 아직 틀리는 것 ----------
fails = [("영조가 결전 방안을 물었을 때, 선비·아전·군사의 반응은?",
          "물어본 장면 조각만 찾음", "“대답은 기록에 없다”", "대답 조각에 질문 낱말이 없음"),
         ("관리들이 세금을 지나치게 걷자 어떻게 바꿨나?",
          "세종 공법 기사(정답: 성종)", "공법으로 설명(다른 사건)", "비슷한 시대 기사가 더 가까움")]
els = []
for i, (q, got, ans, why) in enumerate(fails):
    x = 0.5 + i * 4.65
    els += [box(f"s07_card{i}", x, 1.25, 4.35, 3.65, CARD),
            t(f"s07_q{i}", x + 0.2, 1.35, 3.95, 0.78, q, 16, bold=True)]
    for j, (lab, body, col) in enumerate([("가져온 조각", got, TEAL), ("답", ans, INK), ("틀린 이유(추정)", why, RED)]):
        y = 2.18 + j * 0.92
        els += [t(f"s07_l{i}{j}", x + 0.2, y, 3.95, 0.35, lab, 14, bold=True, color=col),
                t(f"s07_b{i}{j}", x + 0.2, y + 0.38, 3.95, 0.5, body, 15)]
els.append(foot(7, "홀드아웃 오답 2개 모두 이름을 뺀 질문이고 둘 다 검색 단계에서 놓침, 받은 자료 밖 사실을 지어내지는 않음 · 사람 채점: 정답 17, 부분 2, 오답 1"))
content(7, "아직 약한 곳: 이름을 뺀 질문", 7, els,
        "아직 틀리는 것입니다. 홀드아웃에서 틀린 두 문항은 모두 이름을 빼고 단서만 준 질문이었고, 둘 다 검색 단계에서 놓쳤습니다. "
        "첫째는 영조가 토지에 돈을 매기는 결전 방안을 두고 지방 선비·아전·군사에게 물은 장면입니다. 물어본 장면 조각은 찾았지만 사람들이 대답한 바로 뒤 조각은 못 찾아서 "
        "'대답은 기록에 없다'고 했습니다. 대답 조각에는 '결전', '군포' 같은 질문 낱말이 없고 사람들 말만 있어서 검색이 멀었다고 봅니다. "
        "둘째는 관리들이 세금을 지나치게 거두자 어떻게 바꿨냐는 질문입니다. 정답은 성종 때 관수관급인데, 단서가 세종 때 공법 기사와 더 가까워 공법으로 답했습니다. "
        "같은 질문에 ChatGPT도 공법으로 답했습니다. 두 경우 모두 받은 자료 밖의 사실을 지어내지는 않았습니다.")

# ---------- 8. 한계와 발전 방향 ----------
els = [{"id": "s08_tab", "type": "table", "x": 0.5, "y": 1.3, "w": 9.0, "size": 16, "header": True,
        "rows": [["한계", "다음에 할 것"],
                 ["이름을 뺀 질문은 3개 중 1개만 맞힘", "같은 기사의 앞뒤 조각을 후보에 보태고, 검색용으로 질문을 사건 이름 중심으로 바꿔 쓰기"],
                 ["답 하나에 10-20초", "검색·자료 고르기·답 쓰기 단계별 시간을 재고 줄일 곳 찾기"],
                 ["실록 기사 132건, 번역은 일부만 사람 검수", "번역을 보완한 뒤 다시 측정하고, 사건 늘리기"]],
        "col_widths": [3.4, 5.6], "row_h": 0.78},
       foot(8, "오른쪽 열은 아직 하지 않은, 다음에 할 일")]
extra += [bold_cell("s08_tab", r, 0) for r in range(1, 4)]
content(8, "한계와 다음에 할 것", 8, els,
        "한계는 세 가지입니다. 첫째, 이름을 빼면 약합니다. 홀드아웃에서 이름을 뺀 질문은 3개 중 1개만 맞혔습니다. 다음에는 정답 조각 하나를 찾으면 같은 기사의 앞뒤 조각을 함께 후보에 넣고, "
        "단서만 있는 질문은 검색용으로 사건 이름 중심으로 바꿔 쓰려고 합니다. 둘째, 답이 느립니다. 질문 하나에 10초에서 20초가 걸립니다. 단계별 시간을 재서 줄일 곳을 찾겠습니다. "
        "셋째, 자료가 실록 기사 132건뿐이고 번역은 일부만 사람이 검수했습니다. 번역을 보완한 뒤 다시 측정하고 사건을 늘리려고 합니다. 오른쪽은 모두 아직 하지 않은, 다음에 할 일입니다.")

# ---------- 9. 시연 ----------
qs = [("잘 되는 질문", "《삼강행실도》 효자·충신·열녀는 각각 몇 명?"),
      ("함정 질문", "숙종 때 금위영에 따로 둔 대장은 누구?"),
      ("모르는 걸 모른다고", "통신사 기록물이 세계기록유산이 된 해는?")]
els = []
for i, (tag, q) in enumerate(qs):
    y = 1.3 + i * 1.22
    els += [box(f"s09_card{i}", 0.5, y, 4.6, 1.12, CARD),
            t(f"s09_tag{i}", 0.7, y + 0.04, 4.2, 0.36, tag, 14, bold=True, color=RED),
            t(f"s09_q{i}", 0.7, y + 0.4, 4.2, 0.7, q, 15)]
els += [box("s09_video", 5.4, 1.3, 4.1, 3.56, NIGHT, "rect", text="시연 녹화본\n실록에 묻기 → 인물 취재", size=16, color="#FFFFFF", align="CENTER"),
        foot(9, "세 질문 모두 홀드아웃 문항(측정 때 사람·AI 모두 정답) · 인물 취재의 말투와 추천 질문은 측정하지 않은 서비스 기능")]
content(9, "시연: 실록에 묻기와 인물 취재", 9, els,
        "시연입니다. 세 질문 모두 홀드아웃 문항입니다. 첫째는 잘 되는 질문, 둘째는 틀린 전제가 든 함정 질문, 셋째는 실록에 없는 걸 묻는 질문입니다. "
        "셋째는 GPT가 알고 우리가 모르는 게 아니라, 실록 밖의 현대 사실은 지어내지 않는다는 걸 보여 드리는 것입니다. (녹화본 재생: 실록에 묻기 세 질문) "
        "이어서 결과물인 역사 취재록입니다. 강사님이 추천하신 『한국사 이상현상 연구원』의 형식을 참고해, 기자가 사건 속 인물을 취재하는 방식으로 만들었습니다. "
        "화면은 계유정난 날 밤의 수양대군과 권람을 인터뷰하는 장면입니다. 인물은 그 시점까지만 알고, 근거로 확인된 내용만 취재 수첩에 쌓입니다. "
        "인물의 말투나 추천 질문은 측정한 적이 없는 서비스 기능이라, 성능 숫자는 앞의 표로만 말씀드립니다.")

# ---------- 10. 마무리 ----------
nums = [("① 왜 필요한가", "8/20 → 17/20", "처음 보는 홀드아웃 20문항, GPT 빈손(유료) 대 우리(사람 채점)"),
        ("② 무엇을 했나", "47 → 56/67", "리랭커 하나만 추가, 같은 단발 67문항·같은 답변 모델"),
        ("③ 남은 한계", "1/3", "이름을 빼고 단서만 준 질문, 홀드아웃에서 3개 중 1개")]
els = [t("s10_title", 0.7, 0.45, 8.6, 0.75, "발표 숫자 세 개", 30, bold=True, color="#FFFFFF", font=HEAD)]
for i, (head, num, desc) in enumerate(nums):
    x = 0.5 + i * 3.075
    els += [box(f"s10_card{i}", x, 1.45, 2.85, 3.15, "#1B2A3D"),
            t(f"s10_head{i}", x + 0.2, 1.6, 2.45, 0.42, head, 15, bold=True, color=GOLD),
            t(f"s10_num{i}", x, 2.15, 2.85, 0.8, num, 26, bold=True, color="#FFFFFF", font=HEAD, align="CENTER"),
            t(f"s10_desc{i}", x + 0.2, 3.1, 2.45, 1.4, desc, 14, color="#E9DDC2")]
els.append(t("s10_tag", 0.7, 4.85, 8.6, 0.45, "실록에 적힌 것만 말하는 역사 챗봇 · 역사 취재록", 14, color=GOLD))
slides.append({"id": "s10_slide", "layout": "BLANK", "elements": els})
extra.append(bg_req("s10_slide", NIGHT))
notes.append(("s10_slide", "마무리", "정리하면 숫자 세 개입니다. 첫째, 처음 보는 문항에서 GPT 빈손은 8/20, 우리는 17/20입니다. 둘째, 가장 효과가 컸던 리랭커 하나로 47에서 56이 됐습니다. "
              "셋째, 아직 이름을 빼고 단서만 준 질문은 3개 중 1개만 맞힙니다. 감사합니다."))

QA = [("고치기 전과 후의 답변 모델이 다른데 비교가 공정한가요?",
       "숫자 표에 모델 차이를 밝혔습니다. '가장 효과 컸던 변경'인 리랭커는 같은 모델(gpt-4o-mini), 같은 67문항에서 이것 하나만 바꿔 쟀습니다. 모델 교체 효과는 따로 56 → 61/67이었습니다(09-29)."),
      ("AI(Claude)가 채점하면 후하지 않나요?",
       "홀드아웃은 사람(발표자)이 AI 판정을 가린 채 따로 채점했고, 처음 판정이 18/20 일치했습니다. 기준표는 측정 전에 사람 채점과 비교해 맞춘 것입니다(10-02 비교 때는 AI가 더 엄했음)."),
      ("ChatGPT에 웹 검색을 켜면요?",
       "홀드아웃에서 유료 18/20, 무료 17/20(AI 채점)이었습니다. 실록 사이트의 원문과 저작권 있는 국역을 검색해 인용했습니다. 우리는 웹 없이, 한문 원문을 직접 번역한 자료만 쓰고, 인물의 시점을 지킵니다."),
      ("왜 실록 전체가 아니라 132건인가요?",
       "한능검 심화 15회분에 나온 조선 주제를 기준으로 골랐습니다. 직접 번역·검수해야 해서 범위를 좁혔고, 사건을 늘리는 것은 다음 할 일입니다."),
      ("번역은 믿을 만한가요?",
       "AI 초안에 일부 사람 검수입니다. 무작위 조각 검사와 인명·용어 대조를 했지만 전부 사람이 본 것은 아닙니다. 그래서 근거 보기에서 한문 원문과 국편 원문 링크를 함께 보여 줍니다."),
      ("인물이 미래를 말하지 않나요?",
       "역할 대화 측정에서 미래 정보 누설은 150턴 중 0건이었습니다(이번 측정 범위). 조각마다 '알게 된 날짜'를 붙여 그 뒤 기사는 검색에서 뺍니다."),
      ("김종서는 정승이 맞나요?",
       "1453년 김종서는 좌의정이었습니다. 실록 기사에서도 수양대군이 그를 '정승'이라 부릅니다. '좌의정'이라는 벼슬 이름은 우리 자료 조각에 직접 나오지 않습니다."),
      ("시연의 인물 취재 화면도 측정했나요?",
       "아니요. 인물별 자료 제한, 말투, 추천 질문은 측정하지 않은 서비스 기능입니다. 측정 숫자는 '실록에 묻기'와 같은 설정의 결과입니다.")]


def fit_check():
    """한글은 글자 크기만큼, 영문·숫자는 약 0.55배 폭으로 세어 칸을 넘칠지 본다(slides_helper 추정은 영문 기준이라 한글을 덜 셈)."""
    bad = []
    for s in slides:
        for el in s["elements"]:
            if el.get("type") == "table" or not el.get("text"):
                continue
            size, usable = el["size"], (el["w"] - 0.2) * 72
            lines = 0
            for para in el["text"].split("\n"):
                width = sum(size * (1.0 if unicodedata.east_asian_width(c) in "WF" else 0.55) for c in para)
                lines += max(1, -(-int(width) // int(usable)))
            need = (lines * size * 1.2) / 72 + 0.2
            if need > el["h"] + 0.04:
                bad.append(f"{el['id']}: 약 {need:.2f}in 필요, 칸 {el['h']:.2f}in · {el['text'][:24]!r}")
    for s_ in slides:
        for el in s_["elements"]:
            if el.get("type") != "table" and not el["id"].endswith("_foot") and el["y"] + el["h"] > 5.0 and s_["id"] not in ("s00_slide", "s10_slide"):
                bad.append(f"{el['id']}: 아래 끝 {el['y'] + el['h']:.2f}in 이 각주 줄(5.0in)에 닿음")
    return bad


def write_script():
    lines = ["# 최종 발표 스크립트 (2026-10-12)", "",
             "구글 슬라이드 '역사 취재록 최종 발표_이성빈'과 짝입니다. 장마다 할 말이며, 같은 글이 발표자 노트에도 들어 있습니다.",
             "숫자는 10-08 최종 측정 그대로입니다(HANDOFF '10-08 최종 측정 결과'). 생성: `scripts/final_slides.py`(작업기록 [407]).", ""]
    for i, (_, title, note) in enumerate(notes):
        lines += [f"## {i}. {title}", "", note, ""]
    lines += ["## 예상 질문과 답", ""]
    for q, a in QA:
        lines += [f"**Q. {q}**", "", a, ""]
    SCRIPT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "spec.json").write_text(json.dumps({"slides": slides}, ensure_ascii=False), encoding="utf-8")
    (OUT / "extra.json").write_text(json.dumps(extra, ensure_ascii=False), encoding="utf-8")
    (OUT / "notes.json").write_text(json.dumps(notes, ensure_ascii=False), encoding="utf-8")
    write_script()
    problems = fit_check()
    print("\n".join(problems) or "한글 기준 넘침 추정 0곳")
    print(f"슬라이드 {len(slides)}장, 추가 요청 {len(extra)}개, 스크립트 {SCRIPT_MD.name}")
