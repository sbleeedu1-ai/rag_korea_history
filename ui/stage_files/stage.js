// 취재 화면 렌더러(CCv2). Python이 data로 화면 값을 모두 내려보내고, 버튼은 setTriggerValue("action", {...})로 알린다.
// 근거 기사·취재 의뢰·대화 기록·설정 창과 용어집은 받은 data로 이 안에서 연다(추가 호출 없음).
// data 안의 *_html 값은 Python이 이스케이프하고 용어 표시만 붙인 것이다. 그 밖의 글자는 여기서 이스케이프한다.

const UI = new WeakMap()
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]))

function ensureFonts() {
  // 섀도 DOM 안의 @font-face는 등록되지 않으므로 문서 head에 한 번만 넣는다(없어도 시스템 글꼴로 보임)
  // 본문 Pretendard(OFL, 작은 글씨·어두운 바탕에서 또렷함), 제목·이름은 고운바탕(OFL). 연결이 없으면 시스템 글꼴(사용자 10-12)
  if (document.getElementById("sillok-fonts")) return
  for (const [id, href] of [["sillok-fonts", "https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@400;700&family=Noto+Sans+KR:wght@400;500;700&display=swap"],
                            ["sillok-pretendard", "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"]]) {
    const link = document.createElement("link")
    link.id = id; link.rel = "stylesheet"; link.href = href
    document.head.appendChild(link)
  }
}

