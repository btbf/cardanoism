"""privacy.py
プライバシーポリシー (/privacy)

JA / EN は AuthState.language で切り替え (rx.cond でレンダリング先を分岐)。
本文は長文なのでモジュールレベル定数で保持。

グローバル展開を前提とし、日本国の個人情報保護法 (APPI) に加え、
EU/英国居住者向けの GDPR、米国カリフォルニア州居住者向けの CCPA に対応した記述を含む。
"""
from __future__ import annotations

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.components.markdown_doc import bilingual_markdown


_PRIVACY_JA = """\
# プライバシーポリシー

株式会社クヒト（以下「当社」といいます。）は、当社が提供する Cardanoism（以下「本サービス」といいます。）における、ユーザーの個人情報の取扱いについて、以下のとおりプライバシーポリシー（以下「本ポリシー」といいます。）を定めます。

当社は、個人情報の保護に関する法律（以下「個人情報保護法」といいます。）その他の関係法令を遵守し、ユーザーの個人情報を適切に取り扱います。本サービスは世界中のユーザーに提供されており、欧州経済領域（EEA）または英国に居住するユーザーには EU 一般データ保護規則（GDPR）が、米国カリフォルニア州に居住するユーザーにはカリフォルニア州消費者プライバシー法（CCPA / CPRA）が、それぞれ追加で適用される場合があります（第 12 章および第 13 章を参照）。

最終更新日: 2026 年 5 月 7 日

---

## 1. 取得する情報

当社は、本サービスの提供にあたり以下の情報を取得します。

### 1-1. ユーザーが入力・連携する情報

- ソーシャルログイン (LINE / Google / X) を通じて取得する情報: ユーザー識別子、表示名、メールアドレス、プロフィール画像
- ユーザー名、メールアドレス、表示言語、通知頻度
- ステークアドレス、ニックネーム、関連する委任先情報 (公開情報)
- 通知チャンネル設定 (LINE ユーザー ID、メールアドレス、Telegram chat ID)
- お気に入りに登録した提案 ID

### 1-2. サービス利用に伴い自動取得する情報

- セッション管理用 Cookie / トークン
- アクセス解析のためのアクセス情報 (IP アドレス、ブラウザ種別、参照元 URL、閲覧ページ等)
- 通知の重複送信防止のために保管する送信ログ (送信日時、イベント種別、宛先チャンネル等)

### 1-3. ブロックチェーン公開情報

本サービスは Cardano ブロックチェーンの公開情報 (ステークアドレスの委任状況、投票履歴、報酬等) を表示します。これらは元々パブリックな情報であり、当社が個別に収集する個人情報ではありません。

### 1-4. 通知チャンネル連携時に取得する情報

ユーザーが LINE / Telegram / メールでの通知配信を有効にした場合、当社は以下の情報を取得・保管します。これらは通知配信の目的にのみ使用し、第三者へ販売・広告利用することはありません。

| チャンネル | 取得項目 | 取得経路 | 保管場所 |
|----|----|----|----|
| LINE | LINE ユーザー ID (LINE Login OpenID Connect の `sub` クレーム)、表示名 (任意) | LINE OAuth 連携時に取得 | 当社 DB (`notification_channels` テーブル) |
| Telegram | Telegram chat ID、ユーザー名 (任意) | Telegram Bot との連携時に取得 | 当社 DB (`notification_channels` テーブル) |
| メール | メールアドレス | プロフィール編集または OAuth 提供 | 当社 DB (`users` / `notification_channels` テーブル) |

**LINE 連携時の追加事項:**
- LINE ユーザー ID は LINE のお友だち追加 / 連携解除によりユーザーが管理できます
- 通知配信は LINE Messaging API を通じて行います (LINE 株式会社が当該データを処理する範囲は同社のプライバシーポリシーに従います)
- 通知配信を停止したい場合は、本サービスのマイページ > 通知管理タブから個別チャンネル / イベント単位で OFF にできます
- LINE 公式アカウント側でのブロックでも通知は届かなくなります

各通知チャンネルの連携は、本サービスのマイページからいつでも解除できます。解除すると当社 DB から該当のチャンネル識別子は削除されます (送信ログは法令上の保管期間内のみ保管)。

### 1-5. 決済処理時の情報共有 (Stripe)

有料プランをご利用の場合、決済処理は Stripe, Inc. (米国) を通じて行われます。当社が直接保持する決済関連情報と、Stripe 側で処理・保管される情報は以下のとおりです。

| 情報 | 当社で保持 | Stripe で保持 |
|------|------------|----------------|
| クレジットカード番号、有効期限、セキュリティコード | **保持しません** | 保持 (PCI DSS 準拠) |
| Stripe Customer ID | 保持 | 保持 |
| Stripe Subscription ID | 保持 | 保持 |
| 課金履歴 (金額、決済日時、ステータス) | 保持 | 保持 |
| お客様の氏名、請求先住所 | 保持しません | Stripe 側で保管 |

Stripe は世界的な決済プロバイダであり、PCI DSS Level 1 認証を保有しています。Stripe におけるお客様情報の取扱いは、[Stripe 社のプライバシーポリシー](https://stripe.com/privacy) に従います。

決済情報は国際的に処理されるため、米国その他の国・地域への国際データ移転を伴います (第 5 章 国際データ移転 をご参照ください)。

---

## 2. 利用目的および処理の法的根拠

取得した情報は以下の目的のために利用します。GDPR が適用される場合、各利用目的の法的根拠は表のとおりです。

| 利用目的 | 法的根拠 (GDPR 第 6 条) |
|---------|----------------------|
| 本サービスの提供、認証、ユーザー設定の保存 | 契約の履行 (第 6 条 1 項 b 号) |
| 通知配信 (LINE / メール / Telegram) | ユーザー同意 (第 6 条 1 項 a 号) |
| 通知の重複送信防止のためのログ保管 | 正当な利益 (第 6 条 1 項 f 号) |
| 本サービスの改善、新機能の検討、不具合の調査 | 正当な利益 |
| 利用規約に違反する行為の防止・対応 | 正当な利益 |
| お問い合わせ・苦情への対応 | 契約の履行・正当な利益 |
| 統計情報の作成 (個人を特定できない形) | 正当な利益 |
| 法令で求められる場合の保管・開示 | 法的義務 (第 6 条 1 項 c 号) |

ユーザーは、同意を法的根拠とする処理について、いつでも同意を撤回できます。撤回は将来的な処理にのみ影響し、撤回前の処理の適法性には影響しません。

---

## 3. 第三者提供

当社は、以下の場合を除き、ユーザーの同意なく個人情報を第三者に提供しません。

- 法令に基づく場合
- 人の生命、身体または財産の保護のために必要がある場合
- 公衆衛生の向上または児童の健全な育成の推進のために特に必要がある場合
- 国の機関もしくは地方公共団体またはその委託を受けた者が法令の定める事務を遂行することに対して協力する必要がある場合

当社は、ユーザーの個人情報を金銭その他の対価を得て第三者に **販売することはありません**。

---

## 4. 外部委託および第三者サービスへの送信

本サービスは、以下の外部サービスにデータを送信または取得を行います。これらは、当社が個人情報の取扱いを委託する「委託先」と、ユーザー自身が直接サービスを利用するために連携する「第三者」に区分されます。委託先に対しては、個人情報の安全管理措置を求めるとともに、必要に応じて監督します。各サービスのプライバシーポリシーは各社の規定に従います。

| 用途 | 送信先 | 区分 | 主な内容 |
|------|--------|------|---------|
| ソーシャルログイン | LINE / Google / X | 第三者 | OAuth 認証情報 |
| ブロックチェーンデータ取得 | Koios API | 公開情報取得 | ステークアドレス (検索クエリ) |
| 通知配信 | LINE Messaging API | 委託 | LINE ユーザー ID + 通知本文 |
| 通知配信 | Telegram Bot API | 委託 | Telegram chat ID + 通知本文 |
| メール送信 | SMTP プロバイダ | 委託 | メールアドレス + 通知本文 |
| 翻訳・AI 分析 | OpenAI API | 委託 | ガバナンス提案の本文 |
| 価格情報取得 | CoinGecko | 個人情報非送信 | (個人情報は送信しません) |
| アクセス解析 | Google Analytics | 委託 | 匿名化されたアクセス情報 |

---

## 5. 国際データ移転

上記の送信先には、日本国外のサーバー (米国・EU・その他の地域) で処理されるサービスが含まれます。当社は、データの移転先となる国・地域に応じて以下のいずれかの法的メカニズムにより、十分な保護水準を確保するよう努めます。

- 移転先の国が、GDPR や日本の個人情報保護法に基づく十分性認定を受けている場合は、その認定に依拠します
- 当該認定がない場合は、欧州委員会の標準契約条項 (SCC) その他関連する保護措置を採用するか、ユーザーの明示的同意を取得します

各送信先のデータ保護に関する詳細は、各サービスのプライバシーポリシーをご参照ください。本サービスをご利用いただくことにより、当該国への個人情報の移転に同意いただいたものとみなします。

---

## 6. Cookie および類似技術

本サービスは、以下の目的で Cookie および類似技術を利用します。

| 種別 | 目的 | 同意の必要性 |
|------|------|------------|
| 必須 | ログインセッションの維持、セキュリティ | サービス提供に必須のため同意不要 |
| 機能 | 言語・表示モード等のユーザー設定保存 | 必須に準ずる |
| 分析 | アクセス解析 (Google Analytics) | 同意 (オプトイン) |

ユーザーは、ブラウザの設定または本サービスが提供する Cookie 設定からこれらを管理できます。必須以外の Cookie の利用を望まない場合、ご自身で無効化していただけます。

### 6-1. Google Consent Mode v2 について

本サービスは Google が提供する Consent Mode v2 を採用しています。ユーザーが分析 Cookie に同意していない場合、Google Analytics は永続的な Cookie を書き込まず、ユーザーを識別する情報を保存しません。一方で、ページ表示の発生を集計目的で測定するための **匿名のピン (cookieless ping)** が Google に送信されます。このピンには以下の特徴があります。

- 永続的な識別子 (Cookie / IP アドレス等) は保存・送信されません
- 個々のユーザーを識別する情報は含まれず、再訪問時に同一ユーザーとして紐付けされません
- Google による集計モデリングのみに利用されます

匿名ピンの送信を含めて一切の通信を望まない場合、ブラウザの拡張機能 (uBlock Origin 等) や OS のシステム設定により Google Analytics へのリクエスト自体をブロックしてください。

---

## 7. 安全管理措置

当社は、取得した個人情報および当社が個人情報として取り扱うことを予定している情報の漏えい、滅失、毀損および不正取得の防止その他の安全管理のために、適切な措置を講じます。

- 通信の HTTPS 化
- データベースアクセス制限
- 認証情報の暗号化保管
- 認証トークンの定期更新
- 依存ライブラリの脆弱性監視 (フロントエンドへの不正コード混入の防止)
- Content Security Policy 等による不正スクリプト実行の制限

---

## 8. 漏えい等発生時の対応

当社は、個人情報の漏えい、滅失、毀損その他の安全の確保に係る事態 (外部からの不正アクセス等により、当社が個人情報として取り扱うことを予定している情報に対して漏えいが生じたおそれがある場合を含みます。) が発生し、または発生したおそれがある場合、関連法令に従い速やかに以下を行います。

- 個人情報保護委員会への報告 (個人情報保護法に基づく)
- 影響を受ける本人への通知
- GDPR が適用される場合、72 時間以内に管轄監督機関への報告 (GDPR 第 33 条)

---

## 9. データの保管・保持期間

当社は、個人情報を利用目的の達成に必要な範囲で保管します。代表的な保持期間は以下のとおりです。

| データ種別 | 保持期間 |
|----------|---------|
| アカウント情報 (ユーザー名、メール、OAuth ID 等) | アカウント削除リクエスト後 30 日以内に消去 |
| ステークアドレス、通知設定、お気に入り | アカウント削除リクエスト後 30 日以内に消去 |
| 通知送信ログ | 90 日 |
| サーバーアクセスログ | 90 日 |
| 認証セッション・トークン | 失効時点で削除 (典型 7〜30 日) |

法令で別途保持義務が定められている場合は、当該期間中保管します。

---

## 10. ユーザーの権利

ユーザーは、当社が保有する自己の個人情報について、適用される法令に基づき以下の権利を行使できます。

- **開示請求 (Right to Access)**: 保有している個人情報の開示を求める権利
- **訂正・追加・削除請求 (Right to Rectification / Erasure)**: 不正確な情報の訂正、不要な情報の削除を求める権利
- **利用停止・消去請求 (Right to Restriction / Object)**: 利用の停止または異議を申し立てる権利
- **データポータビリティ (Right to Data Portability)**: 機械可読な形式で個人情報を受領する権利 (GDPR 適用時)
- **同意撤回 (Right to Withdraw Consent)**: 同意を法的根拠とする処理についていつでも同意を撤回する権利
- **自動意思決定からの除外 (Right not to be Subject to Automated Decision-making)**: 当社は重要な事項について完全自動の意思決定を行いません
- **監督機関への苦情申立て (Right to Lodge a Complaint)**: 居住国の個人情報保護当局に苦情を申し立てる権利

ユーザー名、メールアドレス、ステークアドレスのニックネーム、通知設定、お気に入り等は、本サービスのマイページから直接編集・削除いただけます。これら以外の請求や、上記の編集が技術的に困難な場合は、第 16 章のお問い合わせ・苦情申出窓口までご連絡ください。本人確認のうえ、合理的期間内に対応します。

---

## 11. 米国カリフォルニア州居住者向けの追加情報 (CCPA / CPRA)

米国カリフォルニア州に居住するユーザーには、本章および第 10 章の権利が適用されます。

### 過去 12 か月間に収集した個人情報のカテゴリ

- 識別子 (ユーザー名、メール、OAuth ID、IP アドレス)
- インターネット活動情報 (ブラウザ種別、参照元 URL、閲覧履歴)
- 概略的な位置情報 (IP アドレスから推測される国・地域レベル)

### 収集元

- ユーザーから直接 (フォーム入力、OAuth 連携)
- 自動的に取得 (Cookie、ログ、アクセス解析)
- 第三者ソーシャルログインプロバイダから (LINE / Google / X)

### 利用目的 (Business Purposes)

第 2 章に記載のとおり。

### 第三者への開示

第 3 章 (第三者提供) および第 4 章 (外部委託および第三者サービス) に記載のとおり。

### 「個人情報の販売」について

当社は、ユーザーの個人情報を **販売 (Sale) または共有 (Share) しません**。

### カリフォルニア州民の権利

- 知る権利 (Right to Know)
- 削除請求権 (Right to Delete)
- 訂正請求権 (Right to Correct)
- 販売・共有のオプトアウト権 (該当しない販売・共有がないため、当社では発生しません)
- 機微な個人情報の利用制限請求権
- 差別を受けない権利 (Right to Non-Discrimination)

これらの権利を行使するには、第 16 章のお問い合わせ窓口までご連絡ください。

---

## 12. EU・英国居住者向けの追加情報 (GDPR)

EU 加盟国・英国・スイス・アイスランド・ノルウェー・リヒテンシュタインに居住するユーザーには、本章および第 10 章の権利が適用されます。

### データ管理者 (Controller)

第 16 章に記載のとおり、株式会社クヒトが管理者となります。

### データ保護責任者 (DPO)

現時点では、GDPR 第 37 条に基づく DPO の指名は要件外と判断していますが、データ保護に関するお問い合わせは第 16 章までお寄せください。

### 監督機関への苦情申立て

ユーザーは、居住する EU 加盟国・英国の管轄監督機関に苦情を申し立てる権利を有します。

---

## 13. 未成年の利用

13 歳未満の方は本サービスを利用できません。13 歳以上 18 歳未満の方は、保護者の同意のうえ利用してください。GDPR が適用される場合、13〜16 歳のユーザーには各加盟国法が定める年齢規定に従い保護者の同意が必要です。

---

## 14. プライバシーポリシーの変更

当社は、必要に応じて本ポリシーを変更することがあります。重要な変更については、本サービス上での掲示およびユーザー登録メールアドレスへの通知 (該当する場合) によりお知らせします。

---

## 15. 準拠法

本ポリシーは日本法に準拠して解釈されます。ただし、各国・地域の強行法規 (GDPR、CCPA 等) が当該国・地域の居住者に適用されることを妨げません。

---

## 16. お問い合わせ・苦情申出窓口

本ポリシーに関するお問い合わせ、保有個人データの開示等のご請求、苦情のお申出は以下までご連絡ください。

- 事業者名: 株式会社クヒト
- 代表者: 加賀谷 侑
- 所在地: 神奈川県横浜市西区北幸二丁目10番48号 むつみビル3階
- メール: contact@kuhito.co.jp
"""


