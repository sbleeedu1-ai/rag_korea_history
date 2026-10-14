"""헤드리스 Chrome(CDP)으로 시연 앱을 조작하며 화면을 받아 mp4로 묶는다.

python scripts/record_demo_video.py <단계 json 절대 경로> <출력 mp4>
시연 서버(8501)를 먼저 켜 둔다. 영상 변환에 imageio-ffmpeg가 필요하다(프로젝트 의존성 아님:
`pip install --target <이 파일 옆>/pylib imageio-ffmpeg`). 단계 파일 예시는 docs/기록/제출/최종발표_영상/녹화단계/.
화면 없는 Chrome은 스크롤 뒤 화면을 겹쳐 그리는 일이 있어, 스크롤 없이 다 보이게 창 높이를 잡는다(2026-10-13).
steps.json: {"w":1280,"h":896,"pre":[...], "rec":[...]}  (pre는 녹화 전 준비, rec는 녹화)
단계: {"click": 글자} {"toggle": 글자} {"type": 글자, "into": 입력칸 안내문} {"key": "Enter"} {"esc": 1}
      {"pause": 초} {"waitfor": 글자, "label": 자막, "timeout": 초} {"scroll": 글자} {"top": 1}
"""
import asyncio, base64, io, json, subprocess, sys, time, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0] + "\\pylib")
import imageio_ffmpeg
import websockets
from PIL import Image, ImageDraw, ImageFont

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
spec = json.load(open(sys.argv[1], encoding="utf-8"))
OUT = sys.argv[2]
W, H, FPS = spec["w"], spec["h"], 15
PROF = sys.argv[1].rsplit("\\", 1)[0] + "\\prof_rec"

FIND = """(t)=>{const sel='button,[data-act],[role=button],a,label,summary,div.card,div[class*=card],span.term';
 const walk=(root)=>{for(const el of root.querySelectorAll('*')){if(el.shadowRoot){const r=walk(el.shadowRoot);if(r)return r}}
 const c=[...root.querySelectorAll(sel)].filter(x=>x.innerText&&x.innerText.includes(t)&&x.offsetParent!==null);return c.length?c[c.length-1]:null};
 return walk(document)}"""
QS = """(s)=>{const w=(r)=>{const e=r.querySelector(s);if(e&&(e.offsetParent!==null||e.getClientRects().length))return e;for(const el of r.querySelectorAll('*')){if(el.shadowRoot){const x=w(el.shadowRoot);if(x)return x}}return null};return w(document)}"""
HAS = """(t)=>{const walk=(root)=>{if(root.body?root.body.innerText.includes(t):[...root.querySelectorAll('*')].some(x=>x.innerText&&x.innerText.includes(t)))return true;
 for(const el of root.querySelectorAll('*')){if(el.shadowRoot&&walk(el.shadowRoot))return true}return false};return walk(document)}"""