export default function (component) {
  const { data, parentElement, setTriggerValue, setStateValue } = component
  const app = parentElement.querySelector("#app")
  const layer = parentElement.querySelector("#layer")
  const measure = parentElement.querySelector("#measure")
  if (!app || !data) return
  ensureFonts()

  let ui = UI.get(parentElement)
  if (!ui) {
    ui = { json: "", tab: "record", open: {}, openMat: {}, overlay: null, drawer: null, page: 0, dlgId: "", busy: false, memoTimer: null }
    UI.set(parentElement, ui)
  }
  const json = JSON.stringify(data)
  const changed = json !== ui.json
  ui.json = json
  if (changed) ui.busy = false
  const A = data.assets || {}

  const send = (action) => {
    if (ui.busy) return
    if (action.type === "ask" || action.type === "retry") {
      ui.busy = true; ui.busyAt = Date.now(); render()
      clearInterval(ui.busyTimer)
      ui.busyTimer = setInterval(() => {
        const el = app.querySelector(".elapsed")
        if (!ui.busy || !el) { clearInterval(ui.busyTimer); return }
        el.textContent = `${Math.floor((Date.now() - ui.busyAt) / 1000)}초`
      }, 1000)
    }
    setTriggerValue("action", { ...action, at: Date.now() })
  }

  // ---------- 조각 ----------
  const img = (name, cls = "") => (A[name] ? `<img class="${cls}" src="${A[name]}" alt="">` : "")
  const has = (name) => (A[name] ? " has-img" : "")

  function topbar() {
    return `<header class="top"><div class="brand">역사 취재록</div>
      <nav class="menu"><button data-act="events">← 사건 목록</button><button data-act="glossary">용어집</button><button data-act="history">대화 기록</button><button data-act="settings">설정 ${img("icon_gear")}</button></nav></header>`
  }

  function notebook() {
    const nb = data.notebook || {}
    let body = ""
    if (ui.tab === "record") {
      // 기록 칸에는 근거로 확인된 목표만(사용자 10-12: 메모 칸은 '내 메모' 탭으로). 갈래가 확인되면 미리 쓴 요약을 보이고
      // 인물의 실제 말과 근거 기사는 펼쳐서 본다. 확인된 항목은 접혀 있어도 색으로 구분한다
      const goals = nb.goals || []
      // 대화 상대가 바뀌면 그 사람이 맡은 목표만 펼친다(사용자 10-13). 그 뒤 직접 접고 편 것은 다음에 바뀔 때까지 그대로
      if (nb.focusWho !== ui.focusWho) {
        ui.focusWho = nb.focusWho
        if (nb.focus) ui.open = Object.fromEntries(goals.map((g) => [g.id, g.id === nb.focus]))
      }
      const doneN = goals.filter((g) => g.done).length
      body += `<div class="nb-sub">이번 취재<span class="prog">${doneN} / ${goals.length} 확인</span></div>`
      goals.forEach((g, i) => {
        const open = ui.open[g.id] ?? (i === 0 || g.entries.length > 0)
        const entries = g.entries.map((e) => `<div class="entry"><b class="lab">✓ ${esc(e.label)}</b><div class="sum">${esc(e.summary)}</div>
            <details><summary>${esc(e.who)}의 말 보기</summary><q>${esc(e.text)}</q><div class="cite">${esc(e.cite)}</div></details></div>`).join("")
        const pending = g.pending.map((p) => `<div class="pend">○ ${esc(p)} · 아직</div>`).join("")
        const hint = g.done || g.entries.length ? "" : `<div class="muted">${esc(g.hint)}</div>`
        const fresh = ui.freshGoal === g.id && Date.now() < (ui.unrollUntil || 0) ? " fresh" : ""
        const state = g.done ? " done" : g.count ? " part" : ""
        body += `<div class="goal-item${open ? " open" : ""}${state}${fresh}"><button class="goal-head" data-act="goal" data-id="${esc(g.id)}">
            <span class="no">${g.done ? "✓" : String(i + 1).padStart(2, "0")}</span><span>${esc(g.title)}</span>
            <span class="cnt">${g.count} / ${g.total}</span><span class="chev">${open ? "▾" : "›"}</span></button>
            ${open ? `<div class="goal-body">${entries}${pending}${hint}</div>` : ""}</div>`
      })
      body += `<div class="nb-foot">${img("icon_books")}<span>근거로 확인된 내용만 이곳에 쌓입니다.</span></div>`
    } else if (ui.tab === "material") {
      // 목표 갈래별 묶음(눌러서 펼침), 답이 기댄 구절은 형광펜(10-12 사용자). html은 Python에서 이스케이프한 우리 번역
      const groups = nb.materials || []
      body += groups.length ? groups.map((g) => `<details class="mgroup"${ui.openMat && ui.openMat[g.label] ? " open" : ""} data-label="${esc(g.label)}">
          <summary>${esc(g.label)}<span>${g.items.length}</span></summary>
          ${g.items.map((m) => `<div class="mat"><b>${esc(m.title)}</b><span class="muted">${esc(m.date)}</span><div class="ev">${m.html}</div></div>`).join("")}</details>`).join("")
        : `<p class="muted">근거로 확인된 실록 기사가 목표별로 여기에 모입니다.</p>`
    } else {
      const marks = nb.marks || []
      body += `<div class="nb-sub">내 메모 ${img("icon_pencil")}</div><textarea class="memo" placeholder="궁금한 점을 적어보세요."></textarea>`
      body += `<div class="nb-sub memo-head">담아 둔 답</div>`
      body += marks.length ? marks.map((m) => `<div class="mat"><b>${esc(m.who)}</b><span class="muted">${esc(m.q)}</span><div>${esc(m.a)}</div></div>`).join("")
        : `<p class="muted">대화창의 '내 메모에 담기'를 누른 답이 여기에 모입니다.</p>`
      body += `<p class="muted">메모와 담아 둔 답은 내 생각을 모으는 칸이며, 확인된 사실로 바뀌지 않습니다.</p>`
    }
    const tab = (id, label) => `<button class="${ui.tab === id ? "on" : ""}" data-act="tab" data-id="${id}">${label}</button>`
    return `<aside class="notebook${has("notebook")}"><div class="nb-title">취재 수첩</div>
      <div class="tabs">${tab("record", "기록")}${tab("material", "자료")}${tab("mine", "내 메모")}</div><div class="nb-body">${body}</div>
      ${data.nextWhen === null && data.scene === 3 ? `<button class="nb-finish${data.nextHi ? " hi" : ""}" data-act="next" ${ui.busy ? "disabled" : ""}>${esc(data.nextLabel)}</button>` : ""}</aside>`
  }

  // ---------- 취재 목표 두루마리(사용자 10-12) ----------
  // 평소에는 두 축이 붙은 닫힌 두루마리(따로 그린 아이콘 대신 같은 그림이 그대로 움직임). 마우스를 올리면(휴대폰은 한 번 누르면) 양끝 축 사이로 종이가 오른쪽으로 펼쳐지며 목표가 보이고,
  // 펼친 상태에서 누르면 취재 의뢰 창. 처음 들어올 때·인물을 바꿔 목표가 바뀔 때·장면이 바뀔 때 저절로 잠깐 펼치고,
  // 목표 하나를 확인하면 '✓ 목표 확인'으로 펼친다. 펼친 종이는 위에 떠서 다른 칸을 밀지 않는다.
  const AUTO_MS = 4000, DONE_MS = 4000   // 저절로 펼침은 안내와 같은 4초(사용자 10-12)
  function scrollInk() {
    // 확인 순간에는 붉은 '확인' 도장이 찍힌다(사용자 10-12: 확인 펼침이 눈에 덜 띔)
    if (ui.doneTitle) return `<small>${esc(ui.doneKind || "목표 확인")}</small><b>✓ ${esc(ui.doneTitle)}</b><span class="stamp">확인</span>`
    return `<small>취재 목표</small><b>${esc(data.goal)}</b>`
  }
  function autoUnroll(ms, doneTitle = null, kind = null, goalId = null) {
    ui.unrollUntil = Date.now() + ms
    ui.doneTitle = doneTitle
    ui.doneKind = kind
    ui.freshGoal = goalId
    ui.unrollPending = true   // 그린 뒤 다음 프레임에 펼쳐야 애니메이션이 보인다
  }
  function watchGoal() {
    const key = `${data.scene}|${data.goal}`
    if (key !== ui.goalKey) { ui.goalKey = key; autoUnroll(AUTO_MS) }
    // 줄기가 다 채워지면 '목표 확인', 갈래 하나만 새로 채워지면 '기록 확인'
    const goals = (data.notebook && data.notebook.goals) || []
    const done = goals.filter((g) => g.done).map((g) => g.id)
    const parts = goals.flatMap((g) => g.entries.map((e) => [g.id, e.label]))
    if (ui.doneSeen) {
      const newGoal = goals.find((g) => g.done && !ui.doneSeen.includes(g.id))
      const newPart = parts.find(([, label]) => !ui.partSeen.includes(label))
      if (newGoal) autoUnroll(DONE_MS, newGoal.title, "목표 확인", newGoal.id)
      else if (newPart) autoUnroll(DONE_MS, newPart[1], "기록 확인", newPart[0])
    }
    ui.doneSeen = done
    ui.partSeen = parts.map(([, label]) => label)
  }
  function playUnroll() {
    const el = app.querySelector(".goal")
    const left = (ui.unrollUntil || 0) - Date.now()
    if (!el || left <= 0) return
    if (ui.unrollPending) { ui.unrollPending = false; requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add("open"))) }
    else el.classList.add("open")
    clearTimeout(ui.unrollTimer)
    ui.unrollTimer = setTimeout(() => {
      const cur = app.querySelector(".goal")
      if (cur && !ui.tapOpen) cur.classList.remove("open")
      if (ui.doneTitle) setTimeout(() => {   // 다 말린 뒤 원래 목표 문구로 되돌린다
        ui.doneTitle = null
        const ink = app.querySelector(".goal .ink"); if (ink) ink.innerHTML = scrollInk()
      }, 700)
    }, left)
  }

  function head() {
    const roller = (side) => `<i class="roller ${side}${has("scroll_roller")}"></i>`
    return `<div class="head">
      <button class="goal${ui.tapOpen ? " open" : ""}" data-act="brief" aria-label="취재 목표 · ${esc(data.goal)} (펼친 뒤 누르면 취재 의뢰)">
        <span class="unroll">${roller("l")}<span class="sheet"><span class="paper${has("scroll_paper")}"><span class="ink">${scrollInk()}</span></span></span>${roller("r")}</span>
      </button>
      ${title()}</div>`
  }

  function title() {
    // 오른쪽 위 사건 제목과 그 아래 날짜(테두리 없는 읽기 전용, 사용자 10-12). 장면 번호는 쓰지 않고 날짜만:
    // 인물은 이 날까지의 일만 알기 때문에 날짜가 바뀌는 것으로 시간이 흐른 것을 보인다. 장면이 바뀌면 날짜가 잠깐 금빛
    const cur = data.scene || 1
    const flash = ui.lastScene !== undefined && ui.lastScene !== cur ? " flash" : ""
    ui.lastScene = cur
    return `<div class="title"><h1>${esc(data.title)}</h1>
      <p class="date${flash}" aria-label="${esc(data.sceneLabel)}"><span class="line${has("divider")}"></span>${esc(data.date)}${timeNav()}</p></div>`
  }

  function timeNav() {
    // 장면 넘기기 = 시간 넘기기라 날짜 옆에 둔다(사용자 10-12). 가는 날짜를 버튼에 쓴다. 마지막 장면의 '수첩 펼치기'는 수첩 맨 아래
    const dis = ui.busy ? "disabled" : ""
    // 버튼 글자는 짧게(날짜까지 넣으면 글자가 작아져 사용자 10-12 지적). 가는 날짜는 마우스를 올리면 보인다
    const back = data.backWhen ? `<button class="tnav" data-act="back" ${dis} title="${esc(data.backWhen)} 면담으로 돌아가기">← 면담으로</button>` : ""
    const next = data.nextWhen ? `<button class="tnav next${data.nextHi ? " hi" : ""}" data-act="next" ${dis} title="${esc(data.nextWhen)}(으)로">다음 장면 →</button>` : ""
    return back || next ? `<span class="tnavs">${back}${next}</span>` : ""
  }

  function cast() {
    if (!data.people) {
      const banner = [].concat(data.banner || []).map(esc).join("<br>")
      return `<div class="record"><div class="card-rec panel${has("panel_dark")}">${banner}</div>
</div>`
    }
    const cards = data.people.map((p) => `<button class="card${p.active ? " on" : ""}" data-act="pick" data-who="${esc(p.name)}" ${p.active ? 'aria-pressed="true"' : ""}
        title="${esc(p.name)} · ${esc(p.moment)}의 면담"><div class="inner">${p.portrait ? `<img src="${p.portrait}" alt="${esc(p.name)} 창작 삽화">` : ""}</div>
        ${img("frame_portrait", "frame")}<div class="plate${has("nameplate")}"><b>${esc(p.name)}</b>
        <span class="pill ${p.active ? "on" : "off"}">${p.active ? "대화 중" : "선택하여 취재"}</span></div></button>`).join("")
    const line = (side) => `<span class="line ${side}${has("divider")}"></span>`
    return [`<div class="pick">${line("l")}<span class="dia">◈</span>취재 대상 선택<span class="dia">◈</span>${line("r")}</div>`, `<div class="cast">${cards}</div>`]
  }

  function dialog() {
    const d = data.dialogue || {}
    const icon = d.narrator ? img("icon_narrator") : ""
    const q = `<div class="dlg-q"${d.question ? ` title="${esc(d.question)}"` : ""}>${d.question ? `나의 질문 · ${esc(d.question)}` : ""}</div>`
    let text
    // 기다리는 동안: 무엇을 하는지(단계)와 흐른 시간. 단계는 차례만 보여 주고 지금 어느 단계인지는 표시하지 않는다
    if (ui.busy) text = `<span class="wait">${esc(data.waitText || "답을 기다리고 있습니다")}<i>…</i></span>
      <span class="steps">자료 찾기 → 기록 고르기 → 답 쓰기 → 근거 대조 · <b class="elapsed">${Math.floor((Date.now() - (ui.busyAt || Date.now())) / 1000)}초</b></span>`
    else text = ""   // 쪽 나누기 뒤 채운다
    const acts = d.canEvidence
      ? `<div class="dlg-actions"><button data-act="evidence" ${ui.busy ? "disabled" : ""}>${img("icon_doc")}근거 보기</button>
         <button data-act="mark" ${d.marked || ui.busy ? "disabled" : ""}>${img("icon_bookmark")}${d.marked ? "내 메모에 담음" : "내 메모에 담기"}</button></div>`
      : ""
    const fail = data.failure && !ui.busy
      ? `<div class="fail">답을 가져오지 못했습니다. 보낸 질문과 앞선 대화는 그대로 있습니다.<button data-act="retry">같은 질문 다시 보내기</button></div>` : ""
    // 머리 줄(이름표·나의 질문·버튼·태그) → 답 칸(정해진 줄 수) → 쪽 표시 띠. 버튼은 답 글자 줄을 차지하지 않는다
    return `<section class="dialog${has("panel_paper")}"><div class="dlg-head"><div class="speaker${has("nameplate")}">${icon}<span>${esc(d.speaker)}</span></div>
      ${q}${acts}<span class="nature">${esc(d.tag)}</span></div>
      <div class="dlg-text" data-act="page">${text}</div><div class="page"></div>${fail}</section>`
  }

  function asks() {
    // 한 번에 qLimit개만(처음 1개, 그 뒤 2개). '다른 질문 ↻'으로 남은 추천을 돌려 본다
    const all = data.questions || [], lim = data.qLimit || 2
    const qKey = all.map((q) => q.qid).join(",")
    if (qKey !== ui.qKey) { ui.qKey = qKey; ui.qShift = 0 }
    const shown = all.length <= lim ? all : Array.from({ length: lim }, (_, i) => all[(ui.qShift + i) % all.length])
    const more = all.length > lim ? `<button class="chip" type="button" data-act="more-q" ${ui.busy ? "disabled" : ""}>다른 질문 ↻</button>` : ""
    const qs = shown.map((q, i) => `<button class="q" data-act="ask" data-qid="${esc(q.qid)}" data-text="${esc(q.text)}" ${ui.busy ? "disabled" : ""}>
        <span class="n">${i + 1}</span><span class="t">${esc(q.text)}</span><span class="c">›</span></button>`).join("")
    const chip = data.narratorChip ? `<button class="chip" data-act="narrator" ${ui.busy ? "disabled" : ""}>${img("icon_book")}${esc(data.narratorChip)}</button>` : ""
    const empty = all.length ? "" : `<p class="muted" style="color:#aab">추천 질문을 모두 물었습니다. 궁금한 것을 직접 적어 보세요.</p>`
    return `<section class="ask panel${has("panel_dark")}"><div class="ask-head"><h2>무엇을 물어볼까요?</h2><span class="ask-tools">${more}${chip}</span></div>${qs}${empty}
      <form class="inrow" data-form="ask"><div class="inbox">${img("icon_pencil")}<input name="q" autocomplete="off" placeholder="${esc(data.inputHint || "직접 질문을 입력하세요…")}" ${ui.busy ? "disabled" : ""}></div>
        <button class="send" type="submit" ${ui.busy ? "disabled" : ""}>질문하기</button>
</form></section>`
  }

  // ---------- 덮는 창 ----------
  function overlay() {
    const o = ui.overlay
    if (!o) return ""
    const modal = (title, body, small = false) => `<div class="overlay" data-act="close"><div class="modal${small ? " small" : ""}${has("panel_paper")}" data-stop="1">
        <div class="modal-head"><h3>${title}</h3><button class="x" data-act="close">✕</button></div><div class="modal-body">${body}</div></div></div>`
    if (o === "brief") {
      const b = data.brief || {}
      const rows = (b.items || []).map(([no, who, q, when]) => `<div class="brief-row"><span class="no">${esc(no)}</span><div><b>${esc(q)}</b><p>${esc(who)} · ${esc(when)}</p></div></div>`).join("")
      return modal("취재 의뢰", `<p class="brief-text">${esc(b.intro)}</p>${rows}<p class="muted">${esc(b.note)}</p>`)
    }
    if (o === "evidence") {
      const cards = (data.dialogue && data.dialogue.cards) || []
      const body = cards.length ? cards.map((c) => `<div class="ev"><h4>${esc(c.title)}</h4><div class="meta">${esc(c.date)} · 화자 ${esc(c.speaker)} · 우리 번역(한문 원문에서 직접 번역한 AI 초안, 일부 사람 검수)</div>
          <div>${c.translation_html}</div><details><summary>한문 원문 보기</summary>${esc(c.original)}</details><a href="${esc(c.url)}" target="_blank" rel="noopener">국사편찬위원회 실록 원문 ↗</a><div class="meta">원문 출처: 국사편찬위원회 「조선왕조실록」(공공누리 제1유형)</div></div>`).join("")
        : `<p>이 답에는 실록 기록과 직접 이어진 문장이 없습니다. 기록을 풀어 쓴 설명이나 재구성한 말일 수 있어요.</p>`
      return modal("근거 기사", body)
    }
    if (o === "history") {
      const h = data.history || []
      const body = h.length ? h.map((x) => `<div class="hist"><div class="meta">${esc(x.scene)} · ${esc(x.speaker)}</div><div class="hq">나의 질문 · ${esc(x.q)}</div><div>${x.a_html}</div></div>`).join("")
        : `<p class="muted">아직 나눈 대화가 없습니다.</p>`
      return modal("대화 기록", body)
    }
    if (o === "settings") {
      const s = data.settings || {}
      const body = `<div class="set-row"><div><b>실제 답변 켜기</b><div class="muted">API 비용 발생 · 질문 하나에 답변·자료 고르기·근거 대조 호출</div>
          ${s.problem ? `<div class="muted" style="color:#8a3a2a">${esc(s.problem)}</div>` : ""}</div>
          <button class="toggle${s.live ? " on" : ""}" data-act="live" ${s.problem ? "disabled" : ""} aria-label="실제 답변 켜기"></button></div>
        <div class="set-row"><span class="muted">${esc(s.measured)}</span></div>`
      return modal("설정", body, true)
    }
    return ""
  }

  function drawer() {
    if (ui.drawer === null) return ""
    const items = (data.terms || []).map((t) => `<div class="gi${ui.drawer === t.term ? " hit" : ""}"><b>${esc(t.term)}</b><p>${esc(t.desc)}</p></div>`).join("")
    return `<aside class="drawer" data-stop="1"><div class="modal-head"><h3>용어집</h3><button class="x" data-act="drawer-close">✕</button></div>
      <p class="muted">답에 밑줄 친 말을 누르면 여기서 뜻을 볼 수 있어요. 이번 자료를 읽는 데 필요한 범위의 짧은 풀이입니다.</p>${items}</aside>`
  }

  // ---------- 대화 쪽 나누기(스크롤 대신 ▼) ----------
  function paginate() {
    const box = app.querySelector(".dlg-text")
    const pager = app.querySelector(".page")
    const d = data.dialogue || {}
    if (!box || ui.busy) return
    const sentences = d.sentences || []
    const id = `${d.id}`
    if (id !== ui.dlgId) { ui.dlgId = id; ui.page = 0 }
    measure.style.width = box.clientWidth + "px"
    measure.style.font = getComputedStyle(box).font
    measure.style.lineHeight = getComputedStyle(box).lineHeight
    const limit = box.clientHeight   // 글자 크기가 소수라 줄 높이 합이 반올림되므로 2px 여유를 둔다(아래)
    const pages = []
    let cur = ""
    for (const s of sentences) {
      const next = cur ? cur + "<br>" + s : s   // 문장마다 줄을 바꿔 대화처럼(사용자 10-12)
      measure.innerHTML = next
      if (cur && measure.scrollHeight > limit + 2) { pages.push(cur); cur = s } else { cur = next }
    }
    if (cur || !pages.length) pages.push(cur)
    ui.page = Math.min(ui.page, pages.length - 1)
    box.innerHTML = pages[ui.page]
    if (!ui.hintAt && box.querySelector(".term")) { ui.hintAt = Date.now(); showHint() }   // 밑줄 친 말이 처음 보일 때 한 번만 알린다
    box.classList.toggle("more", pages.length > 1)
    box.dataset.pages = pages.length
    pager.innerHTML = pages.length > 1 ? `${ui.page + 1} / ${pages.length} ${ui.page < pages.length - 1 ? '<span class="arrow">▼</span>' : ""}` : ""
  }

  // 용어집 안내: 4초 동안 위쪽 메뉴 '용어집' 바로 아래에. 그 사이 화면을 다시 그려도 이어서 보이게 남은 시간만큼 다시 붙인다
  const HINT_MS = 4000   // 6초는 길다는 사용자 지적(10-12). 마우스를 올리면 바로 사라진다
  function showHint() {
    const elapsed = Date.now() - (ui.hintAt || 0)
    if (!ui.hintAt || elapsed >= HINT_MS || layer.querySelector(".hint")) return
    const tip = document.createElement("div")
    tip.className = "hint"
    tip.textContent = "밑줄 친 말을 누르면 뜻이 보여요"
    tip.style.animationDelay = `-${elapsed}ms`
    layer.appendChild(tip)
    const btn = app.querySelector(".menu [data-act=glossary]")
    if (btn) {   // 화살표는 '용어집' 가운데를 가리키고, 상자는 화면 오른쪽 밖으로 나가지 않게
      const r = btn.getBoundingClientRect(), mid = r.left + r.width / 2
      const left = Math.max(8, Math.min(mid - 30, innerWidth - tip.offsetWidth - 8))
      tip.style.top = `${r.bottom + 8}px`
      tip.style.left = `${left}px`
      tip.style.setProperty("--arrow", `${mid - left - 6}px`)
    }
    tip.onmouseenter = () => { ui.hintAt = 1; tip.remove() }   // 다시 그려도 되살아나지 않게 끝난 것으로
    setTimeout(() => tip.remove(), HINT_MS - elapsed)
  }

  // ---------- 그리기 ----------
  function render() {
    const vars = { "--img-notebook": "notebook", "--img-panel": "panel_dark", "--img-paper": "panel_paper", "--img-plate": "nameplate", "--img-divider": "divider",
      "--img-roller": "scroll_roller", "--img-scroll-paper": "scroll_paper" }
    // 덮는 창은 #app 밖(#layer)에 그려지므로 두 곳 모두에 건다(한 곳에만 걸면 창 테두리·바탕이 비어 투명해짐)
    for (const [v, n] of Object.entries(vars)) for (const el of [app, layer]) el.style.setProperty(v, A[n] ? `url(${A[n]})` : "none")
    const memoFocused = parentElement.activeElement && parentElement.activeElement.classList && parentElement.activeElement.classList.contains("memo")
    if (memoFocused) return   // 메모를 쓰는 중에는 다시 그리지 않는다(글자 위치가 튀지 않게)
    const typed = app.querySelector("input[name=q]")?.value || ""
    watchGoal()
    const castParts = cast()
    const middle = Array.isArray(castParts) ? castParts.join("") : castParts
    app.innerHTML = `${topbar()}${notebook()}<main class="stage" style="background-image:${data.background ? `url(${data.background})` : "none"}">
      ${head()}${Array.isArray(castParts) ? "" : '<div></div>'}${middle}${dialog()}${asks()}</main>`
    layer.innerHTML = `${overlay()}${drawer()}`   // 실제 답변 표시는 두지 않음. 켜짐은 설정 창 스위치로 확인(10-12 사용자 "굳이 필요 없어보임 걍 빼셈")
    showHint()
    playUnroll()
    const memo = app.querySelector("textarea.memo")
    if (memo) memo.value = data.memo || ""
    const input = app.querySelector("input[name=q]")
    if (input && typed) input.value = typed
    paginate()   // 바로 한 번(레이아웃은 동기로 계산됨), 글꼴을 다 받은 뒤 한 번 더
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => paginate())
  }

  // ---------- 행동 ----------
  const onClick = (e) => {
    const termEl = e.target.closest(".term")
    if (termEl) { ui.drawer = termEl.dataset.term; render(); return }
    const el = e.target.closest("[data-act]")
    if (!el) return
    const act = el.dataset.act
    if (act === "close" && e.target.closest("[data-stop]") && !e.target.closest(".x")) return
    switch (act) {
      case "tab": ui.tab = el.dataset.id; render(); break
      case "goal": { const id = el.dataset.id; const cur = app.querySelector(`.goal-head[data-id="${id}"]`).parentElement.classList.contains("open"); ui.open[id] = !cur; render(); break }
      case "brief": {
        // 마우스가 없는 화면(휴대폰)은 첫 번째 누름으로 펼치고, 펼친 상태에서 다시 누르면 의뢰 창
        const goal = el.closest(".goal")
        if (goal && matchMedia("(hover: none)").matches && !goal.classList.contains("open")) {
          goal.classList.add("open"); ui.tapOpen = true
          clearTimeout(ui.tapTimer)
          ui.tapTimer = setTimeout(() => { ui.tapOpen = false; app.querySelector(".goal")?.classList.remove("open") }, 5000)
          break
        }
        ui.tapOpen = false; ui.overlay = act; render(); break
      }
      case "evidence": case "history": case "settings": ui.overlay = act; render(); break
      case "close": ui.overlay = null; render(); break
      case "glossary": ui.drawer = ""; render(); break
      case "drawer-close": ui.drawer = null; render(); break
      case "more-q": ui.qShift = (ui.qShift || 0) + (data.qLimit || 2); render(); break
      case "page": { const n = Number(el.dataset.pages || 1); if (n > 1) { ui.page = (ui.page + 1) % n; paginate() } break }
      case "pick": if (!el.classList.contains("on")) send({ type: "pick", who: el.dataset.who }); break
      case "ask": send({ type: "ask", qid: el.dataset.qid, text: el.dataset.text }); break
      case "narrator": send({ type: "narrator" }); break
      case "next": send({ type: "next" }); break
      case "back": send({ type: "back" }); break
      case "mark": send({ type: "mark" }); break
      case "retry": send({ type: "retry" }); break
      case "live": ui.overlay = "settings"; send({ type: "live", on: !el.classList.contains("on") }); break
      case "events": send({ type: "events" }); break
    }
  }
  const onSubmit = (e) => {
    if (!e.target.matches("[data-form=ask]")) return
    e.preventDefault()
    const input = e.target.querySelector("input[name=q]")
    const text = (input.value || "").trim()
    if (!text) return
    input.value = ""
    send({ type: "ask", qid: null, text })
  }
  const onInput = (e) => {
    if (!e.target.classList.contains("memo")) return
    clearTimeout(ui.memoTimer)
    const value = e.target.value
    ui.memoTimer = setTimeout(() => setStateValue("memo", value), 700)
  }
  const onKey = (e) => {
    if (e.key === "Escape") { ui.overlay = null; ui.drawer = null; render() }
  }
  app.onclick = onClick
  // 수첩 '자료' 묶음을 펼친 상태는 다시 그려도 유지(toggle은 버블링되지 않아 캡처로 받음)
  if (!ui.matListener) {
    ui.matListener = true
    app.addEventListener("toggle", (e) => { const d = e.target; if (d.classList && d.classList.contains("mgroup")) ui.openMat[d.dataset.label] = d.open }, true)
  }
  layer.onclick = onClick
  app.onsubmit = onSubmit
  app.oninput = onInput
  parentElement.host ? (parentElement.host.onkeydown = onKey) : null
  window.onresize = () => requestAnimationFrame(paginate)

  if (changed || !app.childElementCount) render()
}
