"""Cardanoism wallet bridge.

`window.cardanoismWallet` API を提供する JS モジュールをページに注入する
ヘルパー。Reflex の rx.script に渡す形で使う。

Python 側からの呼び出しは `rx.call_script(...)` 経由 (wallet_state.py 参照)。

使い方:
    from cardanoism_wallet import wallet_module_script
    rx.script(wallet_module_script())
"""
from __future__ import annotations

from pathlib import Path


def wallet_module_script() -> str:
    """同梱 wallet_module.js の中身を文字列で返す。"""
    src = Path(__file__).resolve().parent / "web" / "src" / "wallet_module.js"
    return src.read_text(encoding="utf-8")
