// 최종 발표 PPT 초안을 만든다(2026-10-12, 작업기록 [405]).
// 실행: NODE_PATH=<pptxgenjs가 설치된 node_modules> node scripts/final_deck.js <apply_theme.js 경로>
// 숫자는 HANDOFF '10-08 최종 측정 결과'와 docs/기록/제출/최종측정_20261008.html 그대로 쓴다(새로 잰 숫자 없음).
// 구성은 docs/기록/제출/최종발표_요구사항.md 0-10번. 캡처·녹화 자리는 비워 둔다.
const path = require("path");
const pptxgen = require("pptxgenjs");
const { applyTheme } = require(process.argv[2]);

const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "docs/기록/제출/최종발표_20261012_이성빈.pptx");
const IMG = (name) => path.join(ROOT, "docs/기록/제출/최종발표_그림", name);

// 앱(역사 취재록)과 같은 색: 밤 남색 · 종이 · 인주 빨강 · 금빛 · 청록
const THEME = {
  name: "역사 취재록",
  headFontFace: "Batang",
  bodyFontFace: "Malgun Gothic",
  colors: {
    dk1: "1B2433", lt1: "FFFFFF", dk2: "0F1B2A", lt2: "F3ECDD",
    accent1: "A2412F", accent2: "B8913F", accent3: "2D6B5C", accent4: "5B6B7A", accent5: "E9DDC2", accent6: "6F2A1F",
    hlink: "2D6B5C", folHlink: "6F2A1F",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";   // 13.33 × 7.5 in
pres.title = "역사 취재록 최종 발표";
pres.author = "이성빈";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;
const W = 13.333;

// ---------- 레이아웃 ----------
pres.defineSlideMaster({
  title: "DARK",
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.0, w: 6.6, h: 1.6, fontSize: 48, bold: true, color: C.background1, valign: "bottom" }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 3.75, w: 6.6, h: 1.6, fontSize: 18, color: C.accent5, valign: "top" }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: C.background1 },
  margin: [0.4, 0.6, 0.6, 0.6],
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 1.35, y: 0.38, w: 11.4, h: 0.8, fontSize: 30, bold: true, color: C.text1, valign: "middle", margin: 0 }, text: "" } },
    { text: { text: "역사 취재록 · 최종 발표", options: { x: 0.6, y: 7.05, w: 6, h: 0.3, fontSize: 10, color: C.accent4, margin: 0 } } },
  ],
  slideNumber: { x: 12.2, y: 7.02, w: 0.55, h: 0.3, fontSize: 10, color: C.accent4, align: "right" },
});

// ---------- 그리기 도우미 ----------
// 반복 모티프: 제목 왼쪽의 인주 도장(정사각형 안에 번호)
function seal(slide, label) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 0.48, w: 0.6, h: 0.6, rectRadius: 0.06, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: "도장" });
  slide.addText(String(label), { x: 0.6, y: 0.48, w: 0.6, h: 0.6, align: "center", valign: "middle", fontSize: 18, bold: true, color: C.background1, fontFace: "Batang", margin: 0, isTextBox: true, objectName: "도장 번호" });
}
function content(title, label, notes, section) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  seal(s, label);
  if (notes) s.addNotes(notes);
  return s;
}
function card(s, x, y, w, h, fill) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill || C.background2 }, line: { color: C.accent5, width: 0.75 }, objectName: "카드" });
}
const text = (s, t, o) => s.addText(t, Object.assign({ isTextBox: true, margin: 0, valign: "top", color: C.text1, fontSize: 16 }, o));
const runs = (arr) => arr.map((r, i) => Object.assign({}, r, { options: Object.assign({ breakLine: i < arr.length - 1 }, r.options || {}) }));

