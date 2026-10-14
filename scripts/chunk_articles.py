"""정제·청킹 규칙서(docs/정제청킹_규칙서.md)대로 기사를 정제하고 청크로 자른다 (2026-09-29, v2 2026-09-30).

사용법:
    python scripts/chunk_articles.py --tag <새 이름>

- 입력은 data/raw_xml/{기사ID}.xml(extract_articles.py가 원문 ZIP에서 잘라 둔 기사 원본)이다.
  예전에는 원문 ZIP을 직접 읽었으나, raw_xml 132건만으로 결과가 한 글자도 같아서 2026-09-30에 바꿨다(작업기록 [136]).
  그래서 청크를 다시 나눌 때 원문 ZIP이 필요 없다(ZIP은 기사를 새로 뽑을 때만 필요).

- 기사는 data/articles.jsonl(extract_articles.py가 고른 기사 목록 순서대로 뽑은 132건)의 순서대로 처리한다. 순서에 뜻은 없지만 코퍼스 줄 순서가 BM25 동점(0점) 청크의
  순위를 정해 검색 결과에 영향을 주므로 함부로 바꾸지 않는다(새 기사는 끝에 더함, 작업기록 [139]).
- 지금 쓰는 결과는 규칙서 v2로 --tag 20260930_v2 로 낸 것이다(기본값이라 그대로 실행하면 멈춘다).
  v1b(2026-09-29, 793청크) 결과는 archive/새코퍼스_1-4차_793청크/청크_v1b/ 에 있다.
- 번역은 하지 않는다. 한문 원문(공공누리 1유형)만 다룬다.

출력 (이미 있으면 덮어쓰지 않고 멈춘다):
    data/청크초안_{TAG}.jsonl            규칙대로 나눈 청크 (원문 + 메타데이터 + 머리말). 다음 단계(번역·코퍼스)가 읽는 유일한 파일
    docs/기록/데이터가공/청크통계_{TAG}.csv     전체·실록별·화자 종류별 청크 수와 길이
    docs/기록/데이터가공/정제기록_{TAG}.csv     기사마다 정제 규칙이 몇 번 적용됐는지
    docs/기록/데이터가공/수동검사표_{TAG}.csv   무작위 25개 청크. 판정 칸은 비워 두고 사람이(또는 AI 가판정 후 사람이) 채운다
    (확인용 기록 3개는 코드가 읽지 않아 docs/기록/데이터가공/로 옮김, 청크초안은 data/ 바로 아래로. 작업기록 [137]-[138])
    (지금 쓰는 수동검사표는 v2 것. 사람 확인까지 끝남)

지금 sillok_rag/ 코드와 data/corpus.jsonl은 건드리지 않는다(만들 당시 파일럿 실험이 사용 중이었음).
"""
from __future__ import annotations

import csv
import json
import math
import random
import re
import statistics
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data"   # 다음 단계가 읽는 청크초안만 data/에 둔다(data/에는 코드가 읽는 파일만, 작업기록 [138])
RAW = ROOT / "data" / "raw_xml"
REC = ROOT / "docs" / "기록" / "데이터가공"   # 청킹이 잘됐는지 사람이 보는 기록(통계·정제 횟수·수동 검사표)
TAG = "20260930_v2"  # 결과 파일 이름. 규칙이나 기사 목록을 바꿔 다시 낼 때는 --tag 로 새 이름을 준다


def take_tag(argv: list[str]) -> list[str]:
    """argv에서 '--tag 이름'을 빼내 TAG에 넣고 나머지를 돌려준다."""
    global TAG
    if "--tag" in argv:
        i = argv.index("--tag")
        TAG = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    return argv

MAX_LEN = 400  # 한 청크의 최대 글자 수(공백 제외 한자). 넘으면 문장 경계에서 나눈다
SEED, N_CHECK = 20260929, 25  # 수동 검사표 표본
MIN_LEN = 30   # 이보다 짧은 조각은 이웃 청크에 붙인다(인용 단위·기사 전체는 예외)

# ---------------------------------------------------------------- 정제 규칙 (규칙서 3장)

# XML 1.0에서 허용되지 않는 제어 문자 참조. 일부 권에 들어 있어 그대로는 읽히지 않는다.
BAD_CHAR_REF = re.compile(r"&#(?:x0*(?:[0-8bcef]|1[0-9a-f])|0*(?:[0-8]|1[124-9]|2[0-9]|3[01]));", re.I)
# 확장 한자가 UTF-16 반쪽 두 개(&#55381;&#56892;)로 적힌 경우. 한 글자로 합쳐야 읽힌다.
SURROGATE_PAIR = re.compile(r"&#(5[5-6]\d{3});&#(5[6-7]\d{3});")
# 확장 한자가 '&#x25447;' 글자 그대로 본문에 남은 경우(이중 이스케이프)
LITERAL_REF = re.compile(r"&#x([0-9A-Fa-f]{4,6});")
# 교감주: (틀린 글자)〔바로잡은 글자〕 → 바로잡은 글자, 단독 〔글자〕(빠진 글자 보충) → 글자
CORRECTION_PAIR = re.compile(r"\(([^()〔〕]{1,10})\)\s*〔([^〔〕]{1,10})〕")
CORRECTION_ADD = re.compile(r"〔([^〔〕]{1,10})〕")
DAY_GANJI = re.compile(r"^朔?([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])/")
VOLUME_END = re.compile(r"實錄卷第.*終$|日記卷第.*終$")

