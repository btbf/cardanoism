// CIP-30 ウォレット接続の薄いラッパ (Phase 1+2)
//
// Phase 1 は「接続して reward addr / used addrs を取得する」だけ担当。
// 署名 (signData / signTx) と トランザクション送信は Phase 2+3 で追加する。
//
// Lucid Evolution は libsodium-wrappers-sumo の解決問題があり Vite で
// バンドルが通らないため、トランザクション構築が必要になる Phase 3 で
// 再導入する。Phase 1+2 は raw CIP-30 + bech32 で完結。

import { bech32 } from "bech32";
import { resolveWalletApi } from "./walletRegistry.js";

let _activeWallet = null;
let _activeApi = null;

// ── CBOR / hex utilities (依存ゼロ) ──────────────────────

function hexToBytes(hex) {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) {
    out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}

/**
 * CIP-30 の getRewardAddresses / getUsedAddresses は
 * "hex-encoded CBOR byte string" を返す実装が多い。
 * 先頭が CBOR の byte-string 型 (major 2) なら剥がす。
 *  - 0x40..0x57 : 即値長 (0..23)
 *  - 0x58 + 1byte len
 *  - 0x59 + 2byte len
 * それ以外は raw 扱い。
 */
function unwrapCborByteString(hex) {
  if (!hex || hex.length < 2) return hex;
  const head = parseInt(hex.slice(0, 2), 16);
  if (head >= 0x40 && head <= 0x57) return hex.slice(2);
  if (head === 0x58) return hex.slice(4);
  if (head === 0x59) return hex.slice(6);
  // 期待外 → raw として扱う (一部ウォレットは CBOR 包まずに返す)
  return hex;
}

/**
 * Cardano アドレス (raw bytes) を bech32 にエンコード。
 *  - reward address: header high nibble 0xe → "stake" / "stake_test"
 *  - payment address: low nibble 0=testnet, 1=mainnet → "addr" / "addr_test"
 */
function bytesToBech32(bytes) {
  if (!bytes || bytes.length === 0) return "";
  const header = bytes[0];
  const network = header & 0x0f;
  const isStake = (header & 0xf0) === 0xe0;
  const prefix = isStake
    ? (network === 1 ? "stake" : "stake_test")
    : (network === 1 ? "addr" : "addr_test");
  // Cardano アドレスは bech32 の標準長 90 を超えるので limit を 1023 にする
  return bech32.encode(prefix, bech32.toWords(bytes), 1023);
}

function hexToBech32(hex) {
  if (!hex) return "";
  const inner = unwrapCborByteString(hex);
  try {
    return bytesToBech32(hexToBytes(inner));
  } catch (e) {
    console.warn("[cardanoism-wallet] bech32 encode failed:", e, hex);
    return "";
  }
}

// ── 公開 API ────────────────────────────────────────────

/**
 * CIP-30 ウォレットに接続する。
 * @returns {Promise<{wallet:string, reward_address:string, used_addresses:string[], network_id:number}>}
 */
export async function connect(key) {
  const wallet = resolveWalletApi(key);
  if (!wallet) throw new Error(`Wallet not installed: ${key}`);

  const api = await wallet.enable();

  // network id: 0 = testnet, 1 = mainnet (CIP-30)
  let network_id = 1;
  try { network_id = await api.getNetworkId(); } catch (_) { /* noop */ }

  const rewardHexArr = await api.getRewardAddresses();
  const usedHexArr   = await api.getUsedAddresses();

  const rewardAddress = rewardHexArr && rewardHexArr.length
    ? hexToBech32(rewardHexArr[0])
    : "";
  const usedAddresses = (usedHexArr || [])
    .map(hexToBech32)
    .filter(Boolean);

  _activeWallet = key;
  _activeApi = api;
  try { localStorage.setItem("cardanoism:wallet", key); } catch (_) { /* noop */ }

  return {
    wallet: key,
    reward_address: rewardAddress,
    used_addresses: usedAddresses,
    network_id,
  };
}

/** 切断 (CIP-30 に明示的な切断はないので内部状態のクリアのみ)。 */
export async function disconnect() {
  _activeWallet = null;
  _activeApi = null;
  try { localStorage.removeItem("cardanoism:wallet"); } catch (_) { /* noop */ }
}

export function getStoredWallet() {
  try { return localStorage.getItem("cardanoism:wallet") || ""; }
  catch (_) { return ""; }
}

export function getActiveApi() {
  return _activeApi;
}

export function getActiveWallet() {
  return _activeWallet;
}

// ── Phase 2: signData (CIP-8 / 所有確認) ───────────────────

/** bech32 文字列を hex (raw bytes) に変換。 */
function bech32ToHex(addr) {
  const decoded = bech32.decode(addr, 1023);
  const bytes = bech32.fromWords(decoded.words);
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** UTF-8 文字列を hex に変換。 */
function utf8ToHex(s) {
  const enc = new TextEncoder().encode(s);
  return Array.from(enc)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * 接続中ウォレットに stake address でメッセージ署名させる。
 * @param {string} stakeAddressBech32 - "stake1..." 形式
 * @param {string} message - UTF-8 文字列。サーバ側で同一メッセージを再構築して照合
 * @returns {Promise<{signature:string, key:string}>}
 */
export async function signOwnership(stakeAddressBech32, message) {
  const api = _activeApi;
  if (!api) throw new Error("Wallet not connected");
  const addrHex = bech32ToHex(stakeAddressBech32);
  const msgHex = utf8ToHex(message);
  const result = await api.signData(addrHex, msgHex);
  // CIP-30: { signature: cose_sign1_hex, key: cose_key_hex }
  return {
    signature: String(result?.signature ?? ""),
    key: String(result?.key ?? ""),
  };
}