// ---------- 0. 표지 ----------
pres.addSection({ title: "표지" });
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "표지" });
  s.addText("역사 취재록", { placeholder: "title" });
  s.addText(runs([
    { text: "조선왕조실록 원문으로 답하는 역사 인물 인터뷰 RAG", options: { fontSize: 20, bold: true, color: "F3ECDD" } },
    { text: "실록에 적힌 것만 말하고, 없는 것은 없다고 하는 역사 챗봇", options: { fontSize: 16 } },
    { text: " ", options: { fontSize: 10 } },
    { text: "이성빈 · 2026년 10월", options: { fontSize: 16, color: "B8913F" } },
  ]), { placeholder: "body" });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.8, y: 1.25, w: 0.6, h: 0.6, rectRadius: 0.06, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: "도장" });
  s.addText("史", { x: 0.8, y: 1.25, w: 0.6, h: 0.6, align: "center", valign: "middle", fontSize: 22, bold: true, color: C.background1, fontFace: "Batang", margin: 0, isTextBox: true });
  s.addImage({ path: IMG("취재화면_계유정난.png"), x: 7.75, y: 1.3, w: 5.0, h: 3.5, objectName: "취재 화면" });
  s.addText("서비스 화면 · 계유정난 인물 취재", { x: 7.75, y: 4.9, w: 5.0, h: 0.35, fontSize: 12, color: C.accent5, isTextBox: true, margin: 0 });
  s.addNotes("인사 후 한 줄 소개. 조선왕조실록 원문(한문)을 직접 번역한 자료로 답하는 챗봇이고, 결과물은 사건 속 인물을 취재하는 학습 서비스 '역사 취재록'입니다.");
}

// ---------- 1. 문제 ----------
pres.addSection({ title: "문제와 사례" });
{
  const s = content("실록을 물으면, 그럴듯한 답이 돌아온다", 1,
    "기술 이야기 없이 상황만. 한국사를 공부하는 사람이 AI에게 실록 내용을 물으면 날짜·숫자·사람 이름까지 그럴듯하게 답하지만, 그게 실록에 실제로 있는 말인지 확인할 방법이 없습니다. 원문은 한문이고 번역문은 찾아 대조하기 어렵습니다.", "문제와 사례");
  const items = [
    ["누가", "한국사를 공부하는 학생 · 한능검 수험생"],
    ["어떤 상황에서", "실록 속 사건과 인물을 AI 챗봇에 물어 공부할 때"],
    ["무엇이 곤란한가", "답이 실제 기록인지 지어낸 말인지 알 수 없다. 원문은 한문이고, 번역문은 찾아 대조하기 어렵다"],
  ];
  items.forEach(([head, body], i) => {
    const x = 0.6 + i * 4.1;
    card(s, x, 1.6, 3.85, 3.3);
    text(s, head, { x: x + 0.35, y: 1.9, w: 3.2, h: 0.5, fontSize: 20, bold: true, color: C.accent1, fontFace: "Batang" });
    text(s, body, { x: x + 0.35, y: 2.55, w: 3.2, h: 2.2, fontSize: 18, lineSpacingMultiple: 1.15 });
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 5.35, w: 12.15, h: 1.2, rectRadius: 0.08, fill: { color: C.text2 }, line: { color: C.text2 }, objectName: "필요한 것" });
  text(s, [
    { text: "필요한 것   ", options: { bold: true, color: "B8913F" } },
    { text: "실록에 적힌 것만 말하고, 없는 것은 없다고 하고, 근거 기사를 바로 보여 주는 답", options: { color: "FFFFFF" } },
  ], { x: 1.0, y: 5.35, w: 11.4, h: 1.2, valign: "middle", fontSize: 20 });
}