KINGS = {
    "太祖": "태조", "定宗": "정종", "太宗": "태종", "世宗": "세종", "文宗": "문종", "端宗": "단종",
    "世祖": "세조", "睿宗": "예종", "成宗": "성종", "燕山君": "연산군", "中宗": "중종", "仁宗": "인종",
    "明宗": "명종", "宣祖": "선조", "宣祖修正": "선조(수정실록)", "光海君": "광해군", "仁祖": "인조",
    "孝宗": "효종", "顯宗": "현종", "顯宗改修": "현종(개수실록)", "肅宗": "숙종", "景宗": "경종",
    "英祖": "영조", "正祖": "정조", "純祖": "순조", "憲宗": "헌종", "哲宗": "철종",
}

# 기록 날짜와 사건 시점이 어긋날 수 있다는 신호 단어 (규칙서 4-4)
# 조각이 이 말로 시작하면 시점이 바뀐 것이므로 앞 조각에 붙이지 않는다
TIME_SHIFT_START = ("初,", "翌日", "明日", "是後", "其後", "後日", "至是", "先是", "前此")
# v2: 서술 속에서 문장이 날짜로 시작하면(初八日, 七月初六日, 二十九日 …) 그 날의 일로 넘어간 것이므로 끊는다 (규칙서 v2 ㉑)
NUM = "一二三四五六七八九十廿"
#   달이 없는 '一日'은 '하루는'이라는 뜻이 많아 뺀다(一日, 成宗試令…)
DATE_START = re.compile(rf"(?:是年)?(?:[{NUM}]{{1,2}}月|(?!一日))(?:初[{NUM}]|[{NUM}]{{1,3}})日(?:[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])?[,， ]")
# v2: 권 끝 표시가 문단 끝에 붙어 남는 경우(…不得。 燕山君日記卷第六十三) (규칙서 8장 ⑫)
VOLUME_END_TAIL = re.compile(r"\s*\S{2,8}(?:實錄|日記)卷第[一二三四五六七八九十百]+終?$")
# v2: 사람이 정한 경계 (규칙서 v2 ㉒). 규칙으로 잡기 어려운 곳을 2026-09-30 사람 검수 결과로 정했다.
#   join: 이 말로 시작하는 청크는 앞 청크에 붙인다 / cut: 이 말 바로 앞에서 끊는다 (join을 먼저 한다)
MANUAL = {
    "wfa_10110010_001": {"join": ["世祖還入後園"], "cut": ["擥見連城曰"]},        # 세조가 후원으로 들어간 데까지 앞, 권람·곽연성 문답부터 뒤
    "wma_10209018_003": {"cut": ["俄而三公至"], "join": ["都承旨趙彦秀以三公意啓曰"]},  # 삼공이 이른 것은 다음 장면의 도입
    "wna_12602024_001": {"join": ["景禧曰: \"李洸至今不誅", "景禧曰: \"洸之素行貪汚"],
                         "cut": ["上曰: \"此處或有敍用之議"]},                        # 선조의 질문과 신경희의 답을 짝으로
    "wpa_11501030_002": {"join": ["都承旨李景稷對曰"], "cut": ["良久, 龍胡等至"]},     # 이경직의 대답은 앞 질문과, 용골대 도착부터 뒤
    "wsa_11506003_002": {"join": ["遂從容就盡"], "cut": ["時烈, 恩津人", "自珥世"]},     # 사사 장면 끝 / 졸기 시작 / 학통·당파 평가
    "wua_12607003_001": {"join": ["當以魚鹽及守令私用"],                             # 이보혁의 말이 길이로 잘린 곳(검사표 v2 10번)
                         "cut": ["上命坊民入陳所懷", "上命百官入陳"]},                 # 유생 / 방민 / 백관 장면
    "wva_10009025_002": {"cut": ["召見大臣、吏曹堂上、玉堂"]},                        # 규장각 배치 설명 / 정조 문답 도입
    "waa_10708026_001": {"cut": ["李茂素有中立之計"]},                               # 당일 일 / 이무가 전에 제보한 일
    "waa_10409029_006": {"cut": ["後築宮城"]},                                     # 1395년 준공 / 뒷날 쌓은 궁성·문 이름
    "wnb_12504014_001": {"cut": ["甲午兵使金應瑞"]},                                 # 1592년 동래성 / 1594년 뒷날 일
    "wnb_10205001_001": {"cut": ["【李滉答李楨書"]},                                 # 기사 당일 / 원주의 뒷날 평가
    "wda_12809029_004": {"join": ["ㅎ喉音"], "cut": ["ㄱ牙音"]},                  # 어제 서문 / 자모 설명(파일럿 c19·c20, 8장 ⑧)
}
# 화자 추정용: 왕실 인물과 관청 (앞의 것부터 찾는다)
ROYALS = [("大王大妃", "대왕대비"), ("王大妃", "왕대비"), ("大妃", "대비"), ("中宮", "중궁"), ("中殿", "중전"),
          ("世子", "세자"), ("東宮", "동궁(세자)")]