_PRIVACY_EN = """\
# Privacy Policy

Kuhito Co., Ltd. ("we", "our", or "us") provides Cardanoism (the "Service"). This Privacy Policy ("Policy") describes how we handle personal information of users.

We comply with the Act on the Protection of Personal Information of Japan ("APPI") and other applicable laws. The Service is offered globally; users residing in the European Economic Area (EEA) or the United Kingdom are also covered by the EU/UK General Data Protection Regulation ("GDPR"), and users residing in California, USA are also covered by the California Consumer Privacy Act ("CCPA / CPRA") (see Sections 11 and 12).

Last updated: May 7, 2026

---

## 1. Information We Collect

### 1-1. Information You Provide

- Information obtained through social login (LINE / Google / X): user identifier, display name, email address, profile image
- Username, email address, display language, notification frequency
- Stake addresses, nicknames, and related delegation information (public on-chain data)
- Notification channel settings (LINE user ID, email, Telegram chat ID)
- Proposal IDs you have favorited

### 1-2. Information We Collect Automatically

- Cookies and tokens for session management
- Access information for analytics (IP address, browser type, referrer URL, pages viewed)
- Delivery logs retained to prevent duplicate notifications (timestamp, event type, channel, etc.)

### 1-3. Public Blockchain Information

The Service displays publicly available Cardano blockchain information (stake address delegation status, voting history, rewards, etc.). These are public on-chain data, not personal information collected by us.

### 1-4. Information Collected When You Connect a Notification Channel

When you enable notifications via LINE / Telegram / email, we collect and store the following data. This data is used solely to deliver notifications and is never sold or used for third-party advertising.

| Channel | Data collected | Source | Stored in |
|----|----|----|----|
| LINE | LINE user ID (the `sub` claim from LINE Login OpenID Connect), display name (optional) | LINE OAuth flow | Our DB (`notification_channels` table) |
| Telegram | Telegram chat ID, username (optional) | Telegram Bot connection | Our DB (`notification_channels` table) |
| Email | Email address | Profile settings or OAuth provider | Our DB (`users` / `notification_channels` table) |

**Additional notes for LINE:**
- You can manage the LINE user ID by adding/removing the LINE friend or revoking the connection from your LINE account
- Notifications are delivered through the LINE Messaging API (data processed by LY Corporation is governed by their own privacy policy)
- You can disable notifications per channel or per event from My Page > Notifications tab in this Service
- Blocking the LINE Official Account also stops delivery

You can disconnect any notification channel from your My Page at any time. Once disconnected, the channel identifier is removed from our DB (delivery logs are retained only within the period required by law).

### 1-5. Information Shared During Payment Processing (Stripe)

When you subscribe to a paid plan, payment processing is handled by Stripe, Inc. (United States). The following table shows what we hold directly versus what is processed and stored by Stripe.

| Information | Held by us | Held by Stripe |
|------|------------|----------------|
| Credit card number, expiry, CVV | **Not held** | Held (PCI DSS compliant) |
| Stripe Customer ID | Held | Held |
| Stripe Subscription ID | Held | Held |
| Billing history (amount, date, status) | Held | Held |
| Cardholder name, billing address | Not held | Held by Stripe |

Stripe is a global payment processor certified to PCI DSS Level 1. Stripe's handling of your information is subject to [Stripe's Privacy Policy](https://stripe.com/privacy).

Payment information is processed internationally, including transfers to the United States and other regions (please see Section 5 — International Data Transfers).

---

## 2. Purposes of Use and Legal Bases for Processing

We use collected information for the following purposes. Where the GDPR applies, the legal basis for each purpose is shown below.

| Purpose | Legal Basis (GDPR Art. 6) |
|---------|--------------------------|
| Providing the Service, authenticating users, storing user settings | Performance of a contract (Art. 6(1)(b)) |
| Delivering notifications (LINE / Email / Telegram) | Consent (Art. 6(1)(a)) |
| Maintaining delivery logs to prevent duplicate notifications | Legitimate interests (Art. 6(1)(f)) |
| Improving the Service, planning new features, troubleshooting | Legitimate interests |
| Preventing and responding to violations of the Terms of Service | Legitimate interests |
| Responding to inquiries and complaints | Performance of a contract / legitimate interests |
| Creating statistical information in a non-identifiable form | Legitimate interests |
| Retention or disclosure required by law | Legal obligation (Art. 6(1)(c)) |

For processing based on consent, you may withdraw consent at any time. Withdrawal affects only future processing and does not affect the lawfulness of processing carried out before the withdrawal.

---

## 3. Disclosure to Third Parties

We do not disclose personal information to third parties without user consent, except in the following cases:

- When required by law
- When necessary for the protection of life, body, or property of any person
- When necessary for public health or the wholesome development of children
- When cooperating with national or local government agencies in carrying out legal duties

We **do not sell** user personal information to third parties for monetary or other consideration.

---

## 4. Outsourcing and Transmission to Third-Party Services

The Service transmits or retrieves data through the following external services. These are categorized either as "outsourcees" (entities to which we entrust the handling of personal information) or "third parties" (entities with which the user separately establishes a relationship). For outsourcees, we require appropriate security measures and supervise them as needed. Each service is governed by its own privacy policy.

| Purpose | Provider | Category | Data |
|---------|----------|----------|------|
| Social login | LINE / Google / X | Third party | OAuth credentials |
| Blockchain data | Koios API | Public data fetch | Stake addresses (query) |
| Notification delivery | LINE Messaging API | Outsourcee | LINE user ID + content |
| Notification delivery | Telegram Bot API | Outsourcee | Telegram chat ID + content |
| Email delivery | SMTP provider | Outsourcee | Email + content |
| Translation / AI analysis | OpenAI API | Outsourcee | Governance proposal text |
| Price information | CoinGecko | No personal data | (no personal data sent) |
| Analytics | Google Analytics | Outsourcee | Anonymized access information |

---

## 5. International Data Transfers

Some providers listed above process data on servers outside of Japan (United States, European Union, or elsewhere). Depending on the destination, we apply one of the following safeguards to ensure an adequate level of protection:

- Reliance on adequacy decisions issued by the European Commission, the UK, or the Personal Information Protection Commission of Japan, where applicable
- In the absence of such adequacy decisions, we use the Standard Contractual Clauses (SCCs) of the European Commission or other appropriate safeguards, or obtain the user's explicit consent

For the data protection details of each provider, please refer to the respective privacy policies. By using the Service, you consent to such cross-border transfers of personal information.

---

## 6. Cookies and Similar Technologies

The Service uses cookies and similar technologies for the following purposes.

| Category | Purpose | Consent |
|----------|---------|---------|
| Essential | Maintaining login session, security | No consent required (necessary for the Service) |
| Functional | Storing user preferences (language, display mode, etc.) | Treated as essential |
| Analytics | Access analytics (Google Analytics) | Consent (opt-in) |

You may manage these via your browser settings or the cookie settings provided by the Service. You may disable non-essential cookies at any time.

### 6-1. Google Consent Mode v2

The Service implements Google Consent Mode v2. When a user has not consented to analytics cookies, Google Analytics does not write persistent cookies and does not store information that identifies the user. However, **anonymized pings (cookieless pings)** are sent to Google for aggregate measurement of page visits. These pings have the following characteristics:

- No persistent identifiers (cookies, IP-based IDs, etc.) are stored or transmitted
- No information that identifies an individual user is included; returning visitors are not linked across sessions
- Used solely by Google for aggregate modeling

If you wish to block all communication, including these anonymized pings, please use a browser extension (such as uBlock Origin) or operating-system-level settings to block requests to Google Analytics directly.

---

## 7. Security Measures

We implement appropriate measures to prevent leakage, loss, destruction, and unauthorized acquisition of personal information we collect, as well as information we plan to handle as personal data.

- HTTPS communication
- Database access restrictions
- Encrypted storage of authentication credentials
- Periodic rotation of authentication tokens
- Vulnerability monitoring of dependencies to prevent injection of malicious code into the frontend
- Restrictions on execution of unauthorized scripts via Content Security Policy and similar mechanisms

---

## 8. Response to Data Breaches

In the event of a leakage, loss, damage, or other incident concerning the security of personal information (including cases where information we plan to handle as personal data is at risk of leakage due to unauthorized access such as web skimming) occurs or is likely to have occurred, we will promptly:

- Report to the Personal Information Protection Commission of Japan (under the APPI)
- Notify affected users
- Where the GDPR applies, notify the competent supervisory authority within 72 hours (GDPR Art. 33)

---

## 9. Data Retention

We retain personal information only for as long as necessary to fulfill the purposes outlined in this Policy. Typical retention periods are as follows.

| Data Category | Retention |
|--------------|-----------|
| Account information (username, email, OAuth ID, etc.) | Deleted within 30 days after account deletion request |
| Stake addresses, notification settings, favorites | Deleted within 30 days after account deletion request |
| Notification delivery logs | 90 days |
| Server access logs | 90 days |
| Authentication sessions and tokens | Deleted upon expiration (typically 7–30 days) |

Where retention is otherwise required by law, we retain the data for the legally required period.

---

## 10. Your Rights

Users may exercise the following rights regarding personal information held by us, subject to applicable law:

- **Right to Access**: Request access to your personal information
- **Right to Rectification / Erasure**: Request correction of inaccurate data or deletion of unnecessary data
- **Right to Restriction / Object**: Request restriction of processing or object to processing
- **Right to Data Portability**: Receive personal information in a machine-readable format (where the GDPR applies)
- **Right to Withdraw Consent**: Withdraw consent at any time for processing based on consent
- **Right not to be Subject to Automated Decision-making**: We do not make significant decisions through fully automated means
- **Right to Lodge a Complaint**: File a complaint with the data protection authority of your country of residence

You can directly edit or delete items such as username, email, stake address nickname, notification settings, and favorites from the My Page section of the Service. For other requests or where direct editing is not technically possible, please contact us through the inquiries window in Section 16. We will respond within a reasonable period after verifying your identity.

---

## 11. Additional Information for California Residents (CCPA / CPRA)

If you reside in California, USA, the rights in this Section and Section 10 apply to you.

### Categories of Personal Information Collected (last 12 months)

- Identifiers (username, email, OAuth ID, IP address)
- Internet activity (browser type, referrer URL, browsing history)
- Approximate location (country/region inferred from IP address)

### Sources

- Directly from users (form input, OAuth login)
- Automatically (cookies, logs, analytics)
- Third-party social login providers (LINE / Google / X)

### Business Purposes

As stated in Section 2.

### Third-Party Disclosures

As stated in Section 3 (Disclosure to Third Parties) and Section 4 (Outsourcing and Third-Party Services).

### Sale or Sharing of Personal Information

We **do not sell or share** user personal information.

### Rights of California Residents

- Right to Know
- Right to Delete
- Right to Correct
- Right to Opt-out of Sale/Sharing (not applicable since we do not sell or share)
- Right to Limit Use of Sensitive Personal Information
- Right to Non-Discrimination

To exercise these rights, please contact us through Section 16.

---

## 12. Additional Information for EU and UK Residents (GDPR)

If you reside in an EU Member State, the United Kingdom, Switzerland, Iceland, Norway, or Liechtenstein, the rights in this Section and Section 10 apply to you.

### Data Controller

Kuhito Co., Ltd. is the data controller as stated in Section 16.

### Data Protection Officer (DPO)

We have determined that the appointment of a Data Protection Officer under GDPR Art. 37 is not required at this time. For inquiries related to data protection, please contact us via Section 16.

### Right to Lodge a Complaint with a Supervisory Authority

You have the right to lodge a complaint with the data protection supervisory authority of your country of residence within the EU/UK.

---

## 13. Minors

The Service is not available to users under 13. Users between 13 and 18 must use the Service with parental consent. Where the GDPR applies, parental consent is required for users between 13 and 16 in accordance with the age requirements set by each Member State.

---

## 14. Changes to This Policy

We may update this Policy as needed. For material changes, we will notify users by posting on the Service and, where applicable, by sending an email to the registered email address.

---

## 15. Governing Law

This Policy is governed by and construed in accordance with the laws of Japan. This does not affect the application of mandatory rules of the country or region of residence (such as the GDPR or CCPA) to residents of those areas.

---

## 16. Inquiries and Complaints

For inquiries regarding this Policy, requests concerning retained personal data, or to file complaints, please contact us at:

- Company: Kuhito Co., Ltd.
- Representative: Yu Kagaya
- Address: Mutsumi Building 3F, 2-10-48 Kitasaiwai, Nishi-ku, Yokohama, Kanagawa, Japan
- Email: contact@kuhito.co.jp
"""


@template(route="/privacy", title="Privacy Policy | Cardanoism")
def privacy_page() -> rx.Component:
    return bilingual_markdown(_PRIVACY_JA, _PRIVACY_EN)
