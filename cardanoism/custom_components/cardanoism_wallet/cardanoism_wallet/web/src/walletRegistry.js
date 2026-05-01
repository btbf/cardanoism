// 対応ウォレットの定義
// CIP-30 の window.cardano.<key> で検出する。
// platform: "desktop" / "mobile" / "both"
//
// PC      : Eternl / Yoroi / Typhon / Tokeo
// Mobile  : Eternl / Yoroi / Tokeo / VESPR

export const SUPPORTED_WALLETS = [
  { key: "eternl",        label: "Eternl",  platform: "both" },
  { key: "yoroi",         label: "Yoroi",   platform: "both" },
  { key: "typhoncip30",   label: "Typhon",  platform: "desktop", aliases: ["typhon"] },
  { key: "tokeo",         label: "Tokeo",   platform: "both" },
  { key: "vespr",         label: "VESPR",   platform: "mobile" },
];

/** window.cardano から本サイトが対応するウォレット key の配列を返す。 */
export function detectInstalledWallets() {
  if (typeof window === "undefined") return [];
  const cardano = window.cardano;
  if (!cardano || typeof cardano !== "object") return [];

  const found = [];
  for (const def of SUPPORTED_WALLETS) {
    if (cardano[def.key]) {
      found.push(def.key);
      continue;
    }
    if (def.aliases) {
      for (const alias of def.aliases) {
        if (cardano[alias]) {
          // 主キーで返す (state 側は SUPPORTED_WALLETS 主キーで管理する)
          found.push(def.key);
          break;
        }
      }
    }
  }
  return found;
}

/** key から拡張機能の API オブジェクトを取得 (alias 対応)。 */
export function resolveWalletApi(key) {
  if (typeof window === "undefined") return null;
  const cardano = window.cardano;
  if (!cardano) return null;
  if (cardano[key]) return cardano[key];
  const def = SUPPORTED_WALLETS.find((w) => w.key === key);
  if (def?.aliases) {
    for (const alias of def.aliases) {
      if (cardano[alias]) return cardano[alias];
    }
  }
  return null;
}
