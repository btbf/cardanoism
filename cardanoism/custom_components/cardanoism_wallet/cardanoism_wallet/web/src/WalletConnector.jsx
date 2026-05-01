// 不可視の React コンポーネント。
// Reflex の rx.Component から props で desired_wallet を受け取り、
// 実際の CIP-30 接続処理を行ってイベントで結果を返す。
//
// Phase 1: connect / disconnect / detect
// Phase 2: signData によるアドレス所有確認
//   - verify_request prop に {stake_address, message} がセットされたら signData 実行
//   - 結果を on_verify_signed イベントで返す
//
// Phase 3 (未着手): Lucid Evolution によるトランザクション構築

import { useEffect, useRef } from "react";
import { detectInstalledWallets } from "./walletRegistry.js";
import {
  connect as walletConnect,
  disconnect as walletDisconnect,
  getStoredWallet,
  signOwnership,
} from "./walletAdapter.js";

export default function WalletConnector({
  desired_wallet = "",
  auto_reconnect = false,
  verify_request = null,
  onWalletList,
  onConnected,
  onDisconnected,
  onError,
  onVerifySigned,
  onVerifyError,
}) {
  // 同じ desired_wallet 値で多重接続を起こさないためのガード
  const lastTriedRef = useRef("");
  const initialDetectDoneRef = useRef(false);
  // verify_request の重複処理防止 (同じ message を 2 回は処理しない)
  const lastVerifyMessageRef = useRef("");

  // 1) ページロード時に対応ウォレットを検出 + 必要なら自動再接続
  useEffect(() => {
    if (initialDetectDoneRef.current) return;
    initialDetectDoneRef.current = true;

    const detected = detectInstalledWallets();
    if (typeof onWalletList === "function") {
      onWalletList(detected);
    }

    if (auto_reconnect) {
      const stored = getStoredWallet();
      if (stored && detected.includes(stored)) {
        (async () => {
          try {
            const info = await walletConnect(stored);
            lastTriedRef.current = stored;
            if (typeof onConnected === "function") onConnected(info);
          } catch (e) {
            if (typeof onError === "function") {
              onError(`auto reconnect failed: ${e?.message ?? e}`);
            }
          }
        })();
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 2) desired_wallet が変化したら接続/切断を行う
  useEffect(() => {
    const target = desired_wallet || "";

    if (!target) {
      if (lastTriedRef.current) {
        (async () => {
          try { await walletDisconnect(); } catch (_) { /* noop */ }
          lastTriedRef.current = "";
          if (typeof onDisconnected === "function") onDisconnected();
        })();
      }
      return;
    }

    if (lastTriedRef.current === target) return;

    (async () => {
      try {
        const info = await walletConnect(target);
        lastTriedRef.current = target;
        if (typeof onConnected === "function") onConnected(info);
      } catch (e) {
        const msg = e?.message ?? String(e);
        if (typeof onError === "function") onError(msg);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [desired_wallet]);

  // 3) verify_request が変化したら signData を実行
  useEffect(() => {
    if (!verify_request || typeof verify_request !== "object") return;
    const stakeAddr = verify_request.stake_address || "";
    const message = verify_request.message || "";
    if (!stakeAddr || !message) return;

    // 同じメッセージで二重発火しないようガード
    if (lastVerifyMessageRef.current === message) return;
    lastVerifyMessageRef.current = message;

    (async () => {
      try {
        const result = await signOwnership(stakeAddr, message);
        if (typeof onVerifySigned === "function") onVerifySigned(result);
      } catch (e) {
        const msg = e?.message ?? String(e);
        if (typeof onVerifyError === "function") onVerifyError(msg);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verify_request]);

  return null;
}