OFFICES = [("備邊司", "비변사"), ("備局", "비변사"), ("承政院", "승정원"), ("政院", "승정원"), ("議政府", "의정부"),
           ("政府", "의정부"), ("司憲府", "사헌부"), ("憲府", "사헌부"), ("司諫院", "사간원"), ("諫院", "사간원"),
           ("弘文館", "홍문관"), ("玉堂", "홍문관"), ("兩司", "양사(사헌부·사간원)"), ("臺諫", "대간"),
           ("義禁府", "의금부"), ("吏曹", "이조"), ("戶曹", "호조"), ("禮曹", "예조"), ("兵曹", "병조"),
           ("刑曹", "형조"), ("工曹", "공조"), ("六曹", "육조"), ("春秋館", "춘추관"), ("集賢殿", "집현전"),
           ("成均館", "성균관"), ("館學", "성균관·사학 유생"), ("儒生", "유생"), ("都堂", "도당"), ("百官", "백관"),
           ("大臣", "대신들"), ("諸將", "장수들")]
TIME_WORDS = ["翌日", "明日", "前此", "先是", "初,", "至是", "是後", "其後", "後日", "旣而", "已而", "是月", "是歲", "今年", "去年", "前日"]


def load_article(aid: str) -> ET.Element:
    """data/raw_xml/{기사ID}.xml을 읽는다. 원문 ZIP의 권 파일을 읽던 때와 같은 정리를 거친다."""
    path = RAW / f"{aid}.xml"
    if not path.exists():
        raise SystemExit(f"기사 원본이 없음: {path.relative_to(ROOT)} — extract_articles.py로 먼저 뽑으세요")
    raw = path.read_text(encoding="utf-8", errors="replace")
    raw = re.sub(r"<!DOCTYPE[^>]*>", "", raw)  # DTD 선언 줄 제거 (ElementTree가 외부 DTD를 못 읽음)
    raw = SURROGATE_PAIR.sub(
        lambda m: f"&#x{(0x10000 + ((int(m[1]) - 0xD800) << 10) + (int(m[2]) - 0xDC00)):X};", raw
    )
    return ET.fromstring(BAD_CHAR_REF.sub("", raw))


class Flattener:
    """기사 XML을 문단별 글자로 펴면서, 무엇을 어떻게 처리했는지 센다."""

    def __init__(self) -> None:
        self.count: Counter = Counter()
        self.index: dict[str, list[str]] = {"이름": [], "지명": [], "서명": [], "연호": []}
        self.sanlon: list[str] = []  # 사론(史論) 문단: 본문과 따로 모은다

    def text(self, el: ET.Element) -> str:
        out = [el.text or ""]
        for ch in el:
            out.append(self.child(ch))
            out.append(ch.tail or "")
        return "".join(out)

    def child(self, el: ET.Element) -> str:
        tag = el.tag
        if tag == "index":
            t = self.text(el)
            kind = el.get("type")
            if kind in self.index and t not in self.index[kind]:
                self.index[kind].append(t)
            return t
        if tag == "annotation":
            kind = el.get("type")
            self.count[f"주석:{kind}"] += 1
            if kind in ("원주", "소자쌍행"):  # 편찬자가 단 작은 글씨 주. 원문의 일부라 【】째 남긴다
                return self.text(el.find("noteContent")) if el.find("noteContent") is not None else ""
            if kind == "교감주":  # 〔바로잡은 글자〕. 앞의 (틀린 글자)와 함께 clean()에서 처리
                title = el.find("noteTitle")
                return title.text or "" if title is not None else ""
            return ""  # 번역주·악보 등: 원문이 아니므로 뺀다
        if tag == "newChar":  # 유니코드에 없는 글자(이미지로만 있음)
            self.count["없는글자□"] += 1
            return "□"
        if tag in ("illustration", "image", "caption"):
            self.count["그림"] += 1
            return ""
        if tag == "postScript":
            for p in el.iter("paragraph"):
                self.sanlon.append(self.text(p))
            self.count["사론"] += 1
            return ""
        if tag == "proofreading":
            self.count[f"교정표시:{el.get('type')}"] += 1
        return self.text(el)  # quotation, noteContent, 모르는 태그 등은 글자만


def clean(s: str, count: Counter) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    s, n = LITERAL_REF.subn(lambda m: chr(int(m[1], 16)), s)
    count["확장한자복원"] += n
    s, n = CORRECTION_PAIR.subn(r"\2", s)
    count["교감:바꿈"] += n
    s, n = CORRECTION_ADD.subn(r"\1", s)
    count["교감:보충"] += n
    return s


# ---------------------------------------------------------------- 화자·인용 나누기 (규칙서 4장)

SPEECH = re.compile(r"(曰|議|啓|言)\s*[:：]")


def quote_depths(s: str, depth0: int = 0) -> list[int]:
    """글자마다 따옴표 깊이. " 는 여닫이가 같아 토글, ‘’「」는 쌍으로 센다."""
    d, inner, out = depth0, 0, []
    for ch in s:
        if ch == '"':
            d = 0 if d else 1
            out.append(1)
            continue
        if ch in "‘「":
            inner += 1
        out.append(d + inner if d or inner else 0)
        if ch in "’」":
            inner = max(0, inner - 1)
    return out


def bracket_spans(s: str) -> list[tuple[int, int]]:
    """편찬자 주석 【…】의 (시작, 끝) 위치. v2: 이 안에서는 끊지 않는다 (규칙서 8장 ④)."""
    spans, start = [], None
    for i, ch in enumerate(s):
        if ch == "【" and start is None:
            start = i
        elif ch == "】" and start is not None:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(s) - 1))
    return spans


