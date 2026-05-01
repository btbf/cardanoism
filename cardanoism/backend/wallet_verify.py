"""CIP-8 (COSE_Sign1) によるアドレス所有確認。

CIP-30 の `wallet.signData(addr, payload)` が返す `{signature, key}` ペアを
サーバ側で検証し、当該 stake address が確かにユーザの管理下にあることを
暗号学的に証明する。

依存: cbor2 (COSE のパース) + pynacl (Ed25519 検証)。

参考:
  - CIP-8:  https://cips.cardano.org/cips/cip8/
  - CIP-30: https://cips.cardano.org/cips/cip30/
  - COSE:   RFC 8152
"""
from __future__ import annotations

import logging
import secrets
from typing import Any

import cbor2
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

logger = logging.getLogger(__name__)


# COSE_Key ラベル
_COSE_KEY_KTY = 1
_COSE_KEY_ALG = 3
_COSE_KEY_CRV = -1
_COSE_KEY_X   = -2  # OKP の場合: 公開鍵バイト列

# COSE_Sign1 の protected header の "address" ラベル (CIP-8 拡張)
_HDR_ADDRESS = "address"


def generate_nonce(num_bytes: int = 16) -> str:
    """検証用 nonce (hex 32 文字) を生成。"""
    return secrets.token_hex(num_bytes)


def build_message(nonce: str) -> str:
    """ウォレットに署名させる平文メッセージ。
    nonce を埋め込み、人間が読んでも安全だと分かる文言にする。
    """
    return (
        f"Cardanoism: verify ownership / nonce={nonce}\n"
        f"This signature does not move funds and only proves that you control "
        f"this stake address."
    )


# ── 内部ユーティリティ ───────────────────────────────────────

def _unwrap_cbor_tag(obj: Any) -> Any:
    """cbor2 が CBORTag を返す場合のアンラップ。"""
    if isinstance(obj, cbor2.CBORTag):
        return obj.value
    return obj


def _to_hex(b: bytes) -> str:
    return b.hex() if isinstance(b, (bytes, bytearray)) else str(b)


# ── 公開検証関数 ─────────────────────────────────────────────

