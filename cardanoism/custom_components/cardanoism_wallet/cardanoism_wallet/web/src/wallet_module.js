// wallet_module.js
// rx.script でページに inject される JS モジュール。
// window.cardanoismWallet API を公開し、Python 側からは
// rx.call_script(...) で呼び出される。
//
// React は使わない。CIP-30 + bech32 (CDN) で完結。

(function () {
  if (typeof window === "undefined") return;
  if (window.cardanoismWallet) return;  // 二重ロード防止

  const SUPPORTED_WALLETS = [
    { key: "eternl",      label: "Eternl",  platform: "both" },
    { key: "lace",        label: "Lace",    platform: "both" },
    { key: "yoroi",       label: "Yoroi",   platform: "both" },
    { key: "typhoncip30", label: "Typhon",  platform: "desktop", aliases: ["typhon"] },
    { key: "tokeo",       label: "Tokeo",   platform: "both" },
    { key: "vespr",       label: "VESPR",   platform: "mobile" },
  ];

  function detectInstalledWallets() {
    const cardano = window.cardano;
    if (!cardano || typeof cardano !== "object") return [];
    const found = [];
    for (const def of SUPPORTED_WALLETS) {
      if (cardano[def.key]) { found.push(def.key); continue; }
      if (def.aliases) {
        for (const alias of def.aliases) {
          if (cardano[alias]) { found.push(def.key); break; }
        }
      }
    }
    return found;
  }

  function resolveWalletApi(key) {
    const cardano = window.cardano;
    if (!cardano) return null;
    if (cardano[key]) return cardano[key];
    const def = SUPPORTED_WALLETS.find(w => w.key === key);
    if (def && def.aliases) {
      for (const alias of def.aliases) {
        if (cardano[alias]) return cardano[alias];
      }
    }
    return null;
  }

  let _activeApi = null;
  let _activeWallet = null;

  // ── bech32 (依存なしの最小実装) ─────────────────────
  const BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l";

  function bech32Polymod(values) {
    const GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3];
    let chk = 1;
    for (const v of values) {
      const top = chk >>> 25;
      chk = ((chk & 0x1ffffff) << 5) ^ v;
      for (let i = 0; i < 5; i++) {
        if ((top >> i) & 1) chk ^= GEN[i];
      }
    }
    return chk;
  }

  function bech32HrpExpand(hrp) {
    const out = [];
    for (let i = 0; i < hrp.length; i++) out.push(hrp.charCodeAt(i) >> 5);
    out.push(0);
    for (let i = 0; i < hrp.length; i++) out.push(hrp.charCodeAt(i) & 31);
    return out;
  }

  function bech32CreateChecksum(hrp, data) {
    const values = bech32HrpExpand(hrp).concat(data).concat([0, 0, 0, 0, 0, 0]);
    const mod = bech32Polymod(values) ^ 1;
    const out = [];
    for (let i = 0; i < 6; i++) out.push((mod >> (5 * (5 - i))) & 31);
    return out;
  }

  function bech32Encode(hrp, data) {
    const checksum = bech32CreateChecksum(hrp, data);
    let out = hrp + "1";
    for (const v of data.concat(checksum)) out += BECH32_CHARSET.charAt(v);
    return out;
  }

  function bech32Decode(addr) {
    const lower = addr.toLowerCase();
    const pos = lower.lastIndexOf("1");
    if (pos < 1 || pos + 7 > lower.length) return null;
    const hrp = lower.slice(0, pos);
    const data = [];
    for (let i = pos + 1; i < lower.length; i++) {
      const idx = BECH32_CHARSET.indexOf(lower[i]);
      if (idx < 0) return null;
      data.push(idx);
    }
    return { hrp, data: data.slice(0, -6) };
  }

  function convertBits(data, from, to, pad) {
    let acc = 0, bits = 0;
    const out = [];
    const maxv = (1 << to) - 1;
    for (const v of data) {
      acc = (acc << from) | v;
      bits += from;
      while (bits >= to) {
        bits -= to;
        out.push((acc >> bits) & maxv);
      }
    }
    if (pad && bits > 0) out.push((acc << (to - bits)) & maxv);
    return out;
  }

  function bytesToBech32(bytes, hrp) {
    const data = convertBits(Array.from(bytes), 8, 5, true);
    return bech32Encode(hrp, data);
  }

  function bech32ToBytes(addr) {
    const dec = bech32Decode(addr);
    if (!dec) throw new Error("invalid bech32: " + addr);
    return new Uint8Array(convertBits(dec.data, 5, 8, false));
  }

  // ── address / hex / cbor utilities ────────────────────
  function hexToBytes(hex) {
    const out = new Uint8Array(hex.length / 2);
    for (let i = 0; i < out.length; i++) {
      out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
    }
    return out;
  }

  function bytesToHex(bytes) {
    return Array.from(bytes).map(b => b.toString(16).padStart(2, "0")).join("");
  }

  function unwrapCborByteString(hex) {
    if (!hex || hex.length < 2) return hex;
    const head = parseInt(hex.slice(0, 2), 16);
    if (head >= 0x40 && head <= 0x57) return hex.slice(2);
    if (head === 0x58) return hex.slice(4);
    if (head === 0x59) return hex.slice(6);
    return hex;
  }

  function addressHexToBech32(hex) {
    if (!hex) return "";
    const inner = unwrapCborByteString(hex);
    try {
      const bytes = hexToBytes(inner);
      const header = bytes[0];
      const network = header & 0x0f;
      const isStake = (header & 0xf0) === 0xe0;
      const hrp = isStake
        ? (network === 1 ? "stake" : "stake_test")
        : (network === 1 ? "addr" : "addr_test");
      return bytesToBech32(bytes, hrp);
    } catch (e) {
      console.warn("[cardanoism-wallet] bech32 encode failed:", e, hex);
      return "";
    }
  }

  function utf8ToHex(s) {
    return bytesToHex(new TextEncoder().encode(s));
  }

  // ── 公開 API ──────────────────────────────────────────

  async function connect(key) {
    const wallet = resolveWalletApi(key);
    if (!wallet) throw new Error("Wallet not installed: " + key);
    const api = await wallet.enable();
    let network_id = 1;
    try { network_id = await api.getNetworkId(); } catch (_) { /* noop */ }
    const rewardHexArr = await api.getRewardAddresses();
    const usedHexArr   = await api.getUsedAddresses();
    const rewardAddress = (rewardHexArr && rewardHexArr.length)
      ? addressHexToBech32(rewardHexArr[0]) : "";
    const usedAddresses = (usedHexArr || []).map(addressHexToBech32).filter(Boolean);
    _activeApi = api;
    _activeWallet = key;
    try { localStorage.setItem("cardanoism:wallet", key); } catch (_) {}
    return {
      wallet: key,
      reward_address: rewardAddress,
      used_addresses: usedAddresses,
      network_id,
    };
  }

  async function disconnect() {
    _activeApi = null;
    _activeWallet = null;
    try { localStorage.removeItem("cardanoism:wallet"); } catch (_) {}
    return true;
  }

  /**
   * 接続状態を変えずに、ウォレットの reward / used アドレスだけ取得する。
   * 新規ステークアドレス登録フォーム用。
   */
  async function getAddress(key) {
    const wallet = resolveWalletApi(key);
    if (!wallet) throw new Error("Wallet not installed: " + key);
    const api = await wallet.enable();
    let network_id = 1;
    try { network_id = await api.getNetworkId(); } catch (_) {}
    const rewardHexArr = await api.getRewardAddresses();
    const usedHexArr   = await api.getUsedAddresses();
    const rewardAddress = (rewardHexArr && rewardHexArr.length)
      ? addressHexToBech32(rewardHexArr[0]) : "";
    const firstUsed = (usedHexArr && usedHexArr.length)
      ? addressHexToBech32(usedHexArr[0]) : "";
    return {
      wallet: key,
      reward_address: rewardAddress,
      first_used_address: firstUsed,
      network_id,
    };
  }

  /**
   * _activeApi が落ちている時に localStorage の wallet で enable() し直す。
   * (ページ遷移やメモリ揮発で wallet 接続が JS 側で失われたケース対策)
   */
  async function _ensureActiveApi() {
    if (_activeApi) return _activeApi;
    const stored = getStoredWallet();
    if (!stored) return null;
    const wallet = resolveWalletApi(stored);
    if (!wallet) return null;
    try {
      _activeApi = await wallet.enable();
      _activeWallet = stored;
      return _activeApi;
    } catch (e) {
      console.warn("[cardanoism-wallet] _ensureActiveApi enable failed:", e);
      return null;
    }
  }

  async function signOwnership(stakeAddressBech32, message) {
    const api = await _ensureActiveApi();
    if (!api) throw new Error("Wallet not connected");
    const addrHex = bytesToHex(bech32ToBytes(stakeAddressBech32));
    const msgHex = utf8ToHex(message);
    const result = await api.signData(addrHex, msgHex);
    return {
      signature: String((result && result.signature) || ""),
      key:       String((result && result.key)       || ""),
    };
  }

  // ── Phase 3: 委任切替 (一旦保留、将来別ブランチで再実装) ──
  // Reflex 0.8 + Vite/Rolldown と Cardano lib (Mesh / Lucid) の WASM/Node API
  // 依存が噛み合わず、現状は安定動作しないため Phase 3 はストップ。
  // 委任ボタンクリック時は「準備中」を toast で返す。

  async function delegateToPool(poolBech32, networkName) {
    throw new Error(
      "委任機能は現在準備中です (Phase 3 で実装予定)。"
    );
  }

  function getStoredWallet() {
    try { return localStorage.getItem("cardanoism:wallet") || ""; }
    catch (_) { return ""; }
  }

  function isConnected() {
    return !!_activeApi;
  }

  window.cardanoismWallet = {
    detectWallets:    detectInstalledWallets,
    connect:          connect,
    disconnect:       disconnect,
    getAddress:       getAddress,
    signOwnership:    signOwnership,
    delegateToPool:   delegateToPool,
    getStoredWallet:  getStoredWallet,
    isConnected:      isConnected,
  };
})();
