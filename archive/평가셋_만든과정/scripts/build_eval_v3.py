"""평가셋 v3를 만든다 (2026-09-29).

v3 = 평가셋 v2(41문항, 그대로) + 초안(exam_20260929_v1)에서 v2에 없는 문항 26개.
    - 사실 19개: v2가 다루지 않은 기사(광교산 전투, 나선 정벌, 은대, 유향소, 훈련도감, 고려사 등)
    - 잘못된 전제 5개: 다른 시대 것을 조선 일로 묻기 4개(건원중보·동시전·활구·벽란도) + 명량 배 수
    - 자료 없음 2개: 이익 한전론, 김정희 북한산비

사용법:
    python scripts/build_eval_v3.py

v2 파일은 읽기만 하고 고치지 않는다. 검사 방식은 build_eval_v2.py와 같다.
    gold_chunks 가 규칙서 청크 파일에 있는지
    must_terms 가 정답 청크 번역(확장분 코퍼스 769청크)에 실제로 나오는지 → 없으면 멈춤
다만 "다른 시대" 함정은 정답(예: 건원중보는 고려 화폐)이 실록에 없는 일반 지식이라
정답 청크가 없다. 그래서 must_terms 번역 검사를 건너뛰고, 헷갈리기 쉬운 조선 쪽 청크를
near_chunks 로 적는다. 한능검 회차·문항 번호는 판정표의 부정형 문항 번호를 직접 적는다.
출력: data/eval/v3_20260929_한능검코퍼스+함정보강.jsonl (이미 있으면 덮어쓰지 않고 멈춤)
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from build_eval_v2 import CHUNKS, CORPUS, VERDICT, hanneung_refs, read_jsonl

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "data" / "eval" / "v2_20260929_한능검코퍼스.jsonl"
OUT = ROOT / "data" / "eval" / "v3_20260929_한능검코퍼스+함정보강.jsonl"

ITEMS: list[dict] = [
    # ── 사실: v2에 없는 기사 ──────────────────────────────────────
    dict(id="F29", category="사실", topic="호란·북벌",
         question="병자호란 때 남한산성이 포위됐을 때, 전라병사 김준룡은 어디서 싸웠고 그 소식이 성 안에 어떤 영향을 줬나?",
         expected="광교산(수원·용인 사이)에 진을 치고 싸워 이겼다고 장계함. 구원병 소식이 잇따르자 성안에서 이를 믿고 굳게 버팀.",
         gold=["wpa_11501005_003-01", "wpa_11501005_003-02"], must=["광교산"]),
    dict(id="F30", category="사실", topic="호란·북벌",
         question="효종 때 변급이 청나라 군사와 함께 쳐부순 상대는 누구인가?",
         expected="나선(러시아). 깨뜨린 뒤 영고탑으로 돌아옴(1654).",
         gold=["wqa_10507002_005-01"], must=["나선|러시아"]),
    dict(id="F31", category="사실", topic="호란·북벌",
         question="1651년 이완은 어떤 벼슬에 임명되었나?",
         expected="특별히 다시 등용되어 어영대장에 임명됨.",
         gold=["wqa_10208004_003-01"], must=["어영"]),
    dict(id="F32", category="사실", topic="사화·사림",
         question="중종 때 김정과 조광조는 과거 말고 어떤 방식으로 인재를 뽑자고 했나?",
         expected="과거 출신만 쓰는 길이 좁으니 천거로 사람을 뽑아(천거과) 쓰자고 함. 대신들 사이에는 반대 의견도 있었음.",
         gold=["wka_11303025_001-04", "wka_11303025_001-05"], must=["천거"]),
    dict(id="F33", category="사실", topic="통치 기구·지방·군사",
         question="승정원을 '은대'라고도 불렀다는데, 실록에 은대는 어떤 곳이라고 나오나?",
         expected="밤낮으로 (왕명을) 출납하는 곳이고, 계판을 두는 곳이라 승지들이 청사에 벌여 앉음(1656 사헌부 계).",
         gold=["wqa_10706011_002-01"], must=["출납"]),
    dict(id="F34", category="사실", topic="통치 기구·지방·군사",
         question="1482년 유향소를 다시 세울 때 좌수는 누가 고르게 했고, 몇 명씩 두었나?",
         expected="각 고을의 경재소가 골라 부 이상은 4명, 군 이하는 3명을 좌수·색장으로 정함.",
         gold=["wia_11302002_006-01"], must=["경재소", "4명"]),
    dict(id="F35", category="사실", topic="통치 기구·지방·군사",
         question="비변사는 원래 무슨 이름이었나?",
         expected="축성사. 1517년(중종) 축성사를 고쳐 비변사라 함.",
         gold=["wka_11206027_005-01"], must=["축성사"]),
    dict(id="F36", category="사실", topic="임진왜란",
         question="1593년 선조가 훈련도감을 따로 두자고 한 이유와 거기서 가르치려던 것은 무엇인가?",
         expected="전쟁 2년이 되도록 비변사가 군사 하나 훈련하지 않고 명군만 바라봄. 장정을 뽑아 날마다 활쏘기·포 쏘기 등 무예를 가르치게 함.",
         gold=["wna_12608019_005-01"], must=["활", "포"]),
    dict(id="F37", category="사실", topic="임진왜란",
         question="행주산성 싸움에서 화살이 거의 떨어졌을 때 누가 화살을 날라 왔나?",
         expected="충청병사 정걸. 싸움은 묘시부터 신시까지 이어짐.",
         gold=["wna_12602024_001-07"], must=["정걸"]),
    dict(id="F38", category="사실(수치)", topic="조선 후기 경제",
         question="1678년 상평통보를 만들 때 돈과 은의 값을 어떻게 정했나?",
         expected="돈 400문을 은 1냥으로 정함. 허적·권대운 등이 청했고 호조·상평청 등 여러 관청이 주조함.",
         gold=["wsa_10401023_001-02"], must=["400", "상평통보"]),
    dict(id="F39", category="사실", topic="세도 정치·민란·천주교",
         question="황사영 백서는 어디로 보내려던 것이고, 어떤 내용이 들어 있었나?",
         expected="북경의 천주당. 신유박해 소식과 함께, 청 황제가 조선에 서양인을 받아들이게 할 것, 안주에 무안사를 둘 것, 서양 배 수백 척과 군사 5~6만을 보낼 것의 세 조목.",
         gold=["wwa_10110005_002-01"], must=["북경", "배"]),
    dict(id="F40", category="사실", topic="세종",
         question="《농사직설》은 누가 어떻게 만들었고, 옛 농서와 무엇이 다른가?",
         expected="정초 등이 지음. 지역마다 풍토가 달라 옛 농서를 그대로 쓸 수 없으니, 각 도 감사가 고을의 늙은 농부에게 실제로 해 본 방법을 물어 모았음(1429).",
         gold=["wda_11105016_002-01"], must=["정초", "농부"]),
    dict(id="F41", category="사실(수치)", topic="정조",
         question="정조가 규장각(내각)에 처음 둔 검서관은 어떤 사람 중에서 뽑았고 몇 명이었나?",
         expected="서얼 가운데 문예가 있는 사람, 4명(1779).",
         gold=["wva_10303027_003-01"], must=["서얼", "4명"]),
    dict(id="F42", category="사실", topic="정조",
         question="정조가 젊은 문신을 따로 뽑아 공부시킨(초계문신) 이유는 무엇인가?",
         expected="문풍이 떨치지 못하는 것은 길러 내는 방법이 잘못되어서라며, 젊은 문신을 뽑아 경사를 공부하고 글을 짓게 해 상벌을 주려 함(1781).",
         gold=["wva_10502017_003-01"], must=["문풍"]),
    dict(id="F43", category="사실", topic="세조·계유정난",
         question="1466년 세조 때 토지 제도는 어떻게 바뀌었나?",
         expected="과전을 혁파하고 직전을 설치함(직전법).",
         gold=["wga_11208025_005-01"], must=["과전", "직전"]),
    dict(id="F44", category="사실", topic="세조·계유정난",
         question="세조가 집현전을 없앤 뒤 집현전에 있던 책은 어떻게 했나?",
         expected="집현전을 없애고 경연도 멈추었으며, 소장하던 책은 예문관이 맡게 함(1456).",
         gold=["wga_10206006_003-01"], must=["예문관"]),
    dict(id="F45", category="사실", topic="대외관계",
         question="1673년 부산의 왜관은 어디로 옮기는 것을 허락했나?",
         expected="초량(초량항). 웅천은 안 되고 초량은 괜찮다는 조정 의논에 따라 허락함.",
         gold=["wra_11410019_001-03"], must=["초량"]),
    dict(id="F46", category="사실(수치)", topic="성종 통치 정비",
         question="1474년 《경국대전》을 반포할 때 대전에 싣지 않은 조항은 어떻게 했나?",
         expected="속록이라 이름하여 모두 72조를 함께 반포함.",
         gold=["wia_10501002_004-01"], must=["속록", "72"]),
    # 고려사: 초안 N31. 한능검 67회 20번(고려사) 기사.
    dict(id="F47", category="사실", topic="조선 전기 문화·편찬",
         question="《고려사》는 누가 바쳤고, 어떻게 구성되어 있나?",
         expected="김종서 등이 바침(1451). 세가 46권, 지 39권, 연표 2권, 열전 50권, 목록 2권.",
         gold=["wea_10108025_001-01"], must=["김종서", "세가 46"]),

    # ── 잘못된 전제: 다른 시대 것을 조선 일로 묻기 (정답은 일반 지식, 번역 검사 없음) ──
    dict(id="T06", category="잘못된 전제(다른 시대)", topic="조선 후기 경제",
         question="조선 태종이 건원중보를 만들어 쓰게 한 이유는 무엇인가?",
         expected="전제가 틀림. 건원중보는 고려(성종) 때 화폐이고 자료에 없음. 조선에서 돈을 널리 쓰게 한 자료는 1678년 상평통보.",
         wrong="태종이 건원중보를 만든 이유를 지어냄",
         gold=[], near=["wsa_10401023_001-02"], must=["고려|아니|없"], hanneung=["72회 27번"]),
    dict(id="T07", category="잘못된 전제(다른 시대)", topic="조선 후기 경제",
         question="정조가 동시전을 두어 서울 시장을 감독하게 했다는데, 동시전은 무슨 일을 했나?",
         expected="전제가 틀림. 동시전은 신라의 시장 감독 관청. 정조 때 시장 자료는 신해통공(1791, 육전 밖 자유 매매 허락).",
         wrong="정조의 동시전 설치를 사실로 받아들임",
         gold=[], near=["wva_11501025_001-01"], must=["신라|아니|없"], hanneung=["66회 26번"]),
    dict(id="T08", category="잘못된 전제(다른 시대)", topic="조선 후기 경제",
         question="순조 때 활구(은병)를 만들어 쓴 이유는 무엇인가?",
         expected="전제가 틀림. 활구(은병)는 고려(숙종) 때 화폐이고 자료에 없음.",
         wrong="순조 때 활구를 만든 이유를 지어냄",
         gold=[], near=[], must=["고려|아니|없"], hanneung=["78회 25번"]),
    dict(id="T09", category="잘못된 전제(다른 시대)", topic="대외관계",
         question="조선 후기에 벽란도에서 송나라 상인과 어떤 무역을 했나?",
         expected="전제가 틀림. 벽란도에서 송 상인과 교역한 것은 고려 때. 조선 후기 교역 자료로는 왜관의 초량 이전(1673) 등이 있음.",
         wrong="조선 후기 벽란도 송 무역을 사실로 받아들임",
         gold=[], near=["wra_11410019_001-03"], must=["고려|아니|없"], hanneung=["68회 23번", "70회 25번"]),

    # ── 잘못된 전제: 자료 안의 사실을 틀리게 바꾸기 ──
    dict(id="T10", category="잘못된 전제", topic="임진왜란",
         question="이순신이 명량(벽파정 아래)에서 배 30척으로 적선 200여 척을 이긴 비결은 무엇인가?",
         expected="전제의 배 수가 틀림. 실록에는 배 12척에 대포를 싣고 조수를 타고 공격해 이기고 적장 마다시를 죽였다고 나옴.",
         wrong="30척을 그대로 받아들여 답함",
         gold=["wnb_13009001_003-01"], must=["12척"]),

    # ── 자료 없음 ──
    dict(id="N06", category="자료 없음", topic="실학",
         question="이익이 《곽우록》에서 주장한 한전론은 어떤 내용인가?",
         expected="자료에 없음. 실학자 저술 내용은 실록 기사에 없다.",
         abstain=True, gold=[], must=[], hanneung=["65회 27번"]),
    dict(id="N07", category="자료 없음", topic="조선 후기 사회·문화(예술)",
         question="김정희는 북한산비가 진흥왕 순수비라는 것을 어떻게 밝혀냈나?",
         expected="자료에 없음. 학자 개인 연구라 실록 기사에 없다.",
         abstain=True, gold=[], must=[], hanneung=["71회 25번"]),
]


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"{OUT.relative_to(ROOT)} 이 이미 있어 멈춤(덮어쓰지 않음)")
    v2 = read_jsonl(V2)
    chunks = {c["chunk_id"]: c for c in read_jsonl(CHUNKS)}
    trans = {c["chunk_id"]: c["translation"] for c in read_jsonl(CORPUS)}
    verdict = list(csv.DictReader(open(VERDICT, encoding="utf-8")))

    seen = {r["id"] for r in v2}
    out, problems = [], []
    for it in ITEMS:
        if it["id"] in seen:
            problems.append(f"{it['id']}: v2와 id가 겹침")
        seen.add(it["id"])
        gold = it["gold"]
        for cid in gold + it.get("near", []):
            if cid not in chunks:
                problems.append(f"{it['id']}: 없는 청크 {cid}")
        evidence = []
        for cid in gold:
            c = chunks.get(cid)
            if c:
                paras = "·".join(str(p + 1) for p in c["paragraphs"])  # 규칙서는 0부터, 평가셋은 1부터
                ev = f"{c['article_id']} {paras}문단" if paras else c["article_id"]
                if ev not in evidence:
                    evidence.append(ev)
        if gold:  # 정답 청크가 있는 문항만 번역 검사(다른 시대 함정·자료 없음은 건너뜀)
            text = " ".join(trans.get(cid, "") for cid in gold)
            for term in it["must"]:
                if not re.search(term, text):
                    problems.append(f"{it['id']}: must_terms '{term}'가 정답 청크 번역에 없음")
        row = {
            "id": it["id"], "category": it["category"], "mode": "fact", "topic": it["topic"],
            "question": it["question"], "expected": it["expected"],
        }
        if "wrong" in it:
            row["wrong_example"] = it["wrong"]
        row.update({
            "evidence": evidence, "must_terms": it["must"], "gold_chunks": gold,
            "abstain": it.get("abstain", False),
        })
        if it.get("near"):
            row["near_chunks"] = it["near"]  # 정답은 아니지만 헷갈리기 쉬운 가까운 청크
        if "hanneung" in it:
            row["hanneung"] = it["hanneung"]
        else:
            arts = {cid.rsplit("-", 1)[0] for cid in gold + it.get("near", [])}
            row["hanneung"] = hanneung_refs(verdict, arts)
        out.append(row)

    if problems:
        raise SystemExit("검사 실패:\n" + "\n".join(problems))
    rows = v2 + out
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    cats: dict[str, int] = {}
    for r in rows:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    print(f"{OUT.relative_to(ROOT)}: {len(rows)}문항 (v2 {len(v2)} + 추가 {len(out)}) {cats}")


if __name__ == "__main__":
    main()