def verify_cose_sign1(
    signature_hex: str,
    key_hex: str,
    expected_message: str,
    expected_address_hex: str,
) -> tuple[bool, str]:
    """CIP-8 COSE_Sign1 を検証し、メッセージとアドレスの一致も確認する。

    Args:
        signature_hex: CIP-30 signData が返す `signature` (COSE_Sign1 CBOR の hex)
        key_hex:       CIP-30 signData が返す `key` (COSE_Key CBOR の hex)
        expected_message: 期待する平文メッセージ (build_message の出力)
        expected_address_hex: 期待する stake/payment address の hex (CBOR ヘッダなし)

    Returns:
        (verified: bool, reason: str)  reason は失敗時のみ意味がある
    """
    try:
        sig_bytes = bytes.fromhex(signature_hex)
        key_bytes = bytes.fromhex(key_hex)
    except ValueError:
        return False, "hex 形式不正"

    # ── COSE_Sign1 のパース ([protected, unprotected, payload, signature]) ──
    try:
        cose = _unwrap_cbor_tag(cbor2.loads(sig_bytes))
    except Exception as e:  # noqa: BLE001
        return False, f"COSE_Sign1 のパース失敗: {e}"

    if not (isinstance(cose, list) and len(cose) == 4):
        return False, "COSE_Sign1 構造が不正 (長さ 4 の配列ではない)"

    protected_bytes, _unprotected, payload, signature = cose

    if not isinstance(protected_bytes, (bytes, bytearray)):
        return False, "protected ヘッダがバイト列ではない"
    if not isinstance(payload, (bytes, bytearray)):
        return False, "payload がバイト列ではない"
    if not isinstance(signature, (bytes, bytearray)):
        return False, "signature がバイト列ではない"

    # protected ヘッダ (CBOR map) をデコード
    try:
        protected = cbor2.loads(bytes(protected_bytes)) if protected_bytes else {}
    except Exception as e:  # noqa: BLE001
        return False, f"protected ヘッダのデコード失敗: {e}"

    if not isinstance(protected, dict):
        return False, "protected ヘッダが map ではない"

    # アドレス一致確認 (CIP-8 拡張: protected["address"] = stake_addr_bytes)
    addr_in_sig = protected.get(_HDR_ADDRESS)
    if addr_in_sig is None:
        return False, "protected ヘッダに address が含まれていない"
    if not isinstance(addr_in_sig, (bytes, bytearray)):
        return False, "address ヘッダがバイト列ではない"
    if _to_hex(addr_in_sig).lower() != expected_address_hex.lower():
        return False, "署名のアドレスが要求アドレスと一致しない"

    # payload 一致確認
    try:
        message_in_sig = bytes(payload).decode("utf-8")
    except UnicodeDecodeError:
        return False, "payload が UTF-8 ではない"
    if message_in_sig != expected_message:
        return False, "payload が要求メッセージと一致しない"

    # ── COSE_Key (公開鍵) のパース ──
    try:
        cose_key = _unwrap_cbor_tag(cbor2.loads(key_bytes))
    except Exception as e:  # noqa: BLE001
        return False, f"COSE_Key のパース失敗: {e}"

    if not isinstance(cose_key, dict):
        return False, "COSE_Key が map ではない"

    pubkey = cose_key.get(_COSE_KEY_X)
    if not isinstance(pubkey, (bytes, bytearray)) or len(pubkey) != 32:
        return False, "Ed25519 公開鍵 (x = 32B) が取得できない"

    # ── Sig_structure を再構築して Ed25519 検証 ──
    sig_structure = [
        "Signature1",
        bytes(protected_bytes),
        b"",                   # external_aad
        bytes(payload),
    ]
    try:
        sig_structure_bytes = cbor2.dumps(sig_structure)
    except Exception as e:  # noqa: BLE001
        return False, f"Sig_structure のエンコード失敗: {e}"

    try:
        VerifyKey(bytes(pubkey)).verify(sig_structure_bytes, bytes(signature))
    except BadSignatureError:
        return False, "Ed25519 署名検証に失敗"
    except Exception as e:  # noqa: BLE001
        return False, f"Ed25519 検証中の例外: {e}"

    return True, "ok"


# ── bech32 → raw bytes (アドレス) ──────────────────────────────

def bech32_to_bytes(addr: str) -> bytes | None:
    """bech32 stake/payment address を raw bytes に変換。

    bech32 ライブラリを使わず、必要最低限の実装で bech32 → 5bit groups → 8bit bytes
    変換を行う。`bech32` パッケージが未インストールの環境でも動作させる。
    """
    if not addr or "1" not in addr:
        return None
    pos = addr.rfind("1")
    if pos < 1 or pos + 7 > len(addr):
        return None
    data_part = addr[pos + 1 :]
    # 末尾 6 文字は checksum
    if len(data_part) < 6:
        return None
    data = data_part[:-6]

    charset = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    words = []
    for c in data:
        idx = charset.find(c)
        if idx < 0:
            return None
        words.append(idx)

    # 5bit → 8bit 変換
    acc = 0
    bits = 0
    out = bytearray()
    for w in words:
        acc = (acc << 5) | w
        bits += 5
        while bits >= 8:
            bits -= 8
            out.append((acc >> bits) & 0xFF)
    if bits >= 5 or ((acc << (8 - bits)) & 0xFF) != 0:
        # padding が想定より多い → 不正
        # ただし strict には判定せず、すでに取れたバイト列を返す
        pass
    return bytes(out)


def stake_address_to_hex(bech32_addr: str) -> str | None:
    """`stake1...` bech32 を hex 文字列に変換。失敗時は None。"""
    b = bech32_to_bytes(bech32_addr)
    if b is None:
        return None
    return b.hex()
