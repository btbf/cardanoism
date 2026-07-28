# Changelog

**Language / 言語:** [English](#english) ・ [日本語](#日本語)

Changelog for Cardanoism, organized by feature theme following the Keep a Changelog format.
Cardanoism の変更履歴。Keep a Changelog 形式に倣い、機能テーマ別に整理しています。

---

## English

## [Unreleased] — vFinal

> **Changes since 2.0.0 (2026-01-29)** (322 commits / 2026-04-10 to 2026-06-11, merge commits excluded)

The deliverable for the Catalyst final milestone is **My Page** (Catalyst proposal list, persistent favorites, favorites export), covered in section 1 below.
Section 2 onward is listed for reference only: features added independently of the Catalyst scope — governance visualization, the DRep matching diagnostic, the staking dashboard, the three-track notification backend, multilingual support, and wallet-based delegation.

---

## 1. Final milestone deliverable — My Page

> **Catalyst reporting scope.** These are the features added for the final milestone.

**My Page (`/mypage`)**
- **Catalyst proposal list** — A list of the user's favorited Catalyst proposals on My Page, with fund / funding-status filters, sort switching, and pagination.
- **Persistent favorites** — Favorites are stored per user account in the DB, so they persist across sessions and devices. Login required.
- **Favorites export** — One-click CSV export of favorites from the top of the tab. RFC 4180 format, UTF-8 with BOM (mojibake-free in Excel), delivered as a browser download with nothing stored server-side. All rows are exported regardless of the active filters. See [export_spec.md](export_spec.md) for the full specification.

---

## 2. Reference — features added independently

> The following are **outside the Catalyst reporting scope**. They were added independently and are listed here for completeness.

### Added

**Governance (GA list / detail / vote tallies)**
- New governance action (GA) list and detail pages. Proposal ID display and search, plus ingestion of CIP-100/108 metadata (authors, etc.).
- Added a DRep × GA voting matrix page. CC / SPO role tabs, sort toggle, vote rationale modal, row hover highlight, and links from DRep cells to individual pages.
- Vote rationale modal shown in a shared format across the GA detail and matrix views.
- Added the current Cardano constitution page and a governance explainer page at `/governance/why`.

**GA AI analysis**
- AI-driven "fact organization" of GAs via OpenAI (gpt-5.4-mini). Auto-enqueue plus a resident worker; renders no verdict, only a neutral summary and key facts. Login required.
- Added a GA re-analysis CLI (`ga_ai_reanalyze`) and an `--all` flag for initial backfill including past GAs.

**DRep matching diagnostic**
- New DRep matching diagnostic at the dedicated route `/governance/drep/match`. An outcome-first model (final 8 axes / 8 questions) that aggregates value-axis scores from 5-point Likert answers to surface compatible DReps.
- Per-axis tagging of GAs (OpenAI-driven) to build each DRep's voting-tendency profile. A transparency UI where clicking an axis chip opens an evidence modal.
- AI-generated one-sentence match summary (JA/EN). DRep detail page shows the delegation-compass profile, full CIP-119 profile, and social links.

**Treasury**
- Added a treasury balance line chart across NCL periods.
- Implemented withdrawal tracking for TreasuryWithdrawals GAs and a per-epoch change table.

**Catalyst**
- Added proposal / fund switch tabs.

**Staking / Dashboard**
- New dashboard and SPO list pages under staking. Added a DB cache and sync worker for stake pools (SPOs).
- Added a stake pool detail page at `/pool/[id]`: block production history, health checks, and per-pool protocol version display (version-descending, ratio bars, heatmap).
- Added a pool activity heatmap, trailing 7-epoch average APY, and live block display.
- Added a personal "Dashboard" summary tab to My Page: delegated SPO / DRep names, delegation-days badge, and paginated unvoted GAs.
- Added a beginner-friendly `/staking/why` "What is staking?" page.

**My Page / Auth**
- Social login (LINE / Google / X) with multi-provider support and external UUID linking.
- Extended the favorites and CSV export mechanism beyond Catalyst to governance GAs, DReps, and Pools (4 favorites tabs in total).
- Stake address nickname editing.
- Initialize a new user's language from browser detection.

**Notifications**
- Added an Ogmios chain-sync daemon for real-time notifications. Real-time resolution of delegation target names on cert detection, per-Tx aggregation of GA proposal notices, and per-Tx aggregation of DRep vote notices.
- Added a Telegram notification channel (unified 3-channel structure: LINE / email / Telegram).
- Cardanoism-branded LINE Flex templates. Epoch-start notices, DRep unvoted-GA reminders (4 triggers), and per-epoch aggregation of treasury enactment notices.
- Added an admin notification connectivity-test event.

**Wallet / Delegation**
- CIP-30 wallet connection + ownership verification (Phase 1+2), and SPO / DRep delegation tx building (pycardano + Ogmios direct).
- Added mobile DApp browser guidance.

**Internationalization / Misc**
- Full-site i18n (all pages and components). Unified language-specific rendering for proposal content and match summaries.
- Added legal pages (privacy policy / terms / specified commercial transactions / company profile / maintenance), a cookie consent banner, a `/help` guide, `/pricing` with a subscription foundation (auto-granted Pro during beta), and a launch teaser page.
- Added an ADA rate + fetch timestamp and a hover dropdown to the navbar.

---

### Changed

**UI / UX & Design**
- Repeatedly renewed the TOP page toward a modern landing / notification-service pitch. Strengthened phone-style mocks (LINE / Telegram).
- Revamped the navbar with a modern design. Suppressed logo stretching, moved the language switch to the footer, and unified scroll-to-top after pagination.
- Overhauled mobile UX (fixed GA card layout breakage, mobile menu, dark-mode button colors).
- Unified the share button on DRep / Pool detail cards into a dropdown, and repositioned share+heart / delegate buttons.
- Switched GA donut charts to a color-vision-friendly palette. Removed the "Ep" label from epoch displays, leaving numbers only.

**Notification backend structure**
- Reorganized notifications into 3 tracks (real-time Ogmios listener / Koios polling / GA AI worker). Folded rationale fetching into a listener background task and retired the standalone worker.
- Redesigned notification templates around the unified 3-channel structure. Unified Telegram templates into a structured layout.

**Governance / Dashboard**
- Unified GA ordering by proposal_index and time direction. Unified vote labels to language-specific text and removed the legend.
- Made the dashboard load progressively, consolidating unvoted GAs into a DRep / SPO-only view with vote-rate bars.

---

### Fixed

**Notifications / Listener**
- Adapted to Ogmios v6.10+ schema changes (vote / DRep / delegation cert / GA anchor). Auto-reconnect on chainsync disconnect and tip-jump on cursor mismatch.
- Fixed a Koios field mix-up in `drep_status_change` and false notices from legacy bug states. Aggregated `drep_new_governance_action` into one notice per user.
- Fixed long-term delegation reminders to send only the single highest milestone reached. Added flood protection for new users.
- Improved email deliverability (Date / Message-ID / formataddr), and fixed the `pool_saturation` formula and the epoch filter for SPO reward notices.

**DB / Koios / Sync**
- Raise an exception instead of `sys.exit` on pool-acquisition failure, and revive dead connections via ping / reconnect. Roll back in `get_db()`'s finally to release frozen snapshots.
- Koios rate-limit mitigations (in-process cache, unified 90/10s rate limiter, cron jitter, D+B hybrid to stay within the 50k/day limit).
- Correctly separate active / pending by active_epoch_no in `/pool_updates`. Fixed DRep sync active-detection and full-set pagination tallies.

**Governance / Treasury / Matching**
- Added body / IPFS metadata / immutable fields to `upsert_proposal`'s on-duplicate-key update. Accounted for the Byron–Shelley transition in `_epoch_from_slot`.
- Resolved various collation mismatches (treasury payout JOIN, drep-compass, favorites-export).
- Fixed axis-name extraction bugs, JSON parse failures from AI output truncation, and zero-match cases in the DRep matching diagnostic.

**Auth / Misc**
- Fixed mobile LINE / Google / Twitter login state_mismatch. Made logout asynchronous to improve perceived speed.

---

### Performance

- Koios rate limiter with 1000-item chunking, and parallelization of notify_worker.
- Resolved dashboard N+1 queries and made protocol-version aggregation lazy-loaded.
- Introduced `FOR UPDATE SKIP LOCKED` in the GA AI `claim_next` to avoid deadlocks under parallel drainers.

---

### Documentation

- Added / refined the initial setup guide, notification backend configuration spec, Koios polling re-sync procedure, and systemd resident-worker setup.
- Brought the Infisical authentication procedure and CLAUDE.md in line with the new migrations / notification backend structure.
- Updated AI analysis to the latest "Plan A" (fact-organization tool) spec. Added AI-specific disclaimers and subscription clauses to the terms.

---

### Internal / Refactoring

- Consolidated migrations into final-shape schemas multiple times (28 → 7, 31 → 14 files, etc.), tidied for fresh deployments.
- Retired `.env` in favor of centralized management via Infisical. Updated the deploy environment (cron / systemd units / dependencies) for the remote setup.
- Extracted shared components (breadcrumb / subnav pill, etc.); removed unused assets and the legacy `oura_listener` / old design docs.
- Plus many smaller chores / refactors: typing fixes, logging improvements, i18n wording tweaks, and diagnostic tools (`fix_drep_vote_ids`, etc.).


---

## 日本語

## [Unreleased] — vFinal

> **2.0.0 (2026-01-29) 以降の変更**（322 コミット / 2026-04-10〜2026-06-11、マージコミット除く）

Catalyst ファイナルマイルストーンの成果物は**マイページ**（Catalyst 提案一覧・お気に入り登録の永続化・お気に入りのエクスポート）で、下記 1. に記載しています。
2. 以降は参考掲載です。Catalyst の報告対象外として独自に追加した機能（ガバナンス可視化・DRep マッチング診断・ステーキングダッシュボード・通知バックエンドの 3 系統化・多言語対応・ウォレット委任など）をまとめています。

---

## 1. ファイナルマイルストーン成果物 — マイページ

> **Catalyst 報告対象。** ファイナルマイルストーンで追加した機能です。

**マイページ（`/mypage`）**
- **Catalyst 提案一覧** — お気に入り登録した Catalyst 提案の一覧をマイページに表示。ファンド / 資金ステータスによる絞り込み、並び順切替、ページネーションに対応。
- **お気に入り登録の永続化** — お気に入りをユーザーアカウント単位で DB に保存し、セッションや端末をまたいで保持。ログイン必須。
- **お気に入りのエクスポート** — タブ上部のボタンから CSV をワンクリック出力。RFC 4180 形式・UTF-8 BOM 付き（Excel で文字化けしない）で、サーバー側に保存せずブラウザダウンロードで配信。絞り込み状態にかかわらず全件を出力します。詳細仕様は [export_spec.md](export_spec.md) を参照。

---

## 2. 参考 — 独自に追加した機能

> 以下は **Catalyst の報告対象外**です。独自に追加した機能を参考として掲載します。

### 新機能 (Added)

**ガバナンス（GA 一覧・詳細・投票集計）**
- ガバナンスアクション（GA）一覧・詳細ページを新設。提案 ID 表示・検索、CIP-100/108 メタデータ（authors 等）の取り込みに対応。
- DRep × GA 投票マトリクスページを追加。CC / SPO ロールタブ、並び順トグル、投票理由モーダル、行ホバーハイライト、DRep セルから個別ページへのリンクを実装。
- 投票理由（rationale）モーダルを GA 詳細・マトリクス共通フォーマットで表示。
- 現行 Cardano 憲法ページ、ガバナンス啓発ページ `/governance/why` を追加。

**GA AI 分析**
- OpenAI（gpt-5.4-mini）による GA の「ファクト整理」分析を実装。自動 enqueue + 常駐ワーカー方式で、判定を出さず中立的な要約と主要ファクトを提示。ログイン必須。
- GA AI 再分析 CLI（`ga_ai_reanalyze`）、過去 GA を含む初期投入の `--all` フラグを追加。

**DRep マッチング診断**
- DRep マッチング診断機能を専用ルート `/governance/drep/match` に新設。Likert 5 段階のクイズ回答から価値観軸を集計し、相性の良い DRep を提示する outcome-first モデル（最終 8 軸 / 8 問）。
- GA を per-axis でタグ分類（OpenAI 駆動）して DRep の投票傾向プロファイルを生成。axis chip クリックで根拠（evidence）モーダルを表示する透明性 UI。
- AI による 1 文マッチサマリ生成（日英対応）。DRep 詳細ページに委任コンパスプロファイル、CIP-119 プロフィール全文、SNS リンクを表示。

**トレジャリー**
- トレジャリー残高の NCL 期間折れ線グラフを追加。
- TreasuryWithdrawals GA の出金状況追跡、エポック別増減表を実装。

**カタリスト**
- 提案 / ファンド切替タブを追加。

**ステーキング / ダッシュボード**
- ステーキング配下にダッシュボード・SPO 一覧ページを新設。ステークプール（SPO）の DB キャッシュと同期ワーカーを追加。
- ステークプール詳細ページ `/pool/[id]` を追加。ブロック生成履歴、健全性チェック、プール別プロトコルバージョン表示（バージョン降順・比率横棒・ヒートマップ）を実装。
- プール活動ヒートマップ、直近 7 エポック APY 平均、ライブブロック表示を追加。
- マイページに個人サマリーの「ダッシュボード」タブを追加。委任先 SPO / DRep 名・委任日数バッジ、未投票 GA のページネーション表示。
- 初心者向け `/staking/why`「ステーキングとは？」ページを追加。

**マイページ / 認証**
- ソーシャルログイン（LINE / Google / X）と複数プロバイダ対応、外部 UUID 連携。
- お気に入り・CSV エクスポートの仕組みを Catalyst 以外（ガバナンス GA / DRep / Pool）へ拡張し、計 4 タブに対応。
- ステークアドレスのニックネーム編集。
- 新規ユーザーの言語をブラウザ判定で初期化。

**通知**
- リアルタイム通知の Ogmios チェーン同期デーモンを追加。委任 cert 検知時の委任先名リアルタイム解決、GA 提案通知の Tx 集約、DRep 投票通知の Tx 単位集約。
- Telegram 通知チャンネルを追加（LINE / メール / Telegram の 3 チャンネル統合構造）。
- LINE Flex テンプレートを Cardanoism ブランドで整備。エポック開始通知、DRep 未投票 GA リマインダー（4 トリガー）、トレジャリー施行通知のエポック単位集約。
- 管理者用の通知疎通テストイベントを追加。

**ウォレット / 委任**
- CIP-30 ウォレット接続 + 所有確認（Phase 1+2）、SPO / DRep 委任 tx 構築（pycardano + Ogmios direct）を実装。
- モバイル DApp ブラウザ案内を追加。

**多言語化 / その他**
- 全ページ・全コンポーネントの言語切替（i18n）対応。提案内容・マッチサマリも言語別表記に統一。
- 法務系ページ（プライバシーポリシー / 利用規約 / 特商法 / 会社概要 / メンテナンス）、Cookie 同意バナー、`/help` ガイド、`/pricing` とサブスク基盤（ベータ中 Pro 自動付与）、ローンチ予告ページを追加。
- ナビバーに ADA レート + 取得時刻表示、ホバードロップダウンを追加。

---

### 改善・変更 (Changed)

**UI / UX・デザイン**
- TOP ページをモダンなランディング / 通知サービス訴求型へ複数回リニューアル。スマホ向け mock（LINE / Telegram 風）演出を強化。
- ナビバーをモダンデザインに刷新。ロゴ伸縮抑止、言語切替のフッター移動、ページ送り後のトップスクロール統一。
- スマホ UX を全面改善（GA カードのレイアウト崩れ修正、モバイルメニュー、ダークモードボタン色）。
- DRep / Pool 詳細カードのシェアボタンをドロップダウンに統一し、share+heart / 委任ボタンを再配置。
- GA ドーナツチャートを色覚多様性対応の配色に変更。エポック表示から Ep ラベルを撤廃し数字のみに統一。

**通知バックエンド構成**
- 通知系を 3 系統（リアルタイム Ogmios リスナー / Koios ポーリング / GA AI ワーカー）に整理。投票理由取得を listener 内バックグラウンドタスクへ統合し常駐ワーカーを廃止。
- 通知テンプレートを 3 チャンネル統合構造へ再設計。Telegram テンプレを構造化レイアウトに統一。

**ガバナンス / ダッシュボード**
- GA 並び順を proposal_index と時間方向で統一。投票ラベルを言語別表記に統一し凡例を削除。
- ダッシュボードを段階ロード化し、未投票 GA を DRep / SPO 限定表示 + 投票率バーに集約。

---

### 修正 (Fixed)

**通知 / リスナー**
- Ogmios v6.10+ のスキーマ変更（vote / DRep / 委任 cert / GA anchor）へ対応。chainsync 切断時の自動再接続、カーソル不一致時の tip ジャンプを実装。
- `drep_status_change` の Koios フィールド取り違い・旧バグ状態からの誤通知を修正。`drep_new_governance_action` をユーザー単位 1 通知に集約。
- 長期委任リマインダーを到達済み最高マイルストーン 1 件のみ送信に修正。新規ユーザー flood 対策。
- メール配信性改善（Date / Message-ID / formataddr 付与）、`pool_saturation` 計算式・SPO 報酬通知のエポックフィルタ修正。

**DB / Koios / 同期**
- プール取得失敗で `sys.exit` せず例外送出、死んだ接続を ping / reconnect で蘇生。`get_db()` の finally で rollback し凍結スナップショットを解放。
- Koios レート制限対策（プロセス内キャッシュ、90/10s rate limiter 統一、cron jitter、D+B ハイブリッドで 50k/day 制限内に収める）。
- `/pool_updates` の active_epoch_no で active / pending を正しく分離。DRep sync の active 判定・ページネーション全件集計を修正。

**ガバナンス / トレジャリー / マッチング**
- `upsert_proposal` の重複キー更新に本文 / IPFS メタ / 不変フィールドを追加。`_epoch_from_slot` の Byron-Shelley 遷移考慮。
- 各種 collation 不一致（treasury payout JOIN、drep-compass、favorites-export）を解消。
- DRep マッチング診断の axis 名抽出バグ・AI 出力 truncation による JSON parse 失敗・0 件マッチを修正。

**認証 / その他**
- モバイルの LINE / Google / Twitter ログイン state_mismatch を修正。logout を非同期化し体感速度を改善。

---

### パフォーマンス

- Koios レートリミッター・1000 件チャンク対応、notify_worker の並列化。
- ダッシュボードの N+1 解消、プロトコルバージョン集計の遅延ロード化。
- GA AI の `claim_next` に `FOR UPDATE SKIP LOCKED` を導入し drainer 並列時のデッドロックを回避。

---

### ドキュメント

- 初期セットアップガイド、通知バックエンド設定仕様書、Koios ポーリング再 sync 手順、systemd 常駐ワーカー手順を追加・整備。
- Infisical 認証手順、CLAUDE.md を新マイグレーション / 通知バックエンド構成へ追従。
- AI 分析を A 方針（ファクト整理ツール）最新仕様に更新。利用規約に AI 専用免責・サブスク補強条項を追記。

---

### 内部・リファクタリング

- マイグレーションを最終形状スキーマへ複数回統合（28 本 → 7 本、31 → 14 ファイル等）。新規デプロイ用に整理。
- `.env` を廃止し Infisical で集中管理へ移行。デプロイ環境（cron / systemd unit / 依存パッケージ）をリモート構成向けに更新。
- breadcrumb / subnav pill 等の共通コンポーネント化、未使用アセット・旧 `oura_listener` / 旧設計書の削除。
- その他、型対応・ログ改善・i18n 文言調整・診断ツール（`fix_drep_vote_ids` 等）追加を含む細かな chore / refactor を多数実施。
