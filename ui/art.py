"""화면용 삽화. 인물은 실존 초상을 재현한 것이 아닌 창작 표현이다.

ui/assets/sized/에 화면 크기로 줄인 그림이 있다(저장소에 들어 있음, 약 7MB). 원본(assets/<이름>.png,
그림마다 2MB 안팎, GPT Image로 생성)은 저장소 밖에 두며, 원본이 있으면 원본에서 다시 줄인다.
그림이 하나도 없으면 아래 벡터 그림을 쓴다.
"""
import base64
import io
import os
import threading
from html import escape
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"
SIZED = "sized"   # 화면 크기로 줄인 그림 폴더(저장소에 들어 있음). 원본은 git 밖
ALPHA_EMPTY = 8   # 이 값 이하의 알파는 빈 곳으로 본다


def _cached(name: str, kind: str, width: int, make) -> bytes | None:
    """원본 assets/<name>.png를 make(원본 경로)로 줄인 결과(바이트). 원본도 줄인 그림도 없으면 None.

    원본은 2MB 안팎이라 줄이는 데 한 장에 0.3-1.7초(40장이면 약 30초) 걸린다. 결과를 assets/sized/에
    파일로 두어 서버를 다시 켜도 다시 줄이지 않는다. 줄인 파일의 수정 시각을 원본과 같게 맞춰 두고,
    원본을 바꾸면(시각이 달라지면) 다시 만든다. 줄이는 방법(아래 함수)을 고치면 sized/ 폴더를 지운다.
    원본이 없으면(저장소만 받은 경우) sized/의 그림을 그대로 쓴다.
    """
    path = ASSETS / f"{name}.png"
    cache = ASSETS / SIZED / f"{name}_{kind}{width}"
    if not path.exists():
        return cache.read_bytes() if cache.exists() else None
    stamp = path.stat().st_mtime_ns
    if cache.exists() and cache.stat().st_mtime_ns == stamp:
        return cache.read_bytes()
    data = make(path)
    try:   # 임시 파일에 다 쓴 뒤 바꿔 넣는다(뒤에서 미리 만드는 작업과 화면이 같은 파일을 동시에 쓸 수 있음)
        cache.parent.mkdir(exist_ok=True)
        part = cache.with_name(f"{cache.name}.{os.getpid()}.{threading.get_ident()}.part")
        part.write_bytes(data)
        os.utime(part, ns=(stamp, stamp))
        os.replace(part, cache)
    except OSError:   # 캐시를 못 써도 화면은 그대로 뜬다(다음에 다시 줄일 뿐)
        pass
    return data


def asset_uri(name: str, width: int) -> str | None:
    """assets/<name>.png를 너비 width 이하로 줄인 data URI. 파일이 없으면 None."""
    def make(path):
        from PIL import Image   # streamlit이 함께 설치하는 Pillow

        with Image.open(path) as img:
            img = img.convert("RGB")
            if img.width > width:
                img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, "JPEG", quality=85)
        return buffer.getvalue()

    data = _cached(name, "jpg", width, make)
    return data and "data:image/jpeg;base64," + base64.b64encode(data).decode()


def asset_png(name: str, width: int) -> str | None:
    """투명 배경 UI 부품(assets/<name>.png): 빈 가장자리를 잘라 내고 너비 width로 줄인 PNG data URI. 없으면 None.

    이미지 AI 그림은 가장자리에 거의 투명한 얼룩(알파 1-8)이 퍼져 있어 getbbox()만으로는 여분이 남는다.
    알파 8 이하를 빈 곳으로 보고 자른다(stage.css의 border-image 자르기 값은 이렇게 자른 그림 기준).
    """
    def make(path):
        from PIL import Image

        with Image.open(path) as img:
            img = img.convert("RGBA")
            box = img.getchannel("A").point(lambda a: 255 if a > ALPHA_EMPTY else 0).getbbox()
            if box:
                img = img.crop(box)
            if img.width > width:
                img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, "PNG", optimize=True)
        return buffer.getvalue()

    data = _cached(name, "png", width, make)
    return data and "data:image/png;base64," + base64.b64encode(data).decode()


