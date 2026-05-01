"""WalletState
CIP-30 ウォレットの接続状態を保持する Reflex State。

JS 側 (`window.cardanoismWallet`) を `rx.call_script` で呼び出す方式。
React コンポーネントは使わない。

Phase 1: 接続/切断 + reward addr 取得
Phase 2: signData (CIP-8) によるアドレス所有確認
"""
from __future__ import annotations

import json
import logging

import reflex as rx

from cardanoism.backend import auth_db, pool_search
from cardanoism.backend.auth_state import AuthState
from cardanoism.backend.wallet_verify import (
    build_message,
    generate_nonce,
    stake_address_to_hex,
    verify_cose_sign1,
)

logger = logging.getLogger(__name__)


def _short(addr: str, head: int = 10, tail: int = 6) -> str:
    if not addr:
        return ""
    if len(addr) <= head + tail + 1:
        return addr
    return f"{addr[:head]}…{addr[-tail:]}"


def _js_call(expr: str) -> str:
    """try/catch を被せて { __error } か通常結果を返す async IIFE を組み立てる。"""
    return (
        "(async () => {"
        "  try { return await " + expr + "; }"
        "  catch (e) { return { __error: String(e && e.message ? e.message : e) }; }"
        "})()"
    )


def _disconnect_js():
    """JS 側 (window.cardanoismWallet) を切断して localStorage をクリアする。"""
    return rx.call_script(
        "(async () => {"
        "  try { await window.cardanoismWallet.disconnect(); } catch (_) {}"
        "  return true;"
        "})()"
    )