def in_bracket(spans: list[tuple[int, int]], pos: int) -> tuple[int, int] | None:
    return next(((a, b) for a, b in spans if a < pos <= b), None)


def at_sentence_start(s: str, pos: int) -> bool:
    """pos가 문장 첫머리인가(앞의 공백을 건너 문장 끝 。?! 이나 닫는 따옴표·주석이 바로 앞). v2: 쉼표 뒤는 아님 (규칙서 8장 ⑭)."""
    j = pos - 1
    while j >= 0 and s[j] == " ":
        j -= 1
    return j < 0 or s[j] in "。?!\"”’」】"


def clause_start(s: str, pos: int, depths: list[int], level: int) -> int:
    """pos(曰)가 속한 구절의 시작. 같은 깊이의 문장 끝(。?!) 또는 따옴표 바로 뒤."""
    i = pos - 1
    while i >= 0:
        ch = s[i]
        if depths[i] == level and ch in "。?!":
            return i + 1
        if depths[i] < level or (level == 0 and ch == '"') or (level == 1 and ch in "’」"):
            return i + 1
        i -= 1
    return 0


def speaker_of(clause: str, persons: list[str], king: str) -> tuple[str, str]:
    """구절에서 화자와 화자 종류를 추정한다. (화자, 종류)"""
    c = re.sub(r"^[\s○/,]+", "", clause)
    if "史臣" in c:
        return "사관", "사론"
    who = [p for p in persons if p in c]
    who = [w for w in who if not any(w != o and w in o for o in who)]  # 崔萬理가 있으면 萬理는 뺀다
    if re.search(r"上疏|上書|上箚|封疏|陳疏|箚曰|疏曰|交章", c):
        return ("·".join(who[:2]) + ("등" if "等" in c else "")) or c[:12], "상소"
    for hanja, name in ROYALS:
        if hanja in c:
            return name, "왕실"
    if re.match(r"(上|王|傳|敎|御)", c) or re.search(r"(^|[,。 ])上(曰|敎|謂|問|答|召|覽|命)|傳曰|傳于|敎曰|(敎|傳)$", c) \
            or re.search(r"備忘記|綸音|敎旨|下敎|^批", c):
        return king, "임금"
    if who:
        return "·".join(who[:2]) + ("등" if "等" in c else ""), "신하"
    for hanja, name in OFFICES:
        if hanja in c:
            return name, "관청"
    c = re.sub(r"(曰|議|啓|言)\s*[:：]?$", "", c).strip()
    if re.fullmatch(r"(又|且|其|若|又敎|又啓|又對|對|答|其[一二三四五]|其別幅|別幅)?", c):
        return "", "이어서"  # '又曰' 등: 바로 앞 화자가 이어 말함 (호출한 쪽에서 채움)
    return c[-12:] or "?", "기타(확인필요)"


def split_speech_quotes(seg: str, persons: list[str]) -> list[tuple[str, list[str]]]:
    """한 발언 안에 다른 사람 말 인용(X曰: ‘…’)이 2개 이상이면 인용 단위로 쪼갠다.
    한 조각 = (인용 소개 + 인용 + 그 인용에 대한 화자의 말). 첫 조각은 앞말(上曰: " 등)을 함께 가진다."""
    depths = quote_depths(seg)
    starts = []
    for m in SPEECH.finditer(seg):
        j = m.end()
        while j < len(seg) and seg[j] == " ":
            j += 1
        if j < len(seg) and seg[j] in "‘「" and depths[m.start()] == 1:
            starts.append((clause_start(seg, m.start(), depths, 1), m.start()))
    if len(starts) < 2:
        return [(seg, [])]
    pieces = []
    for k, (st, pos) in enumerate(starts):
        a = 0 if k == 0 else st
        b = starts[k + 1][0] if k + 1 < len(starts) else len(seg)
        quoted = [p for p in persons if p in seg[st:pos]]
        quoted = [w for w in quoted if not any(w != o and w in o for o in quoted)]
        pieces.append((seg[a:b].strip(), quoted or [seg[st:pos].strip()[-8:]]))
    return pieces


def nlen(s: str) -> int:
    return len(re.sub(r"\s", "", s))


def split_long(text: str) -> list[str]:
    """MAX_LEN을 넘으면 '一,' 항목 시작 또는 문장 끝(。?!)에서 비슷한 길이로 나눈다."""
    if nlen(text) <= MAX_LEN:
        return [text]
    n_parts = math.ceil(nlen(text) / MAX_LEN)
    target = nlen(text) / n_parts
    units = re.split(r"(?<=[。?!])\s*(?=\S)|\s(?=一,)", text)
    parts, cur = [], ""
    for u in units:
        if cur and nlen(cur) + nlen(u) > target * 1.15 and nlen(cur) >= target * 0.6:
            parts.append(cur.strip())
            cur = ""
        cur += (" " if cur else "") + u
    if cur:
        parts.append(cur.strip())
    # v2: 조각이 닫는 따옴표(’" 등)로 시작하면 그 따옴표를 앞 조각 끝으로 옮긴다. 자르는 위치는 그대로 (규칙서 8장 ⑬)
    for i in range(1, len(parts)):
        m = re.match(r"[’”\"」\s]+", parts[i])
        if m and parts[i][: m.end()].strip():
            parts[i - 1] += parts[i][: m.end()].rstrip()
            parts[i] = parts[i][m.end():].lstrip()
    return [p for p in parts if p]


