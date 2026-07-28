# Export Spec / データエクスポート仕様

**Language / 言語:** [English](#english) ・ [日本語](#日本語)

Specification of Cardanoism's user-facing data export. Current scope: **CSV export of the 4 "Favorites" tabs on My Page.**
Cardanoism のユーザー向けデータエクスポート機能の仕様。現状の対応範囲は**マイページの「お気に入り」4 タブの CSV エクスポート**。

- **Implementation:** [`cardanoism/backend/auth_state.py`](../../cardanoism/backend/auth_state.py) (`_csv_response` / `export_*_favorites_csv`, L1460–1619)
- **UI:** [`cardanoism/pages/mypage.py`](../../cardanoism/pages/mypage.py) (`_export_csv_button`, top of each favorites tab)
- **Data sources:** `get_favorites` / `get_governance_favorites_for_export` / `get_drep_favorites` / `get_pool_favorites`

---

## English

### Common specification

| Item | Specification |
|---|---|
| **Trigger** | "CSV export" button (download icon) at the top of each favorites tab |
| **Auth** | **Login required.** When not logged in, the handler returns immediately and emits nothing |
| **Scope** | Only the acting user's own favorites (`self.user_id`). Filters/paging are ignored; **all rows** are exported |
| **Format** | CSV (RFC 4180). Delimiter `,`, newline `\r\n` (CRLF), `QUOTE_MINIMAL` (quote only when needed) |
| **Encoding** | UTF-8 with a leading **BOM** (`﻿`). Prevents mojibake in Excel for Japanese text |
| **Row 1** | Header row with English keys |
| **Delivery** | `rx.download(data=..., filename=...)` browser download (nothing stored server-side) |
| **Filename** | `favorites_{type}_{YYYY-MM-DD}.csv`. Date is **UTC** (`datetime.now(timezone.utc)`) |
| **URL building** | Each row includes an absolute URL to the target detail page. Base is `CARDANOISM_URL` (defaults to `https://cardanoism.com`, trailing `/` stripped) |
| **Amount conversion** | lovelace → ADA: divide by `1_000_000`, format to 6 decimals, strip trailing zeros and `.`. Zero or invalid → empty string |

> The shared output helper is `_csv_response(headers, rows, filename)` (auth_state.py L1463), which handles BOM, CRLF, and download conversion.

### Export types

#### 1. Catalyst (`export_catalyst_favorites_csv`)
Filename: `favorites_catalyst_{YYYY-MM-DD}.csv` / Source: `get_favorites(user_id, "catalyst")`

| Column | Content |
|---|---|
| `uuid` | Proposal UUID (CIDP) |
| `title` / `title_ja` | Original / Japanese title |
| `fund` | Fund label |
| `status` | funding_status |
| `amount_requested` | Requested amount (raw number) |
| `currency` | Currency symbol |
| `url` | `{base}/catalyst/proposals/{uuid}` |
| `favorited_at` | Favorited timestamp (created_at) |

#### 2. Governance (`export_governance_favorites_csv`)
Filename: `favorites_governance_{YYYY-MM-DD}.csv` / Source: `get_governance_favorites_for_export(user_id)`

| Column | Content |
|---|---|
| `proposal_id` | GA proposal_id (CIP-129) |
| `title` / `title_ja` | Original / Japanese title |
| `type` | proposal_type |
| `proposed_epoch` | Submission epoch |
| `status` | active/ratified/enacted/dropped/expired (derived from epoch columns) |
| `enacted_epoch` | Enacted epoch |
| `withdrawal_ada` | Treasury withdrawal amount (lovelace→ADA; 0 → empty) |
| `url` | `{base}/governance/{proposal_id}` |
| `favorited_at` | Favorited timestamp |

> `status` is derived by `_status_from_epochs(ratified, enacted, dropped, expired)` (priority: enacted > ratified > expired > dropped > active).

#### 3. DRep (`export_drep_favorites_csv`)
Filename: `favorites_drep_{YYYY-MM-DD}.csv` / Source: `get_drep_favorites(user_id)`

| Column | Content |
|---|---|
| `drep_id` | DRep ID (bech32 / CIP-129) |
| `given_name` | CIP-119 display name |
| `status` | drep_status |
| `amount_ada` | Delegated amount (lovelace→ADA) |
| `url` | `{base}/drep/{drep_id}` |
| `favorited_at` | Favorited timestamp |

#### 4. Pool (`export_pool_favorites_csv`)
Filename: `favorites_pool_{YYYY-MM-DD}.csv` / Source: `get_pool_favorites(user_id)`

| Column | Content |
|---|---|
| `pool_id` | Pool ID (bech32) |
| `ticker` | Ticker |
| `pool_name` | Pool name |
| `live_stake_ada` | Live stake (lovelace→ADA) |
| `live_saturation_pct` | Saturation % |
| `live_delegators` | Delegator count |
| `status` | pool_status |
| `retiring_epoch` | Retiring epoch |
| `url` | `{base}/staking/pool/{pool_id}` |
| `favorited_at` | Favorited timestamp |

### Constraints / notes

- Export covers **favorites only**. A full **personal-data disclosure / portability export (data-subject access) is not yet supported**. For those stored fields, see [`schema_user_store.md`](schema_user_store.md).
- Output is synchronous. Splitting/async handling for very large favorite counts is not supported.
- Values are as returned by the source queries (whether titles are translated depends on the data). URL is empty when the target ID is empty.

> When a "full personal-data export (disclosure / portability)" is implemented, expand this doc into two sections: (a) favorites CSV and (b) user-data disclosure.

---

## 日本語

### 共通仕様

| 項目 | 仕様 |
|---|---|
| **トリガー** | 各お気に入りタブ上部の「CSV エクスポート」ボタン（download アイコン） |
| **認証** | **ログイン必須**。未ログイン時はハンドラが即 return し何も出力しない |
| **対象範囲** | 操作ユーザー自身（`self.user_id`）のお気に入りのみ。フィルタ・ページングは無視し**全件**出力 |
| **形式** | CSV（RFC 4180 準拠）。区切り `,`、改行 `\r\n`(CRLF)、クォート `QUOTE_MINIMAL`（必要時のみ `"` 囲み） |
| **文字コード** | UTF-8 + **先頭に BOM**（`﻿`）。Excel での日本語文字化け対策 |
| **1 行目** | 英語キーのヘッダー行 |
| **配信** | `rx.download(data=..., filename=...)` でブラウザダウンロード（サーバ保存はしない） |
| **ファイル名** | `favorites_{type}_{YYYY-MM-DD}.csv`。日付は **UTC**（`datetime.now(timezone.utc)`） |
| **URL 生成** | 各行に対象詳細ページの絶対 URL を付与。ベースは `CARDANOISM_URL`（未設定時 `https://cardanoism.com`、末尾 `/` 除去） |
| **金額変換** | lovelace → ADA は `/1_000_000` 後、小数 6 桁で末尾 0 と `.` を除去。0 または不正値は空文字 |

> 共通の出力ヘルパーは `_csv_response(headers, rows, filename)`（auth_state.py L1463）。BOM 付与・CRLF・ダウンロード化を一手に担う。

### エクスポート種別

#### 1. カタリスト（`export_catalyst_favorites_csv`）
ファイル名: `favorites_catalyst_{YYYY-MM-DD}.csv` / ソース: `get_favorites(user_id, "catalyst")`

| 列 | 内容 |
|---|---|
| `uuid` | 提案 UUID（CIDP） |
| `title` / `title_ja` | 原題 / 日本語タイトル |
| `fund` | Fund ラベル |
| `status` | funding_status |
| `amount_requested` | 要求金額（数値そのまま） |
| `currency` | 通貨記号 |
| `url` | `{base}/catalyst/proposals/{uuid}` |
| `favorited_at` | お気に入り登録時刻（created_at） |

#### 2. ガバナンス（`export_governance_favorites_csv`）
ファイル名: `favorites_governance_{YYYY-MM-DD}.csv` / ソース: `get_governance_favorites_for_export(user_id)`

| 列 | 内容 |
|---|---|
| `proposal_id` | GA の proposal_id（CIP-129） |
| `title` / `title_ja` | 原題 / 日本語タイトル |
| `type` | proposal_type |
| `proposed_epoch` | 提出エポック |
| `status` | active/ratified/enacted/dropped/expired（エポック列から導出） |
| `enacted_epoch` | 施行エポック |
| `withdrawal_ada` | 国庫引き出し額（lovelace→ADA 変換。0 は空） |
| `url` | `{base}/governance/{proposal_id}` |
| `favorited_at` | お気に入り登録時刻 |

> `status` は `_status_from_epochs(ratified, enacted, dropped, expired)` で導出（優先順: enacted > ratified > expired > dropped > active）。

#### 3. DRep（`export_drep_favorites_csv`）
ファイル名: `favorites_drep_{YYYY-MM-DD}.csv` / ソース: `get_drep_favorites(user_id)`

| 列 | 内容 |
|---|---|
| `drep_id` | DRep ID（bech32 / CIP-129） |
| `given_name` | CIP-119 表示名 |
| `status` | drep_status |
| `amount_ada` | 委任額（lovelace→ADA 変換） |
| `url` | `{base}/drep/{drep_id}` |
| `favorited_at` | お気に入り登録時刻 |

#### 4. プール（`export_pool_favorites_csv`）
ファイル名: `favorites_pool_{YYYY-MM-DD}.csv` / ソース: `get_pool_favorites(user_id)`

| 列 | 内容 |
|---|---|
| `pool_id` | プール ID（bech32） |
| `ticker` | ティッカー |
| `pool_name` | プール名 |
| `live_stake_ada` | ライブステーク（lovelace→ADA 変換） |
| `live_saturation_pct` | 飽和率 |
| `live_delegators` | 委任者数 |
| `status` | pool_status |
| `retiring_epoch` | 引退予定エポック |
| `url` | `{base}/staking/pool/{pool_id}` |
| `favorited_at` | お気に入り登録時刻 |

### 制約・留意点

- エクスポートは**お気に入りデータのみ**。プロフィール・ステークアドレス・通知設定等の**ユーザー個人データ一式の開示/ポータビリティ出力（データ主体アクセス対応）は現状未対応**。これらの格納項目は [`schema_user_store.md`](schema_user_store.md) を参照。
- 出力は同期処理。お気に入り件数が極端に多い場合の分割・非同期化は未対応。
- 値はソースクエリの返却そのまま（タイトル等の翻訳有無はデータ依存）。URL は対象 ID が空なら空文字。

> 将来「本人データ一式エクスポート（開示請求 / データポータビリティ）」を実装する場合は、本書を (a) お気に入り CSV と (b) ユーザーデータ開示、の 2 セクション構成に拡張する。