class WalletState(rx.State):
    """ブラウザ拡張ウォレットの接続状態。"""

    # 検出済みウォレット (例: ["eternl", "yoroi"])
    available_wallets: list[str] = []

    # 接続結果
    connected: bool = False
    wallet_name: str = ""
    reward_address: str = ""
    used_addresses: list[str] = []
    network_id: int = 1
    # 接続中アドレスの現在の委任先 pool_id_bech32 (ステーキングページで強調表示用)
    current_delegated_pool_id: str = ""

    # ブートストラップ済みフラグ (二重発火防止)
    bootstrapped: bool = False

    # 接続要求時のターゲット reward address (空 = 特定アドレス指定なし)
    # 特定アドレス指定がある場合、wallet が違うアカウントを返したら拒否する
    desired_target_address: str = ""

    # 直近のエラーメッセージ
    error: str = ""

    # ── Phase 2: 検証フロー ────────────────────────────
    verifying_address: str = ""
    # 検証セッション一時保管 (サーバ側のみで保持)
    _verify_message: str = ""
    _verify_nonce: str = ""

    # ── Phase 3: 委任切替 (確認ダイアログ) ──────────────
    delegate_dialog_open: bool = False
    # ステーキングページの SPO カードから渡される対象プール情報
    delegate_target_pool: dict = {}
    # 現在委任中のプール情報 (current_delegated_pool_id から引いたもの)
    delegate_current_pool: dict = {}
    delegating: bool = False
    last_delegate_tx_hash: str = ""

    # ── 派生プロパティ ──────────────────────────────
    @rx.var
    def reward_address_short(self) -> str:
        return _short(self.reward_address)

    @rx.var
    def has_available_wallets(self) -> bool:
        return len(self.available_wallets) > 0

    @rx.var
    def wallet_label(self) -> str:
        labels = {
            "eternl":      "Eternl",
            "lace":        "Lace",
            "yoroi":       "Yoroi",
            "typhoncip30": "Typhon",
            "tokeo":       "Tokeo",
            "vespr":       "VESPR",
        }
        if not self.wallet_name:
            return ""
        return labels.get(self.wallet_name, self.wallet_name.capitalize())

    # ── 起動シーケンス ──────────────────────────────────
    @rx.event
    def bootstrap(self):
        """ナビバーのマウント時に検出 + 自動再接続を試みる。"""
        if self.bootstrapped:
            return
        self.bootstrapped = True
        return rx.call_script(
            "(() => {"
            "  const w = window.cardanoismWallet;"
            "  if (!w) return { detected: [], stored: '' };"
            "  return { detected: w.detectWallets(), stored: w.getStoredWallet() };"
            "})()",
            callback=WalletState.bootstrap_result,
        )

    @rx.event
    def bootstrap_result(self, info: dict):
        if not isinstance(info, dict):
            return
        try:
            self.available_wallets = [str(x) for x in (info.get("detected") or [])]
        except Exception:
            self.available_wallets = []
        stored = str(info.get("stored", ""))
        if stored and stored in self.available_wallets:
            return WalletState.connect_wallet(stored)

    # ── 接続 ────────────────────────────────────────────
    @rx.event
    def connect_wallet(self, wallet_name: str, target_address: str = ""):
        """指定ウォレットへの接続を要求する。

        target_address が指定されている場合、接続結果の reward address が
        一致しなければ connect_result 側で拒否する (特定アドレス要求時に有効)。
        navbar からの auto reconnect 等では target_address は空。
        """
        wallet_name = (wallet_name or "").strip()
        if not wallet_name:
            return
        self.error = ""
        self.desired_target_address = (target_address or "").strip()

        events: list = []

        # 既に接続中の場合、ユーザに拡張機能側でのアカウント切替を促す
        # (CIP-30 はサイトから wallet にアカウント選択を強制できないため)
        if self.connected and self.reward_address != self.desired_target_address:
            events.append(rx.toast.info(
                "別のアドレスに接続するには、ウォレット拡張機能で対象アカウントに切り替えてから接続してください。",
                duration=6000,
            ))

        events.append(rx.call_script(
            _js_call(f"window.cardanoismWallet.connect({json.dumps(wallet_name)})"),
            callback=WalletState.connect_result,
        ))
        return events

    @rx.event
    async def connect_result(self, result: dict):
        # target は 1 回限り (このコールバックの判定にのみ使う)
        target = self.desired_target_address
        self.desired_target_address = ""

        if not isinstance(result, dict):
            self.error = "ウォレット接続結果が不正です"
            return rx.toast.error(self.error)
        if "__error" in result:
            self.error = str(result["__error"])
            logger.warning("wallet connect failed: %s", self.error)
            return rx.toast.error(f"ウォレット接続に失敗: {self.error}")

        reward_address = str(result.get("reward_address", ""))
        if not reward_address:
            self.error = "reward address が取得できませんでした"
            return [_disconnect_js(), rx.toast.error(self.error)]

        auth = await self.get_state(AuthState)
        if not auth.user_id:
            self.error = "ウォレットを使うにはログインが必要です"
            return [_disconnect_js(), rx.toast.error(self.error)]

        # ── 特定アドレスを要求していた場合の不一致チェック (最優先) ──
        # 「アドレス A のカードでウォレット接続」を押したのに wallet が
        # 違うアドレス (登録済みでも未登録でも) を返した場合。target を
        # 先にチェックすることで「アカウント切替の案内」を優先的に出す。
        if target and reward_address != target:
            short = reward_address[:10] + "…" + reward_address[-6:] if len(reward_address) > 18 else reward_address
            self.error = (
                f"目的のアドレスではなく {short} に接続されました。"
                "ウォレット拡張機能で対象のアカウントに切り替えてから再度接続してください。"
            )
            logger.info(
                "address mismatch: user=%s want=%s got=%s",
                auth.user_id, target, reward_address,
            )
            return [_disconnect_js(), rx.toast.error(self.error, duration=8000)]

        # ── 登録済みアドレスとの一致を確認 (target 指定なし時のみ重要) ──
        registered = [
            str(a.get("address", "")) for a in (auth.stake_addresses or [])
        ]
        if reward_address not in registered:
            self.error = (
                "このウォレットのアドレスはマイページに登録されていません。"
                "先にステークアドレスを登録してください。"
            )
            logger.info(
                "rejected unregistered wallet: user=%s reward=%s registered=%s",
                auth.user_id, reward_address, registered,
            )
            return [_disconnect_js(), rx.toast.error(self.error)]

        # ── 登録済み → 接続確定 ──
        try:
            self.wallet_name = str(result.get("wallet", ""))
            self.reward_address = reward_address
            ua = result.get("used_addresses") or []
            self.used_addresses = [str(x) for x in ua]
            try:
                self.network_id = int(result.get("network_id", 1))
            except (TypeError, ValueError):
                self.network_id = 1
            self.connected = True
            self.error = ""

            # この reward_address の現在の委任先を引き当てる
            self.current_delegated_pool_id = ""
            for a in (auth.stake_addresses or []):
                if str(a.get("address", "")) == reward_address:
                    self.current_delegated_pool_id = str(a.get("delegated_pool_id") or "")
                    break

            return rx.toast.success(f"{self.wallet_label} に接続しました")
        except Exception as e:  # noqa: BLE001
            logger.exception("connect_result parse error")
            self.error = f"接続情報の取り込みに失敗: {e}"
            return rx.toast.error(self.error)

    # ── 切断 ────────────────────────────────────────────
    @rx.event
    def disconnect_wallet(self):
        self.connected = False
        self.wallet_name = ""
        self.reward_address = ""
        self.used_addresses = []
        self.current_delegated_pool_id = ""
        return rx.call_script(
            "(async () => { await window.cardanoismWallet.disconnect(); return true; })()"
        )

    # ── 新規登録用: 接続状態を変えずアドレスだけ取得 ──────────
    @rx.event
    def fetch_for_register(self, wallet_name: str):
        """登録フォームに自動入力するためにウォレットからアドレスを取得する。

        connect_wallet と違い `_activeApi` は更新しない (登録フォーム用の単発取得)。
        登録後にユーザが「ウォレット接続」を別途押せば改めて enable される。
        """
        wallet_name = (wallet_name or "").strip()
        if not wallet_name:
            return
        return rx.call_script(
            _js_call(f"window.cardanoismWallet.getAddress({json.dumps(wallet_name)})"),
            callback=WalletState.fetch_for_register_result,
        )

    @rx.event
    async def fetch_for_register_result(self, result: dict):
        if not isinstance(result, dict):
            return rx.toast.error("ウォレットからアドレスを取得できませんでした")
        if "__error" in result:
            return rx.toast.error(
                f"ウォレットからアドレスを取得できませんでした: {result['__error']}"
            )
        used = str(result.get("first_used_address", ""))
        reward = str(result.get("reward_address", ""))
        if not used and not reward:
            return rx.toast.error("ウォレットからアドレスを取得できませんでした")

        # 既存の add_stake_address_handler が addr1... を Koios で stake1u に
        # 解決する仕組みなので、ここでは used (addr1...) を入れる。
        auth = await self.get_state(AuthState)
        auth.new_stake_address = used or reward
        # 既存エラーメッセージをクリア
        auth.stake_error = ""
        # ニックネーム未入力ならウォレット名を仮置き (後でユーザが変更可)
        if not auth.new_stake_nickname:
            wallet_label_map = {
                "eternl": "Eternl", "lace": "Lace", "yoroi": "Yoroi",
                "typhoncip30": "Typhon", "tokeo": "Tokeo", "vespr": "VESPR",
            }
            wallet_key = str(result.get("wallet", ""))
            auth.new_stake_nickname = wallet_label_map.get(wallet_key, wallet_key.capitalize() or "Wallet")

        return rx.toast.success(
            "ウォレットからアドレスを取得しました。ニックネームを確認して登録してください。"
        )

    # ── Phase 2: 検証フロー ────────────────────────────────────

    @rx.event
    async def request_verify(self, stake_address: str):
        stake_address = (stake_address or "").strip()
        if not stake_address:
            return

        auth = await self.get_state(AuthState)
        if not auth.user_id:
            return rx.toast.error("ログインが必要です")

        if not self.connected:
            return rx.toast.error("ウォレットが接続されていません")

        if self.reward_address != stake_address:
            return rx.toast.error(
                "接続中ウォレットがこの登録アドレスと一致しません。"
                "ウォレット側でアカウントを切り替えてください。"
            )

        nonce = generate_nonce()
        try:
            auth_db.issue_verification_nonce(auth.user_id, stake_address, nonce)
        except Exception as e:  # noqa: BLE001
            logger.exception("issue_verification_nonce failed")
            return rx.toast.error(f"nonce 発行エラー: {e}")

        message = build_message(nonce)
        self.verifying_address = stake_address
        self._verify_message = message
        self._verify_nonce = nonce

        return rx.call_script(
            _js_call(
                "window.cardanoismWallet.signOwnership("
                f"{json.dumps(stake_address)}, {json.dumps(message)})"
            ),
            callback=WalletState.verify_result,
        )

    @rx.event
    async def verify_result(self, info: dict):
        stake_address = self.verifying_address or ""
        message = self._verify_message
        nonce = self._verify_nonce

        self._verify_message = ""
        self._verify_nonce = ""
        self.verifying_address = ""

        try:
            if not stake_address or not nonce or not message:
                return rx.toast.error("検証セッションが見つかりません (タイムアウト?)")

            if not isinstance(info, dict):
                return rx.toast.error("署名結果が不正な形式です")

            if "__error" in info:
                return rx.toast.error(f"署名がキャンセルされました: {info['__error']}")

            signature = str(info.get("signature", ""))
            key = str(info.get("key", ""))
            if not signature or not key:
                return rx.toast.error("署名データが不完全です")

            auth = await self.get_state(AuthState)
            if not auth.user_id:
                return rx.toast.error("ログインが必要です")

            if not auth_db.consume_verification_nonce(
                auth.user_id, stake_address, nonce
            ):
                return rx.toast.error("nonce が無効か期限切れです")

            addr_hex = stake_address_to_hex(stake_address) or ""
            ok, reason = verify_cose_sign1(
                signature_hex=signature,
                key_hex=key,
                expected_message=message,
                expected_address_hex=addr_hex,
            )
            if not ok:
                logger.warning(
                    "signature verify failed: user=%s addr=%s reason=%s",
                    auth.user_id, stake_address, reason,
                )
                return rx.toast.error(f"署名の検証に失敗しました: {reason}")

            try:
                auth_db.mark_stake_address_verified(auth.user_id, stake_address)
            except Exception as e:  # noqa: BLE001
                logger.exception("mark_stake_address_verified failed")
                return rx.toast.error(f"DB 更新エラー: {e}")

            try:
                auth.stake_addresses = auth_db.get_stake_addresses(auth.user_id)
            except Exception as e:  # noqa: BLE001
                logger.warning("refresh stake_addresses failed: %s", e)

            return rx.toast.success("ウォレット所有確認に成功しました")
        except Exception as e:  # noqa: BLE001
            logger.exception("verify_result unexpected error")
            return rx.toast.error(f"検証中に予期せぬエラー: {e}")

    # ── Phase 3: 委任切替 (SPO カードから直接呼ぶ確認フロー) ──

    @rx.event
    async def request_delegate_to_pool(self, pool_id_bech32: str):
        """ステーキングページの SPO カードから「委任する」を押した時の入口。
        対象プールを取得し、ウォレット接続済みなら確認ダイアログを開く。
        """
        pool_id_bech32 = (pool_id_bech32 or "").strip()
        if not pool_id_bech32 or not pool_id_bech32.startswith("pool"):
            return rx.toast.error("無効な SPO です")

        auth = await self.get_state(AuthState)
        if not auth.user_id:
            return rx.toast.error("ログインが必要です")

        if not self.connected:
            return rx.toast.error(
                "ウォレットが未接続です。マイページのステークアドレスタブから接続してください。",
                duration=8000,
            )

        try:
            info = pool_search.get_pool_by_bech32(pool_id_bech32)
        except Exception as e:  # noqa: BLE001
            logger.warning("get_pool_by_bech32 failed: %s", e)
            info = {}
        if not info:
            return rx.toast.error("対象 SPO の情報が見つかりません")

        # 現在委任中プールの情報も取得 (あれば)
        current_info: dict = {}
        if self.current_delegated_pool_id and self.current_delegated_pool_id != pool_id_bech32:
            try:
                current_info = pool_search.get_pool_by_bech32(
                    self.current_delegated_pool_id
                ) or {}
            except Exception as e:  # noqa: BLE001
                logger.warning("current pool fetch failed: %s", e)
                current_info = {}

        self.delegate_target_pool = info
        self.delegate_current_pool = current_info
        self.last_delegate_tx_hash = ""
        self.delegate_dialog_open = True

    @rx.event
    def close_delegate_dialog(self):
        self.delegate_dialog_open = False
        self.delegate_target_pool = {}
        self.delegate_current_pool = {}

    @rx.event
    def on_delegate_dialog_open_change(self, is_open: bool):
        """Radix Dialog の open 変化を受ける。閉じる時だけ state クリーンアップ。"""
        if not is_open and self.delegate_dialog_open:
            self.delegate_dialog_open = False
            self.delegate_target_pool = {}
            self.delegate_current_pool = {}

    @rx.event
    async def submit_delegation(self):
        """確認ダイアログから委任 tx を組み立てて wallet で署名 → submit する。"""
        if self.delegating:
            return
        if not self.connected:
            return rx.toast.error("ウォレットが接続されていません")

        pool_id = str((self.delegate_target_pool or {}).get("pool_id_bech32", "")).strip()
        if not pool_id or not pool_id.startswith("pool"):
            return rx.toast.error("有効な SPO が選択されていません")

        auth = await self.get_state(AuthState)
        if not auth.user_id:
            return rx.toast.error("ログインが必要です")

        # 接続中の reward が登録済みアドレスのいずれかと一致することを確認
        registered = [
            str(a.get("address", "")) for a in (auth.stake_addresses or [])
        ]
        if self.reward_address not in registered:
            return rx.toast.error(
                "接続中ウォレットのアドレスが登録されていません。"
                "マイページで登録 + 接続してから再度お試しください。"
            )

        # network 推定 (network_id: 0=testnet, 1=mainnet)
        network_name = "Mainnet" if self.network_id == 1 else "Preprod"

        self.delegating = True
        return rx.call_script(
            _js_call(
                "window.cardanoismWallet.delegateToPool("
                f"{json.dumps(pool_id)}, {json.dumps(network_name)})"
            ),
            callback=WalletState.delegation_result,
        )

    @rx.event
    def delegation_result(self, result: dict):
        self.delegating = False
        if not isinstance(result, dict):
            return rx.toast.error("委任 tx の結果が不正です")
        if "__error" in result:
            msg = str(result["__error"])
            logger.warning("delegation tx failed: %s", msg)
            return rx.toast.error(f"委任に失敗しました: {msg}", duration=8000)
        tx_hash = str(result.get("tx_hash", ""))
        if not tx_hash:
            return rx.toast.error("tx_hash が取得できませんでした")
        self.last_delegate_tx_hash = tx_hash
        # 楽観的に委任先を更新 (実反映は次の Koios 同期で確定)
        new_pool_id = str((self.delegate_target_pool or {}).get("pool_id_bech32", ""))
        if new_pool_id:
            self.current_delegated_pool_id = new_pool_id
        self.delegate_dialog_open = False
        self.delegate_target_pool = {}
        self.delegate_current_pool = {}
        return rx.toast.success(
            f"委任 tx を送信しました: {tx_hash[:10]}…{tx_hash[-6:]}",
            duration=10000,
        )
