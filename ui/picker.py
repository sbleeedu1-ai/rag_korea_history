"""모드·사건 고르기 카드 화면(CCv2, 2026-10-12 사용자 결정 [386]·[388]).

큰 세로 그림 카드를 나란히 보이고, 고르면 trigger "pick"으로 카드 id를 알린다. 마우스를 올리면 카드가 떠오르고,
카드마다 작은 움직임(취재: 등불, 실록: 덮인 책 → 펼친 책, 과거: 햇빛)이 있다. 준비 중 카드는 흐리게, 누를 수 없다.
화면 파일(picker_files/)을 고치면 서버를 다시 켜야 반영된다(stage와 같음).
"""
from pathlib import Path

import streamlit as st

FILES = Path(__file__).resolve().parent / "picker_files"


def _read(name: str) -> str:
    return "\n" + (FILES / name).read_text(encoding="utf-8")


def mount(data: dict, *, key: str, on_pick):
    """data: {"cards": [{id, title, sub, img, img_hover?, badge?, locked?, fx?}]}. on_pick: 카드를 고르면 부를 콜백."""
    renderer = st.components.v2.component(
        "sillok_card_picker", html=_read("picker.html"), css=_read("picker.css"), js=_read("picker.js"))
    return renderer(data=data, key=key, on_pick_change=on_pick)