# ---------------------------------------------------------------- v2 규칙 도우미

def narration_time_words(text: str) -> list[str]:
    """시점 신호 단어와 서술 속 날짜. v2: 문장 첫머리·따옴표 밖·【】 밖에 있을 때만 센다
    (말 속의 '今年·明日', '何至是', '興運之初', '不得已而', '自前日本' 같은 오탐을 막음, 규칙서 8장 ⑭)."""
    depths, spans = quote_depths(text), bracket_spans(text)
    ok = lambda i: depths[i] == 0 and not in_bracket(spans, i) and at_sentence_start(text, i)
    found = [w for w in TIME_WORDS if any(ok(m.start()) for m in re.finditer(re.escape(w), text))]
    found += [m.group().rstrip(", ，") for m in DATE_START.finditer(text) if ok(m.start())]
    return found


def dedupe_names(names: list[str]) -> list[str]:
    """긴 이름에 들어 있는 짧은 이름은 뺀다(成三問이 있으면 三問은 빼기, 규칙서 8장 ⑨)."""
    return [n for n in names if not any(n != o and n in o for o in names)]


def _speaker_of_piece(piece: str, persons: list[str], king: str) -> tuple[str, str]:
    m = SPEECH.search(piece)
    if m and quote_depths(piece)[m.start()] == 0:
        return speaker_of(piece[: m.start()], persons, king)
    return "사관", "서술"


def _join_base(a: dict, b: dict) -> dict:
    """두 조각을 합칠 때 화자: 한쪽이 서술이면 말한 쪽, 둘 다 말이면 '문답'."""
    if a["kind"] == "서술":
        return dict(b) if b["kind"] != "서술" else dict(a)
    if b["kind"] == "서술" or a["speaker"] == b["speaker"]:
        return dict(a)
    return {**a, "speaker": f"{a['speaker']}·{b['speaker']}", "kind": "문답"}


def apply_manual(aid: str, chunks: list[dict], persons: list[str], king: str) -> list[dict]:
    """사람이 정한 경계(MANUAL)를 적용한다: join을 먼저, 그다음 cut. 찾지 못하면 멈춘다(원문이 바뀐 것)."""
    rule = MANUAL.get(aid)
    if not rule:
        return chunks
    chunks = [dict(c) for c in chunks]
    for phrase in rule.get("join", []):
        k = next((i for i, c in enumerate(chunks) if i > 0 and c["text"].startswith(phrase)), None)
        if k is None:
            raise SystemExit(f"사람 경계(join)를 찾지 못함: {aid} '{phrase}'")
        prev, cur = chunks[k - 1], chunks.pop(k)
        prev["base"] = _join_base(prev["base"], cur["base"])
        prev["text"] = prev["text"] + " " + cur["text"]
        prev["quoted"] = list(dict.fromkeys(prev["quoted"] + cur["quoted"]))
        prev["split"] = "사람 경계"
    for phrase in rule.get("cut", []):
        k = next((i for i, c in enumerate(chunks) if c["text"].find(phrase) > 0), None)
        if k is None:
            raise SystemExit(f"사람 경계(cut)를 찾지 못함: {aid} '{phrase}'")
        c = chunks[k]
        pos = c["text"].find(phrase)
        head, rest = c["text"][:pos].strip(), c["text"][pos:].strip()
        spk, kind = _speaker_of_piece(rest, persons, king)
        if kind == "이어서":
            spk, kind = c["base"]["speaker"], c["base"]["kind"]
        first = {**c, "text": head, "split": "사람 경계",
                 "base": {**c["base"], **dict(zip(("speaker", "kind"), _speaker_of_piece(head, persons, king)))}}
        if first["base"]["kind"] == "이어서":
            first["base"] = c["base"]
        second = {**c, "text": rest, "split": "사람 경계", "quoted": [],
                  "base": {**c["base"], "speaker": spk, "kind": kind}}
        chunks[k:k + 1] = [first, second]
    out: list[dict] = []
    for c in chunks:  # 따옴표 한 글자처럼 떨어져 나온 조각은 앞 청크 끝에 붙인다
        if out and nlen(re.sub(r"[\"“”‘’「」]", "", c["text"])) == 0:
            out[-1]["text"] += c["text"]
        else:
            out.append(c)
    return out


# ---------------------------------------------------------------- 기사 하나 처리

def article_meta(aid: str, el: ET.Element) -> dict:
    bib = el.find("front/biblioData")
    d = bib.find("date/dateOccured")
    date = d.get("date") if d is not None else None
    sources = [
        f"{s.find('mainTitle').get('type')} {s.find('mainTitle').text} {s.find('page').get('begin')}"
        for s in bib.findall("source")
    ]
    book = sources[0].split()[1] if sources else ""
    king_hanja = re.sub(r"(實錄|日記)$", "", book)
    king = KINGS.get(king_hanja, king_hanja)
    if aid[4:7] == "000":
        reign = "즉위 전(총서)"
    else:
        y = int(aid[5:7])
        reign = f"{king} {'즉위년' if y == 0 else str(y) + '년'}"  # 재위 연도 00 = 즉위년
    return {
        "article_id": aid,
        "record_date": date[:10] if date else None,
        "leap_month": bool(date and date.endswith("L1")),
        "king": king,
        "reign": reign,
        "title_ko": (bib.find("title/mainTitle").text or "").strip(),
        "source": sources[0] if sources else "",
        "subjects": [s.text for s in bib.findall("subjectClass")],
    }