// ---------- 2. GPT 빈손 오답 사례 ----------
{
  const s = content("GPT 빈손이 틀린 실제 사례", 2,
    "2026-10-08 측정 때 무료 ChatGPT(웹 검색 끔, 임시 채팅)의 답입니다. 임시 채팅이라 기록이 남지 않아 같은 조건으로 다시 물어 캡처를 넣습니다. 다시 물었을 때 GPT가 맞히면, '같은 질문에도 답이 바뀐다'는 점과 10-08 측정 숫자를 구분해서 말합니다.", "문제와 사례");
  const ex = [
    { q: "《삼강행실도》를 처음 엮을 때 효자·충신·열녀의 사례는 각각 몇 명씩 골랐어?",
      gpt: "“세종 16년 4월 27일, 각 35명”", real: "각각 110명", src: "세종실록 1432년(세종 14년) 6월 9일 기사" },
    { q: "숙종 때 금위영에 대장을 따로 두기로 했다던데, 그때 대장으로 누구를 임명했어?",
      gpt: "대장으로 “신여철”을 임명했다고 답함", real: "대장은 따로 두지 않고 병조판서가 겸함", src: "숙종실록 1685년(숙종 11년) 7월 23일 기사 · 따로 둔 것은 제조" },
  ];
  ex.forEach((e, i) => {
    const y = 1.5 + i * 2.65;
    card(s, 0.6, y, 7.3, 2.45);
    text(s, [{ text: "질문  ", options: { bold: true, color: C.accent4 } }, { text: e.q }], { x: 0.9, y: y + 0.2, w: 6.8, h: 0.75, fontSize: 15 });
    text(s, [{ text: "GPT 빈손  ", options: { bold: true, color: C.accent1 } }, { text: e.gpt }], { x: 0.9, y: y + 1.0, w: 6.8, h: 0.4, fontSize: 16 });
    text(s, [{ text: "실록 기록  ", options: { bold: true, color: C.accent3 } }, { text: e.real, options: { bold: true } }], { x: 0.9, y: y + 1.42, w: 6.8, h: 0.45, fontSize: 16 });
    text(s, "출처 · " + e.src, { x: 0.9, y: y + 1.9, w: 6.8, h: 0.4, fontSize: 12, color: C.accent4 });
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.2, y: 1.5, w: 4.55, h: 5.1, rectRadius: 0.08, fill: { color: C.background2 }, line: { color: C.accent4, width: 1.25, dashType: "dash" }, objectName: "캡처 자리" });
  text(s, runs([
    { text: "캡처 넣을 자리", options: { bold: true, fontSize: 18, color: C.accent4 } },
    { text: " ", options: { fontSize: 8 } },
    { text: "같은 조건으로 다시 묻기", options: { fontSize: 14, color: C.accent4 } },
    { text: "ChatGPT 화면 · 임시 채팅 · 웹 검색 끔 · 질문 앞에 “조선왕조실록에 기록된 내용을 바탕으로 답해 줘. 기록에서 확인할 수 없으면 확인할 수 없다고 말해 줘.”", options: { fontSize: 13, color: C.accent4 } },
  ]), { x: 8.5, y: 2.9, w: 3.95, h: 2.6, align: "center", valign: "middle" });
}

// ---------- 3. 데이터 ----------
pres.addSection({ title: "만든 것" });
{
  const s = content("데이터: 실록 원문을 직접 번역해 조각으로", 3,
    "기사 고르기: 한능검 심화 65-79회 조선 문항 148개의 출제 주제로 실록 기사 132건을 골랐습니다. 번역: 저작권이 있는 국역은 쓰지 않고 한문 원문만 보고 번역했습니다(AI 초안 + 일부 사람 검수). 조각마다 말한 사람과 그 일을 알게 된 날짜를 붙여, 인물이 아직 모르는 미래 기사는 검색에서 뺍니다.", "만든 것");
  const stats = [["132건", "실록 기사"], ["803개", "조각(청크)"], ["4,512개", "쉬운 말 풀이"]];
  stats.forEach(([n, l], i) => {
    const x = 0.6 + i * 2.55;
    card(s, x, 1.6, 2.35, 1.9);
    text(s, n, { x: x + 0.1, y: 1.8, w: 2.15, h: 0.9, fontSize: 36, bold: true, color: C.accent1, align: "center", valign: "middle", fontFace: "Batang" });
    text(s, l, { x: x + 0.1, y: 2.75, w: 2.15, h: 0.5, fontSize: 15, color: C.accent4, align: "center" });
  });
  const rows = [
    ["출처", "국사편찬위원회 조선왕조실록 원문(공공누리 1유형). 한능검 심화 15회분 조선 문항 148개의 출제 주제로 기사를 고름"],
    ["번역", "한문 원문만 보고 직접 번역(AI 초안 + 일부 사람 검수). 저작권이 있는 국역 번역문은 쓰지 않음"],
    ["자른 방식", "기사 → 문단 → 말한 사람(○○曰) → 시점이 바뀌는 곳 → 400자 순으로 자르고, 뜻이 끊기는 곳은 사람이 경계를 정함"],
    ["조각마다", "말한 사람 · 그 일을 알게 된 날짜 · 쉬운 말 풀이를 붙임"],
  ];
  rows.forEach(([h, b], i) => {
    const y = 1.6 + i * 1.22;
    text(s, h, { x: 8.4, y, w: 1.4, h: 1.0, fontSize: 16, bold: true, color: C.accent3 });
    text(s, b, { x: 9.8, y, w: 2.95, h: 1.1, fontSize: 14, lineSpacingMultiple: 1.1 });
  });
  card(s, 0.6, 3.8, 7.45, 2.8, C.background1);
  text(s, runs([
    { text: "조각 하나의 모습", options: { bold: true, fontSize: 15, color: C.accent4 } },
    { text: "[1453-10-10 · 단종 1년 · 말한 사람: 수양대군]", options: { fontSize: 14, color: C.accent3 } },
    { text: "“내가 깊이 생각해 보니 간사한 무리 가운데 가장 간사하고 교활한 자는 김종서만 한 이가 없다. 저쪽이 만약 먼저 알면 일이 이루어지지 못할 것이다.”", options: { fontSize: 15 } },
    { text: "풀이 · 종사: 왕실과 나라", options: { fontSize: 13, color: C.accent4 } },
  ]), { x: 0.9, y: 4.0, w: 6.9, h: 2.45, paraSpaceAfter: 6 });
}

