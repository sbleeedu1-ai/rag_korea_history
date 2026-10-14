// 모드·사건 고르기 카드(CCv2). 카드를 누르면 setTriggerValue("pick", {id, at})로 알린다. 준비 중 카드는 누를 수 없다.
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]))

function ensureFonts() {
  // 카드 제목의 고운바탕(OFL). 본문 Pretendard는 ui/style.css가 문서에 불러온다
  if (document.getElementById("sillok-fonts")) return
  const link = document.createElement("link")
  link.id = "sillok-fonts"; link.rel = "stylesheet"
  link.href = "https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@400;700&family=Noto+Sans+KR:wght@400;500;700&display=swap"
  document.head.appendChild(link)
}

export default function (component) {
  const { data, parentElement, setTriggerValue } = component
  const root = parentElement.querySelector("#cards")
  if (!root || !data) return
  ensureFonts()
  const cards = data.cards || []
  root.style.setProperty("--n", cards.length)
  root.innerHTML = cards.map((c) => {
    const bg = c.img ? `<img class="art" src="${c.img}" alt="">` : `<div class="art blank"></div>`
    // 실록 카드: 평소 덮인 책(img), 마우스를 올리면 펼친 책(img_hover)으로 바뀐다
    const hover = c.img_hover ? `<img class="art over" src="${c.img_hover}" alt="">` : ""
    const badge = c.badge ? `<span class="badge${c.locked ? " lock" : ""}">${esc(c.badge)}</span>` : ""
    return `<button class="card fx-${esc(c.fx || "none")}${c.locked ? " locked" : ""}" data-id="${esc(c.id)}" ${c.locked ? 'disabled aria-disabled="true"' : ""}
        aria-label="${esc(c.title)} · ${esc(c.sub)}">${bg}${hover}<span class="light"></span>${badge}
        <span class="band"><b>${esc(c.title)}</b><small>${esc(c.sub)}</small></span></button>`
  }).join("")
  root.onclick = (e) => {
    const el = e.target.closest(".card")
    if (!el || el.disabled) return
    setTriggerValue("pick", { id: el.dataset.id, at: Date.now() })
  }
}