def date_ko(meta: dict) -> str:
    if not meta["record_date"]:
        return "태조 즉위 전"
    y, m, d = meta["record_date"].split("-")
    leap = "윤" if meta["leap_month"] else ""
    return f"{int(y)}년 {leap}{int(m)}월 {int(d)}일"


def process_article(aid: str, el: ET.Element, quote_split: bool = True) -> tuple[list[dict], dict]:
    """quote_split=False 이면 인용 단위 쪼개기(4-3)를 하지 않는다 (청킹 전략 A 비교용)."""
    meta = article_meta(aid, el)
    fl = Flattener()
    paras = []
    for p in el.findall("text/content/paragraph"):
        only_quote = len(p) >= 1 and p[0].tag == "quotation" and not (p.text or "").strip()
        paras.append((fl.text(p), only_quote))
    count = fl.count
    persons = sorted(fl.index["이름"], key=len, reverse=True)
    king = meta["king"]

    # 1) 문단 정제
    cleaned = []
    for i, (raw, only_quote) in enumerate(paras):
        t = clean(raw, count)
        if t and not VOLUME_END.search(t) and VOLUME_END_TAIL.search(t):  # v2: 문단 끝에 붙은 권 끝 표시
            t = VOLUME_END_TAIL.sub("", t)
            count["권끝표시삭제"] += 1
        if not t or VOLUME_END.search(t):
            if t:
                count["권끝표시삭제"] += 1
            continue
        cleaned.append((i, t, only_quote))
    day_ganji = None
    if cleaned:
        i0, t0, q0 = cleaned[0]
        t0 = t0.lstrip("○◎ ")
        m = DAY_GANJI.match(t0)
        if m:
            day_ganji = m[1]
            t0 = t0[m.end():]
        cleaned[0] = (i0, t0, q0)

    # 2) 문단 안을 '말머리(X曰:)' 단위로 나누기. 말머리만 있는 문단 + 뒤따르는 인용 문단은 한 화자로 묶는다
    segs = []  # dict(paragraphs, text, speaker, kind)
    carry = None  # 앞 문단의 상소·발언을 이어받는 중인지
    for i, t, only_quote in cleaned:
        top_speech = any(quote_depths(t)[m.start()] == 0 for m in SPEECH.finditer(t))
        if carry is not None and (only_quote or not top_speech):
            segs.append({"paragraphs": [i], "text": t, "speaker": carry[0], "kind": carry[1]})
            continue
        if t.startswith("【史臣") or t.startswith("史臣曰"):
            segs.append({"paragraphs": [i], "text": t, "speaker": "사관", "kind": "사론"})
            carry = None
            continue
        depths = quote_depths(t)
        spans = bracket_spans(t)
        # v2: 【】 밖의 말머리는 구절 시작을 찾을 때 【】 안의 마침표를 문장 끝으로 보지 않는다
        #     (청크가 '】曰'로 시작하거나 【】 앞에서 문장이 잘리는 것을 막음, 8장 ④)
        masked = "".join("・" if in_bracket(spans, i) and ch not in "【】" else ch for i, ch in enumerate(t))
        mdepths = quote_depths(masked)
        cuts = [0]
        for m in SPEECH.finditer(t):
            if depths[m.start()] == 0:
                inside = in_bracket(spans, m.start())
                st = clause_start(t, m.start(), depths, 0) if inside else clause_start(masked, m.start(), mdepths, 0)
                if st > cuts[-1]:
                    cuts.append(st)
        # 시점이 바뀌는 곳(翌日 등)에서도 끊는다. v2: 문장 첫머리·따옴표 밖·【】 밖일 때만 (8장 ⑭)
        for m in re.finditer("|".join(TIME_SHIFT_START), t):
            if depths[m.start()] == 0 and not in_bracket(spans, m.start()) and at_sentence_start(t, m.start()):
                cuts.append(m.start())
        # v2: 서술에서 문장이 날짜(初八日 등)로 시작하면 끊는다 (규칙서 v2 ㉑)
        for m in DATE_START.finditer(t):
            if m.start() > 0 and depths[m.start()] == 0 and not in_bracket(spans, m.start()) and at_sentence_start(t, m.start()):
                cuts.append(m.start())
        cuts = sorted(set(cuts)) + [len(t)]
        carry = None
        for a, b in zip(cuts, cuts[1:]):
            piece = t[a:b].strip()
            if not piece:
                continue
            m = SPEECH.search(piece)
            if m and quote_depths(piece)[m.start()] == 0:
                spk, kind = speaker_of(piece[: m.start()], persons, king)
            else:
                spk, kind = "사관", "서술"
            tail = ""
            if kind != "서술":  # 말이 끝난 뒤 긴 서술이 이어지면(60자 이상) 서술 조각으로 떼어 낸다
                pd = quote_depths(piece)
                close = max((j for j, ch in enumerate(piece) if ch == '"' and pd[j - 1 if j else 0] >= 1
                             and (j + 1 == len(piece) or pd[j + 1] == 0)), default=-1)
                if close > 0 and nlen(piece[close + 1:]) >= 2 * MIN_LEN:
                    # v2: 닫는 따옴표 바로 뒤가 아니라 그 문장이 끝나는 곳에서 뗀다("義不可殺" / ", 力止之" 방지, 8장 ⑬)
                    end = close + 1
                    if not at_sentence_start(piece, end) or piece[end:].lstrip()[:1] in (",", "，"):
                        stop = re.search(r"[。?!]", piece[end:])
                        end = end + stop.end() if stop else len(piece)
                    if nlen(piece[end:]) >= 2 * MIN_LEN:
                        piece, tail = piece[:end], piece[end:].strip()
            segs.append({"paragraphs": [i], "text": piece, "speaker": spk, "kind": kind})
            if tail:
                segs.append({"paragraphs": [i], "text": tail, "speaker": "사관", "kind": "서술"})
            if m and piece.rstrip().endswith((":", "：")):
                carry = (spk, kind)  # 다음 문단이 이 말의 본문(상소문 등)

    # 3) 짧은 조각 붙이기: 말머리만 있는 조각('X上疏曰:')은 뒤 본문과, MIN_LEN 미만 조각은 앞 조각과 합친다.
    #    단, 시점이 바뀌는 말(翌日 등)로 시작하는 조각과 사론은 따로 둔다
    for k in range(len(segs) - 2, -1, -1):  # 말머리만 있는 조각('X序曰:')은 바로 뒤 본문 앞에 붙인다
        if segs[k]["text"].rstrip().endswith((":", "：")) and nlen(segs[k]["text"]) < MIN_LEN:
            nxt = segs[k + 1]
            nxt["text"] = segs[k]["text"] + " " + nxt["text"]
            nxt["paragraphs"] = sorted(set(segs[k]["paragraphs"] + nxt["paragraphs"]))
            nxt["speaker"], nxt["kind"] = segs[k]["speaker"], segs[k]["kind"]
            del segs[k]
    merged: list[dict] = []
    for s in segs:
        if s["kind"] == "이어서":  # '又曰' 등은 앞 화자를 물려받는다
            s["speaker"], s["kind"] = (merged[-1]["speaker"], merged[-1]["kind"]) if merged else ("?", "기타(확인필요)")
        too_short = bool(merged) and nlen(s["text"]) < MIN_LEN and not s["text"].startswith(TIME_SHIFT_START) \
            and not DATE_START.match(s["text"]) and "사론" not in (merged[-1]["kind"], s["kind"])
        if too_short:
            merged[-1].setdefault("speakers", [merged[-1]["speaker"]]).append(s["speaker"])
            merged[-1]["text"] += " " + s["text"]
            merged[-1]["paragraphs"] = sorted(set(merged[-1]["paragraphs"] + s["paragraphs"]))
        else:
            merged.append(dict(s))
    # v2: 다음 조각이 先是·初 등으로 시작하면(기사 날짜의 일 → 그 이전 배경) 짧아도 붙이지 않는다 (규칙서 v2 ㉓)
    if len(merged) > 1 and nlen(merged[0]["text"]) < MIN_LEN and merged[0]["kind"] != "사론" \
            and not merged[1]["text"].startswith(TIME_SHIFT_START):
        first = merged.pop(0)  # 기사 첫머리의 짧은 서술(설치하다 등)은 다음 조각 앞에 붙인다
        merged[0]["text"] = first["text"] + " " + merged[0]["text"]
        merged[0]["paragraphs"] = sorted(set(first["paragraphs"] + merged[0]["paragraphs"]))

    # 짧은 말이 여럿 합쳐진 조각: 말한 사람이 둘 이상이면 '문답'으로 적는다
    for s in merged:
        who = list(dict.fromkeys(w for w in s.get("speakers", [s["speaker"]]) if w != "사관"))
        if len(who) > 1:
            s["speaker"], s["kind"] = "·".join(who), "문답"

    # 4) 사론(postScript)은 따로
    for t in fl.sanlon:
        t = clean(t, count)
        if t:
            merged.append({"paragraphs": [], "text": t, "speaker": "사관", "kind": "사론"})

    # 5) 인용 단위 쪼개기 → 길이 나누기 → 청크 기록
    chunks = []
    for s in merged:
        units = []
        if quote_split and s["kind"] not in ("서술", "사론"):
            for piece, quoted in split_speech_quotes(s["text"], persons):
                units.append((piece, quoted, "인용" if quoted else ""))
        else:
            units.append((s["text"], [], ""))
        n_quote = sum(1 for u in units if u[2])
        for qi, (piece, quoted, why) in enumerate(units, 1):
            parts = split_long(piece)
            for pi, part in enumerate(parts, 1):
                split = []
                if why:
                    split.append(f"인용 {qi}/{n_quote}")
                if len(parts) > 1:
                    split.append(f"길이 {pi}/{len(parts)}")
                chunks.append({"base": s, "text": part, "quoted": quoted, "split": " · ".join(split)})

    chunks = apply_manual(aid, chunks, persons, king)

    out = []
    for k, c in enumerate(chunks, 1):
        s = c["base"]
        time_words = narration_time_words(c["text"])
        flags = []
        if time_words:
            flags.append("시점확인")
        if s["kind"] == "기타(확인필요)":
            flags.append("화자확인")
        if "□" in c["text"]:
            flags.append("없는글자")
        speaker_label = s["speaker"] if s["kind"] not in ("서술", "사론") else ("사관(서술)" if s["kind"] == "서술" else "사관(사론)")
        head = f"[{date_ko(meta)} · {meta['reign']} · {meta['title_ko']} · 말한 사람: {speaker_label}"
        if c["quoted"]:
            head += f" · 인용: {'·'.join(c['quoted'])}"
        head += "]"
        out.append({
            "chunk_id": f"{aid}-{k:02d}",
            **{key: meta[key] for key in ("article_id", "record_date", "leap_month", "king", "reign", "title_ko", "source", "subjects")},
            "day_ganji": day_ganji,
            "paragraphs": s["paragraphs"],
            "speaker": speaker_label,
            "speaker_kind": s["kind"],
            "quoted": c["quoted"],
            "split": c["split"],
            "event_date": None,   # 비워 두면 record_date와 같다고 본다. 번역 단계에서 사람/AI가 채움 (규칙서 4-4)
            "known_from": None,   # 인물들이 이 사실을 알게 된 때. 비워 두면 event_date와 같다
            "time_words": time_words,
            "flags": flags,
            "persons": dedupe_names([p for p in fl.index["이름"] if p in c["text"]]),
            "places": [p for p in fl.index["지명"] if p in c["text"]],
            "books": [p for p in fl.index["서명"] if p in c["text"]],
            "header": head,
            "original": c["text"],
            "n_chars": nlen(c["text"]),
        })
    return out, {"article_id": aid, "chunks": len(out), **count}