// ---------- 4. 평가셋 ----------
{
  const s = content("평가셋: 고치는 데 쓴 문항과 봉인한 문항", 4,
    "개발 문항은 고치는 동안 계속 보며 쓴 문항이라 점수가 잘 나오는 게 당연합니다. 그래서 9-30에 한능검 재료 절반을 봉인해 두고, 고치는 동안 한 번도 쓰지 않은 그 절반으로 홀드아웃 20문항을 만들어 10-08에 딱 한 번 돌렸습니다. 함정 예시 두 개를 설명합니다.", "만든 것");
  card(s, 0.6, 1.5, 5.95, 2.75);
  text(s, runs([
    { text: "개발 문항 · 고치는 데 씀", options: { bold: true, fontSize: 20, color: C.accent3, fontFace: "Batang" } },
    { text: "단발 질문 67개: 사실 47 · 함정 10 · 자료에 없는 질문 7 · 일부만 있음 3", options: { fontSize: 15, bullet: true } },
    { text: "역할 대화 5장면 50턴(인물이 미래를 말하지 않는지 포함)", options: { fontSize: 15, bullet: true } },
    { text: "비교용 20개: 홀드아웃과 같은 구성으로 무작위로 뽑음", options: { fontSize: 15, bullet: true } },
  ]), { x: 0.9, y: 1.7, w: 5.4, h: 2.4, paraSpaceAfter: 6 });
  card(s, 6.8, 1.5, 5.95, 2.75);
  text(s, runs([
    { text: "홀드아웃 · 봉인, 한 번만 실행", options: { bold: true, fontSize: 20, color: C.accent1, fontFace: "Batang" } },
    { text: "20개: 정답형 10 · 이름을 뺀 질문 3 · 숫자 2 · 자료 없음 2 · 함정 3", options: { fontSize: 15, bullet: true } },
    { text: "두 AI가 따로 만든 40개 중 사람이 20개 확정 → 잠근 뒤 10-08에 한 번 실행", options: { fontSize: 15, bullet: true } },
    { text: "결과를 보고 문항·코드·번역을 고치지 않음", options: { fontSize: 15, bullet: true } },
  ]), { x: 7.1, y: 1.7, w: 5.4, h: 2.4, paraSpaceAfter: 6 });
  text(s, "함정 문항 예시", { x: 0.6, y: 4.5, w: 6, h: 0.4, fontSize: 18, bold: true, color: C.text1, fontFace: "Batang" });
  const traps = [
    ["틀린 전제", "“숙종 때 금위영에 대장을 따로 두기로 했다던데, 그때 대장으로 누구를 임명했어?”",
      "실제로는 대장을 따로 두지 않았다. 질문을 따라가면 없는 사람을 지어내게 된다"],
    ["말한 사람 바꿔 묻기", "(최만리 상소 날 세종에게) “최만리가 전에 ‘언문 제작이 불가하지 않다’고 했다가 말을 바꾼 것 아닙니까?”",
      "말을 바꾼 사람은 김문이다. 맞장구치면 틀린다"],
  ];
  traps.forEach(([tag, q, why], i) => {
    const x = 0.6 + i * 6.2;
    card(s, x, 5.0, 5.95, 1.75, C.background1);
    text(s, tag, { x: x + 0.3, y: 5.12, w: 5.4, h: 0.35, fontSize: 14, bold: true, color: C.accent1 });
    text(s, q, { x: x + 0.3, y: 5.47, w: 5.4, h: 0.7, fontSize: 14 });
    text(s, "왜 함정인가 · " + why, { x: x + 0.3, y: 6.17, w: 5.4, h: 0.5, fontSize: 13, color: C.accent4 });
  });
}