def courtyard():
    """시안의 야간 궁궐·등불·창살 분위기를 작은 벡터 그림으로 표현한다."""
    windows = "".join(f'<rect x="{x}" y="{y}" width="12" height="20" fill="#ba8147" opacity=".65"/>'
                      for x in range(388, 955, 31) for y in (262, 295))
    rails = "".join(f'<path d="M{x} 348v110m-9-65h18" stroke="#554b3e" stroke-width="6"/>'
                    for x in range(25, 1260, 46))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 520" fill="none">
    <defs><linearGradient id="sky" x2="0" y2="1"><stop stop-color="#0b1722"/><stop offset="1" stop-color="#344759"/></linearGradient>
    <radialGradient id="glow"><stop stop-color="#ffbe62" stop-opacity=".48"/><stop offset="1" stop-color="#ffbe62" stop-opacity="0"/></radialGradient></defs>
    <path fill="url(#sky)" d="M0 0h1280v520H0z"/><circle cx="1010" cy="92" r="36" fill="#e5d8b2" opacity=".85"/>
    <path d="M0 249 97 209 185 247 266 187 352 230 440 204 539 252 690 195 812 229 905 185 1096 256 1200 214 1280 250v270H0" fill="#182d35"/>
    <path d="M330 242h680v106H330z" fill="#263039"/>{windows}
    <path d="m270 248 75-38 95-16 57-37h322l65 37 104 20 72 34-116-9H384z" fill="#0b1c26"/>
    <path d="m279 248 103-20h563l105 20M456 193h409M496 156h326" stroke="#6d7770" stroke-width="4"/>
    <path d="M352 254v94m132-94v94m150-94v94m160-94v94m180-94v94" stroke="#794f39" stroke-width="9"/>
    <path d="M306 345h731v13H306zM280 366h790v9H280z" fill="#69706b" opacity=".45"/>
    <path d="M0 458h1280v62H0z" fill="#151c1f"/>{rails}<path d="M0 345h1280v10H0zm0 94h1280v12H0z" fill="#766247"/>
    <path d="M0 0h105v520H0zM1191 0h89v520h-89z" fill="#271b18"/>
    <path d="M79 0h13v520M1205 0h13v520M0 32h1280" stroke="#785437" stroke-width="8"/>
    <path d="M0 0h1280v31H0z" fill="#171519"/>
    <circle cx="157" cy="278" r="150" fill="url(#glow)"/><circle cx="1125" cy="282" r="136" fill="url(#glow)"/>
    <g stroke="#372721" stroke-width="7"><path d="M127 215h61v100h-61z" fill="#e8a34f"/><path d="M140 215v100m32-100v100m-45-68h61m-61 43h61M157 32v179"/>
    <path d="M1095 215h61v100h-61z" fill="#e8a34f"/><path d="M1108 215v100m32-100v100m-45-68h61m-61 43h61M1125 32v179"/></g>
    </svg>'''


def portrait(name):
    """직책의 차이를 색과 관모로 표현한 픽셀풍 창작 삽화."""
    royal = name in ("세종", "세조")
    robe = "#8d443a" if royal else "#365b58"
    trim = "#c5a063" if royal else "#a6a58b"
    hat = '<path d="M58 20h64v56H58zM47 48h86v25H47z"/>' if royal else '<path d="M64 17h52v19H64zM56 36h68v37H56zM26 54h31v13H26zm98 0h31v13h-31z"/>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 220" role="img" aria-label="{escape(name)} 창작 삽화" shape-rendering="crispEdges">
    <path d="M0 0h180v220H0z" fill="#17282d"/><path d="M14 0v220M166 0v220M0 25h180M0 164h180" stroke="#43564e" stroke-width="2"/>
    <circle cx="91" cy="110" r="67" fill="#9b835b" opacity=".12"/>
    <path d="M63 131h54l15 17h20v14h13v58H15v-58h13v-14h20z" fill="{robe}"/>
    <path d="m58 132 31 35 34-35-11-8H71z" fill="#dfd2ae"/><path d="m67 140 23 22 24-22-9 34H77z" fill="{trim}"/>
    <path d="M62 64h56v53h-8v16H73v-16H62z" fill="#cfa782"/><path d="M63 72h10v41h-10zm45 0h10v43h-10z" fill="#b58767"/>
    <g fill="#172027">{hat}<path d="M69 81h15v4H69zm29 0h14v4H98zM73 87h7v4h-7zm28 0h7v4h-7zM81 107h22v7H81zm-8 2h9v23h-9zm28 0h9v23h-9zM82 117h20v27H82zM88 143h8v12h-8z"/></g>
    <path d="M91 91v11h5" stroke="#a97557" stroke-width="4"/><path d="M44 161v59m94-58v58" stroke="#162b2c" stroke-width="5" opacity=".5"/>
    <path d="M65 176h50v34H65z" fill="#243c3c" stroke="{trim}" stroke-width="3"/><path d="m77 192 12-8 13 8-13 9z" fill="{trim}"/>
    </svg>'''