# ---------------------------------------------------------------- 통계

def stats_rows(chunks: list[dict]) -> list[list]:
    def row(name, group):
        ls = [c["n_chars"] for c in group]
        if not ls:
            return [name, 0, "", "", "", "", "", ""]
        short = sum(1 for n in ls if n < MIN_LEN)
        return [name, len(ls), round(statistics.mean(ls), 1), int(statistics.median(ls)), min(ls), max(ls),
                short, sum(1 for n in ls if n > MAX_LEN)]

    rows = [["구분", "청크수", "평균글자", "중앙값", "최단", "최장", f"{MIN_LEN}자미만", f"{MAX_LEN}자초과"]]
    rows.append(row("전체", chunks))
    for kind in ["서술", "임금", "왕실", "신하", "관청", "상소", "문답", "사론", "기타(확인필요)"]:
        rows.append(row(f"화자종류:{kind}", [c for c in chunks if c["speaker_kind"] == kind]))
    rows.append(row("인용 단위로 쪼갠 청크", [c for c in chunks if c["split"].startswith("인용")]))
    rows.append(row("길이 때문에 나눈 청크", [c for c in chunks if "길이" in c["split"]]))
    rows.append(row("시점확인 표시", [c for c in chunks if "시점확인" in c["flags"]]))
    rows.append(row("화자확인 표시", [c for c in chunks if "화자확인" in c["flags"]]))
    for king in dict.fromkeys(c["king"] for c in chunks):
        rows.append(row(f"실록:{king}", [c for c in chunks if c["king"] == king]))
    return rows