// ---------- 5. 숫자 표 ----------
pres.addSection({ title: "결과" });
{
  const s = content("결과: 처음 보는 문항 8/20 → 17/20", 5,
    "부분 정답은 정답으로 세지 않았습니다. 개발 문항은 AI(Claude)가 미리 합의한 기준표로 채점했고, 홀드아웃은 사람과 AI가 따로 채점해 처음 판정이 18/20 일치했습니다. 답변 모델이 다르다는 점을 꼭 말합니다: 고치기 전은 gpt-4o-mini, 고친 후는 gpt-6-luna. GPT 빈손 숫자는 ChatGPT 화면에서 웹 검색을 끄고 물은 것입니다.", "결과");
  const hd = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: "1B2433" }, align: "center" } });
  const c = (t, o) => ({ text: t, options: Object.assign({ align: "center" }, o || {}) });
  const hi = (t) => c(t, { bold: true, color: "A2412F" });
  text(s, "답 채점 (부분 정답은 세지 않음)", { x: 0.6, y: 1.4, w: 8, h: 0.4, fontSize: 16, bold: true, color: C.accent3 });
  s.addTable([
    [hd("문항"), hd("GPT 빈손 유료"), hd("GPT 빈손 무료"), hd("고치기 전"), hd("고친 후")],
    [c("개발 단발 20 · AI 채점", { align: "left" }), c("13/20"), c("10/20"), c("12/20"), hi("20/20")],
    [c("개발 역할 대화 10 · AI 채점", { align: "left" }), c("7/10"), c("5/10"), c("6/10"), hi("10/10")],
    [c("홀드아웃 20 · 처음 보는 문항", { align: "left", bold: true }), c("8/20 (AI)"), c("6/20 (AI)"), c("없음"), hi("사람 17/20 · AI 18/20")],
  ], { x: 0.6, y: 1.85, w: 12.15, colW: [3.55, 2.0, 2.0, 1.8, 2.8], rowH: 0.5, fontSize: 15, fontFace: "Malgun Gothic", color: "1B2433",
       border: { type: "solid", color: "E9DDC2", pt: 0.75 }, fill: { color: "FFFFFF" }, valign: "middle", objectName: "답 채점 표" });
  text(s, "검색 적중 (정답 조각이 최종 자료에 들어왔나 · 프로그램이 셈)", { x: 0.6, y: 4.1, w: 8, h: 0.4, fontSize: 16, bold: true, color: C.accent3 });
  s.addTable([
    [hd("문항"), hd("고치기 전"), hd("고친 후")],
    [c("개발 단발 (정답 조각이 있는 17)", { align: "left" }), c("12/17"), hi("17/17")],
    [c("홀드아웃 (정답 조각이 있는 17)", { align: "left" }), c("없음"), hi("16/17")],
  ], { x: 0.6, y: 4.55, w: 7.4, colW: [3.8, 1.8, 1.8], rowH: 0.46, fontSize: 15, fontFace: "Malgun Gothic", color: "1B2433",
       border: { type: "solid", color: "E9DDC2", pt: 0.75 }, fill: { color: "FFFFFF" }, valign: "middle", objectName: "검색 적중 표" });
  card(s, 8.3, 4.1, 4.45, 2.6);
  text(s, runs([
    { text: "비교 조건", options: { bold: true, fontSize: 14, color: C.accent1 } },
    { text: "답변 모델: 고치기 전 gpt-4o-mini, 고친 후 gpt-6-luna", options: { fontSize: 12 } },
    { text: "GPT 빈손: ChatGPT 화면, 웹 검색 끔, 질문마다 새 임시 채팅(유료 GPT-6 Sol 생각 High · 무료 GPT-5.6 Luna Think)", options: { fontSize: 12 } },
    { text: "고친 후 개발은 같은 설정 3회: 단발 20·20·20, 대화 10·10·9", options: { fontSize: 12 } },
  ]), { x: 8.55, y: 4.25, w: 4.0, h: 2.35, paraSpaceAfter: 4 });
}