async def main():
    proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=9334", f"--window-size={W},{H}",
                             f"--user-data-dir={PROF}", "--hide-scrollbars", "about:blank"])
    try:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9334/json")); break
            except Exception:
                await asyncio.sleep(0.2)
        ws = await websockets.connect([t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"], max_size=2**28)
        pending, frames, marks = {}, [], {"clicks": [], "cuts": []}
        recording = {"on": False}
        n = [0]

        async def reader():
            async for raw in ws:
                msg = json.loads(raw)
                if "id" in msg and msg["id"] in pending:
                    pending.pop(msg["id"]).set_result(msg.get("result", {}))
                elif msg.get("method") == "Page.screencastFrame":
                    p = msg["params"]
                    if recording["on"]:
                        frames.append((time.time(), p["data"]))
                    await ws.send(json.dumps({"id": 10**9 + p["sessionId"], "method": "Page.screencastFrameAck",
                                              "params": {"sessionId": p["sessionId"]}}))
        asyncio.create_task(reader())

        async def call(method, **params):
            n[0] += 1
            fut = asyncio.get_event_loop().create_future()
            pending[n[0]] = fut
            await ws.send(json.dumps({"id": n[0], "method": method, "params": params}))
            return await fut

        async def ev(expr):
            r = await call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
            return r.get("result", {}).get("value")

        async def wheel_to(find_js, frac):
            for _ in range(3):
                r = await ev(f"(()=>{{const e={find_js};if(!e)return null;const r=e.getBoundingClientRect();return [r.top,r.height]}})()")
                if not r:
                    return False
                delta = r[0] - H * frac
                if abs(delta) < 40:
                    return True
                steps = max(1, int(abs(delta) // 90))
                for _ in range(steps):
                    await call("Input.dispatchMouseEvent", type="mouseWheel", x=W / 2, y=H / 2, deltaX=0, deltaY=delta / steps)
                    await asyncio.sleep(0.035)
                await asyncio.sleep(0.5)
            return True

        async def click_at(find_js):
            box = await ev(f"(()=>{{const e={find_js};if(!e)return null;const r=e.getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]}})()")
            if not box:
                return False
            x, y = box
            marks["clicks"].append((time.time(), x, y))
            await call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
            await asyncio.sleep(0.15)
            for t in ("mousePressed", "mouseReleased"):
                await call("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left", clickCount=1)
            return True

        async def click(text):
            if not await wheel_to(f"({FIND})({json.dumps(text)})", 0.45):
                print("못 찾음:", text); return
            await asyncio.sleep(0.3)
            box = await ev(f"(()=>{{const e=({FIND})({json.dumps(text)});const r=e.getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]}})()")
            x, y = box
            marks["clicks"].append((time.time(), x, y))
            for t in ("mouseMoved", "mousePressed", "mouseReleased"):
                await call("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left", clickCount=1)

        async def run(steps):
            for s in steps:
                if "click" in s:
                    await click(s["click"])
                elif "toggle" in s:
                    await ev("(()=>{const l=[...document.querySelectorAll('label')].find(x=>x.innerText.includes(%s));l&&l.querySelector('input').click()})()" % json.dumps(s["toggle"]))
                elif "type" in s:
                    await ev("(()=>{const i=[...document.querySelectorAll('input,textarea')].find(x=>(x.placeholder||'').includes(%s));i.scrollIntoView({block:'center'});i.focus()})()" % json.dumps(s["into"]))
                    for ch in s["type"]:
                        await call("Input.insertText", text=ch)
                        await asyncio.sleep(0.07)
                elif "key" in s:
                    for t in ("keyDown", "keyUp"):
                        await call("Input.dispatchKeyEvent", type=t, key=s["key"], code=s["key"], windowsVirtualKeyCode=13 if s["key"] == "Enter" else 27)
                elif "esc" in s:
                    for t in ("keyDown", "keyUp"):
                        await call("Input.dispatchKeyEvent", type=t, key="Escape", code="Escape", windowsVirtualKeyCode=27)
                elif "pause" in s:
                    await asyncio.sleep(s["pause"])
                elif "waitfor" in s:
                    t0 = time.time()
                    await asyncio.sleep(1.0)
                    while time.time() - t0 < s.get("timeout", 90) and not await ev(f"({HAS})({json.dumps(s['waitfor'])})"):
                        await asyncio.sleep(0.3)
                    await asyncio.sleep(0.6)
                    print("기다림", round(time.time() - t0, 1), "초:", s.get("label", s["waitfor"]))
                    marks["cuts"].append((t0 + 0.8, time.time() - 0.3, s.get("label", "답 기다림")))
                elif "scroll" in s:
                    fj = ("((t)=>{const w=(root)=>{for(const el of root.querySelectorAll('*')){if(el.shadowRoot){const r=w(el.shadowRoot);if(r)return r}}"
                          "return [...root.querySelectorAll('*')].filter(x=>x.innerText&&x.innerText.includes(t)&&x.children.length<4).pop()};return w(document)})(%s)" % json.dumps(s["scroll"]))
                    await wheel_to(fj, {"start": 0.08, "center": 0.4}.get(s.get("block", "center"), 0.4))
                    await asyncio.sleep(0.6)
                elif "clicksel" in s:
                    if not await click_at(f"({QS})({json.dumps(s['clicksel'])})"):
                        print("못 찾음:", s["clicksel"])
                elif "typesel" in s:
                    await ev(f"(()=>{{const i=({QS})({json.dumps(s['typesel'])});i.focus()}})()")
                    for ch in s["text"]:
                        await call("Input.insertText", text=ch)
                        await asyncio.sleep(0.07)
                elif "waitsel" in s:
                    t0 = time.time()
                    await asyncio.sleep(1.5)
                    while time.time() - t0 < s.get("timeout", 120) and not await ev(f"!!({QS})({json.dumps(s['waitsel'])})"):
                        await asyncio.sleep(0.3)
                    await asyncio.sleep(0.6)
                    print("기다림", round(time.time() - t0, 1), "초:", s.get("label", s["waitsel"]))
                    if s.get("cut", True):
                        marks["cuts"].append((t0 + 0.8, time.time() - 0.3, s.get("label", "답 기다림")))
                elif "eval" in s:
                    print("eval:", await ev(s["eval"]))
                elif "top" in s:
                    await ev("document.querySelectorAll('*').forEach(e=>{if(e.scrollTop>0)e.scrollTo({top:0,behavior:'smooth'})})")
                    await asyncio.sleep(1.0)

        await call("Page.enable")
        await call("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False)
        await call("Page.navigate", url="http://localhost:8501")
        await asyncio.sleep(8)
        await run(spec["pre"])
        await call("Page.startScreencast", format="jpeg", quality=85, maxWidth=W, maxHeight=H, everyNthFrame=1)
        recording["on"] = True
        t_start = time.time()
        await asyncio.sleep(0.5)
        await run(spec["rec"])
        await asyncio.sleep(0.5)
        recording["on"] = False
        t_end = time.time()
        await call("Page.stopScreencast")
        build(frames, marks, t_start, t_end)
    finally:
        proc.kill()


def build(frames, marks, t0, t1):
    font = ImageFont.truetype(r"C:\Windows\Fonts\malgunbd.ttf", 22)
    imgs = [(t, Image.open(io.BytesIO(base64.b64decode(d))).convert("RGB").resize((W, H))) for t, d in frames]
    # 출력 시각 → 원본 시각. 기다림 구간은 1.5초로 줄인다
    segs, t, out_t = [], t0, 0.0
    for a, b, label in sorted(marks["cuts"]):
        segs.append((t, a, None)); segs.append((a, b, label)); t = b
    segs.append((t, t1, None))
    ff = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                           "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", OUT], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    i = 0
    count = 0
    for a, b, label in segs:
        dur = 1.5 if label else max(b - a, 0)
        steps = max(int(dur * FPS), 1)
        for k in range(steps):
            src = a + (b - a) * k / steps
            while i + 1 < len(imgs) and imgs[i + 1][0] <= src:
                i += 1
            fr = imgs[i][1].copy() if imgs else Image.new("RGB", (W, H))
            d = ImageDraw.Draw(fr, "RGBA")
            for ct, x, y in marks["clicks"]:
                if 0 <= src - ct < 0.8:
                    r = 14 + 20 * (src - ct)
                    d.ellipse((x - r, y - r, x + r, y + r), outline=(220, 50, 40, 230), width=4)
            if label:
                txt = f"{label} · 실제 약 {round(b - a + 1.1)}초, 줄여서 보여 줌"
                tw = d.textlength(txt, font=font)
                d.rounded_rectangle(((W - tw) / 2 - 16, H - 70, (W + tw) / 2 + 16, H - 28), 10, fill=(0, 0, 0, 170))
                d.text(((W - tw) / 2, H - 64), txt, font=font, fill=(255, 255, 255))
            ff.stdin.write(fr.tobytes())
            count += 1
    ff.stdin.close(); ff.wait()
    print("프레임", len(imgs), "→ 출력", count, f"({count / FPS:.1f}초)", OUT)


asyncio.run(main())