def article_ids() -> list[str]:
    """data/articles.jsonl에서 기사 ID를 순서 그대로 읽는다(고른 기사 목록은 추출할 때만 씀, 작업기록 [140])."""
    with open(ROOT / "data" / "articles.jsonl", encoding="utf-8") as f:
        return [json.loads(line)["article_id"] for line in f if line.strip()]


def main() -> None:
    ids = article_ids()
    files = {"jsonl": OUT / f"청크초안_{TAG}.jsonl", "stats": REC / f"청크통계_{TAG}.csv",
             "clean": REC / f"정제기록_{TAG}.csv", "check": REC / f"수동검사표_{TAG}.csv"}
    for f in files.values():
        if f.exists():
            raise SystemExit(f"이미 있음(덮어쓰지 않음): {f.relative_to(ROOT)} — 새 버전 이름으로 바꿔 실행하세요")
    OUT.mkdir(parents=True, exist_ok=True)
    REC.mkdir(parents=True, exist_ok=True)

    found = {aid: process_article(aid, load_article(aid)) for aid in ids}

    chunks, clean_rows = [], []
    for aid in ids:
        cs, cnt = found[aid]
        chunks += cs
        clean_rows.append(cnt)

    with open(files["jsonl"], "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with open(files["stats"], "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(stats_rows(chunks))
    keys = ["article_id", "chunks"] + sorted({k for r in clean_rows for k in r} - {"article_id", "chunks"})
    with open(files["clean"], "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, restval=0)
        w.writeheader()
        w.writerows(clean_rows)
    sample = random.Random(SEED).sample(chunks, N_CHECK)
    with open(files["check"], "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["번호", "chunk_id", "제목", "자동화자", "화자종류", "인용된사람", "나눔", "글자수", "표시",
                    "원문", "가판정(정상/잘림/섞임/버림)", "화자맞음(O/X/△)", "가판정메모", "사람확인"])
        for i, c in enumerate(sample, 1):
            w.writerow([i, c["chunk_id"], c["title_ko"], c["speaker"], c["speaker_kind"], "·".join(c["quoted"]),
                        c["split"], c["n_chars"], " ".join(c["flags"]), c["original"], "", "", "", ""])
    print(f"기사 {len(ids)}건 → 청크 {len(chunks)}개")
    for r in stats_rows(chunks)[:4]:
        print("  ", r)


if __name__ == "__main__":
    if take_tag(sys.argv[1:]):
        raise SystemExit(__doc__)
    main()