// ---------- 6. 가장 효과 컸던 변경 ----------
{
  const s = content("가장 효과 컸던 변경: 리랭커", 6,
    "09-29에 같은 단발 67문항, 같은 답변 모델로 리랭커 하나만 바꿔 쟀습니다. 통과는 Claude 채점, 검색 적중은 프로그램이 셌습니다. 그 뒤의 변경(답변 모델 교체, 최종 자료 6개, 전제 판정)은 여러 개를 한꺼번에 바꿨다고 밝힙니다.", "결과");
  const steps = [
    ["무엇이 문제였나", "검색이 질문과 낱말만 겹치는 조각을 가져와, 정답 조각이 최종 자료 4개 안에 못 들었다"],
    ["무엇을 바꿨나", "검색 후보 20개를 모델이 다시 읽고, 질문에 맞는 4개를 고르게 했다(리랭커)"],
    ["몇 점이 됐나", "단발 67문항 통과 47 → 56\n검색 적중 44 → 54 / 56"],
  ];
  steps.forEach(([h, b], i) => {
    const y = 1.5 + i * 1.75;
    card(s, 0.6, y, 6.3, 1.5);
    s.addShape(pres.shapes.OVAL, { x: 0.85, y: y + 0.45, w: 0.6, h: 0.6, fill: { color: i === 2 ? C.accent1 : C.accent3 }, line: { color: "FFFFFF" }, objectName: "단계 번호" });
    text(s, String(i + 1), { x: 0.85, y: y + 0.45, w: 0.6, h: 0.6, fontSize: 18, bold: true, color: C.background1, align: "center", valign: "middle" });
    text(s, h, { x: 1.7, y: y + 0.15, w: 5.0, h: 0.4, fontSize: 16, bold: true, color: i === 2 ? C.accent1 : C.accent3 });
    text(s, b, { x: 1.7, y: y + 0.55, w: 5.0, h: 0.9, fontSize: 15 });
  });
  s.addChart(pres.charts.BAR, [{ name: "단발 67문항 통과", labels: ["리랭커 없음", "리랭커 추가"], values: [47, 56] }], {
    x: 7.3, y: 1.5, w: 5.45, h: 4.6, barDir: "col", chartColors: ["5B6B7A", "A2412F"], invertedColors: ["5B6B7A"],
    showTitle: true, title: "단발 67문항 중 통과 (같은 문항·같은 답변 모델)", titleFontSize: 14, titleColor: "1B2433", titleFontFace: "+mn-lt",
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 16, dataLabelColor: "1B2433", dataLabelFontFace: "+mn-lt", dataLabelFontBold: true,
    valAxisMinVal: 0, valAxisMaxVal: 67, valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
    catAxisLabelColor: "1B2433", catAxisLabelFontSize: 14, catAxisLabelFontFace: "+mn-lt", showLegend: false, barGapWidthPct: 80, objectName: "리랭커 전후",
  });
  text(s, "통과: AI(Claude) 채점 · 검색 적중: 프로그램 · 2026-09-29", { x: 7.3, y: 6.2, w: 5.45, h: 0.35, fontSize: 12, color: C.accent4, align: "center" });
}

// ---------- 7. 아직 틀리는 것 ----------
{
  const s = content("아직 틀리는 것: 이름을 빼고 단서만 준 질문", 7,
    "홀드아웃에서 틀린 두 문항 모두 이름을 빼고 단서만 준 질문이고, 둘 다 검색 단계에서 놓쳤습니다. 받은 자료 안에서 지어낸 사실은 없습니다. 사람 채점은 정답 17 · 부분 2 · 오답 1이었고, 부분 하나는 노걸대 번역 표현(‘중국말을 옮긴 책’) 문제입니다.", "결과");
  const fails = [
    { q: "영조 때 군포를 줄여 생긴 재정 부족을 메우려 토지에 돈을 매기는 방안을 두고, 지방 선비·아전·군사들을 불러 물었다던데 각각 반응이 어땠어?",
      got: "물어본 장면 조각만 가져옴. 사람들이 답한 조각은 후보에도 없음",
      ans: "“각 집단의 답변은 기록에 없다” + 1750년 다른 기사",
      why: "답이 적힌 조각엔 ‘결전’·‘군포’ 같은 질문 낱말 없이 사람들의 말만 있어 검색이 멀다고 봄" },
    { q: "조선 전기에 관리들이 토지의 세금을 지나치게 거둬 백성이 괴로워하자 어떻게 바꿨어?",
      got: "세종 때 공법 논의(1430) 조각. 정답(성종 관수관급, 1470)은 4위였지만 고르지 않음",
      ans: "공법을 바꾼 방법으로 설명(다른 사건)",
      why: "단서가 같은 시대의 비슷한 세금 기사와 더 가까움. 같은 질문에 ChatGPT(검색 끔)도 공법으로 답함" },
  ];
  fails.forEach((f, i) => {
    const x = 0.6 + i * 6.2;
    card(s, x, 1.5, 5.95, 5.15);
    text(s, [{ text: "질문  ", options: { bold: true, color: C.accent4 } }, { text: f.q }], { x: x + 0.3, y: 1.7, w: 5.35, h: 1.3, fontSize: 15 });
    [["가져온 조각", f.got, C.accent3], ["답", f.ans, C.text1], ["틀린 이유(추정)", f.why, C.accent1]].forEach(([h, b, col], j) => {
      const y = 3.1 + j * 1.15;
      text(s, h, { x: x + 0.3, y, w: 5.35, h: 0.35, fontSize: 14, bold: true, color: col });
      text(s, b, { x: x + 0.3, y: y + 0.35, w: 5.35, h: 0.75, fontSize: 14 });
    });
  });
}

// ---------- 8. 한계와 발전 방향 ----------
{
  const s = content("한계와 발전 방향", 8,
    "발전 방향은 아직 하지 않은 일입니다. '구현했다'고 말하지 않고 '다음에 할 것'으로 말합니다.", "결과");
  const lim = [
    ["이름을 빼면 약하다", "홀드아웃 이름을 뺀 질문 1/3. 답이 같은 기사의 다른 조각에 있거나 비슷한 기사가 있으면 놓친다"],
    ["답이 느리다", "질문 하나에 10-20초. 검색 → 자료 고르기 → 답 쓰기 → 근거 대조를 차례로 부른다"],
    ["자료 범위", "실록 기사 132건뿐이고, 번역은 AI 초안이라 일부만 사람이 검수했다"],
  ];
  const next = [
    ["앞뒤 조각 보태기", "정답 조각 하나를 찾으면 같은 기사의 앞뒤 조각을 자료 고르기 후보에 더한다"],
    ["질문 바꿔 쓰기", "단서만 준 질문을 검색용으로 사건 이름 중심으로 바꿔 쓴다"],
    ["번역 보완 뒤 다시 재기", "검수에서 나온 번역·풀이를 고친 뒤 개발 문항을 다시 측정하고, 사건을 늘린다"],
  ];
  [[lim, "한계", C.accent1, 0.6], [next, "다음에 할 것", C.accent3, 6.8]].forEach(([list, head, col, x]) => {
    text(s, head, { x, y: 1.45, w: 5.95, h: 0.5, fontSize: 22, bold: true, color: col, fontFace: "Batang" });
    list.forEach(([h, b], i) => {
      const y = 2.1 + i * 1.55;
      card(s, x, y, 5.95, 1.38);
      text(s, h, { x: x + 0.3, y: y + 0.15, w: 5.35, h: 0.4, fontSize: 17, bold: true });
      text(s, b, { x: x + 0.3, y: y + 0.58, w: 5.35, h: 0.75, fontSize: 14, color: C.text1 });
    });
  });
}

// ---------- 결과물: 역사 취재록 ----------
pres.addSection({ title: "시연" });
{
  const s = content("결과물: 역사 취재록", "史",
    "취재하기 화면은 서비스 시연입니다. 인물별 자료 제한, '대화하듯 짧게' 말투, 추천 질문은 측정한 적이 없으므로 성능 숫자로 말하지 않습니다. 숫자는 '실록에 묻기'와 앞의 측정표로만 말합니다.", "시연");
  s.addImage({ path: IMG("취재화면_계유정난.png"), x: 0.6, y: 1.45, w: 7.3, h: 5.11, objectName: "취재 화면" });
  const modes = [
    ["취재하기", "사건 속 인물을 그 시점 그대로 인터뷰. 근거로 확인된 내용만 취재 수첩에 쌓인다(언문 논쟁 · 계유정난)"],
    ["실록에 묻기", "측정한 설정 그대로 사실 질문. 없는 내용은 지어내지 않는다"],
    ["기출처럼 풀기", "실록 사료와 우리 번역으로 새로 만든 5지선다"],
  ];
  modes.forEach(([h, b], i) => {
    const y = 1.45 + i * 1.5;
    card(s, 8.2, y, 4.55, 1.35);
    text(s, h, { x: 8.45, y: y + 0.12, w: 4.1, h: 0.4, fontSize: 17, bold: true, color: C.accent3 });
    text(s, b, { x: 8.45, y: y + 0.52, w: 4.1, h: 0.8, fontSize: 13 });
  });
  text(s, "취재하기의 인물 말투·추천 질문은 측정하지 않은 서비스 화면", { x: 8.2, y: 6.0, w: 4.55, h: 0.55, fontSize: 12, color: C.accent1 });
}

// ---------- 9. 시연 ----------
{
  const s = content("시연: 질문 세 개", 9,
    "녹화본을 틉니다. 세 질문 모두 홀드아웃(고치는 데 쓰지 않은 문항)이고 측정 때 사람·AI 모두 정답이었습니다. 답변 모델은 같은 질문에도 답이 조금씩 달라질 수 있어 녹화 전에 리허설했습니다. 자료 없음 질문은 'GPT는 알고 우리는 모른다'가 아니라, 실록 밖 현대 사실은 지어내지 않는다는 뜻으로 설명합니다.", "시연");
  const qs = [
    ["잘 되는 질문", "《삼강행실도》를 처음 엮을 때 효자·충신·열녀의 사례는 각각 몇 명씩 골랐어?", "각각 110명 + 근거 기사"],
    ["함정 질문", "숙종 때 금위영에 대장을 따로 두기로 했다던데, 그때 대장으로 누구를 임명했어?", "따로 두지 않고 병조판서가 겸함, 따로 둔 것은 제조"],
    ["모르는 걸 모른다고", "조선 통신사 기록물이 유네스코 세계기록유산에 등재된 해는 언제야?", "자료에 등재 연도가 없어 확인되지 않는다"],
  ];
  qs.forEach(([tag, q, a], i) => {
    const y = 1.5 + i * 1.72;
    card(s, 0.6, y, 6.6, 1.55);
    text(s, tag, { x: 0.9, y: y + 0.12, w: 6.0, h: 0.35, fontSize: 14, bold: true, color: C.accent1 });
    text(s, q, { x: 0.9, y: y + 0.47, w: 6.0, h: 0.65, fontSize: 15 });
    text(s, "→ " + a, { x: 0.9, y: y + 1.1, w: 6.0, h: 0.38, fontSize: 14, color: C.accent3, bold: true });
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.5, y: 1.5, w: 5.25, h: 5.0, rectRadius: 0.08, fill: { color: C.text2 }, line: { color: C.accent4, width: 1.25, dashType: "dash" }, objectName: "녹화 자리" });
  text(s, runs([
    { text: "시연 녹화본 넣을 자리", options: { bold: true, fontSize: 18, color: "F3ECDD" } },
    { text: "실록에 묻기 질문 세 개 → 인물 취재 짧은 장면", options: { fontSize: 14, color: "E9DDC2" } },
  ]), { x: 7.8, y: 3.3, w: 4.65, h: 1.4, align: "center", valign: "middle" });
}

// ---------- 10. 마무리 ----------
pres.addSection({ title: "마무리" });
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "마무리" });
  s.addText("발표 숫자 세 개", { placeholder: "title", y: 0.5, h: 1.0, fontSize: 36 });
  const nums = [
    ["① 왜 필요한가", "8/20 → 17/20", "처음 보는 홀드아웃 20문항\nGPT 빈손(유료, 웹 검색 끔) → 우리(사람 채점)"],
    ["② 무엇을 했나", "47 → 56/67", "리랭커 하나만 추가\n같은 개발 단발 67문항 · 같은 답변 모델"],
    ["③ 남은 한계", "1/3", "홀드아웃에서 이름을 빼고 단서만 준 질문\n두 오답 모두 검색에서 놓침"],
  ];
  nums.forEach(([h, n, b], i) => {
    const x = 0.8 + i * 4.0;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.9, w: 3.7, h: 4.3, rectRadius: 0.08, fill: { color: "1B2A3D" }, line: { color: "B8913F", width: 0.75 }, objectName: "숫자 카드" });
    text(s, h, { x: x + 0.3, y: 2.15, w: 3.1, h: 0.45, fontSize: 18, bold: true, color: "B8913F" });
    text(s, n, { x: x + 0.1, y: 2.8, w: 3.5, h: 1.2, fontSize: 34, bold: true, color: "FFFFFF", align: "center", valign: "middle", fontFace: "Batang" });
    text(s, b, { x: x + 0.3, y: 4.3, w: 3.1, h: 1.7, fontSize: 14, color: "E9DDC2" });
  });
  text(s, "실록에 적힌 것만 말하고, 없는 것은 없다고 하는 역사 챗봇 · 역사 취재록", { x: 0.8, y: 6.55, w: 11.7, h: 0.4, fontSize: 14, color: "B8913F" });
  s.addNotes("세 숫자를 다시. ① 처음 보는 문항에서 GPT 빈손 8/20, 우리 17/20(사람 채점). ② 가장 효과 컸던 변경은 리랭커, 47에서 56으로. ③ 아직 약한 것은 이름을 빼고 단서만 준 질문(1/3), 검색 단계에서 놓친다. 질의응답으로 넘어갑니다.");
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("만듦:", OUT);
})();
