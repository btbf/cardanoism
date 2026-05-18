"""terms.py
利用規約 (/terms)

JA / EN は AuthState.language で切り替え。
本文は長文なのでモジュールレベル定数で保持。
"""
from __future__ import annotations

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.components.markdown_doc import bilingual_markdown


_TERMS_JA = """\
# 利用規約

本利用規約（以下「本規約」といいます。）は、株式会社クヒト（以下「当社」といいます。）が提供する Cardanoism（以下「本サービス」といいます。）の利用条件を定めるものです。本サービスを利用するすべてのユーザーは、本規約に同意したものとみなします。

最終更新日: 2026 年 5 月 18 日

---

## 1. 適用

本規約は、ユーザーと当社との間の本サービス利用に関する一切の関係に適用されます。当社が個別に定める個別規定がある場合、本規約とあわせて適用されます。

---

## 2. 定義

本規約において用いる用語の定義は以下のとおりです。

- **本サービス**: 当社が提供する Cardano ブロックチェーンに関する情報提供・通知サービス Cardanoism
- **ユーザー**: 本サービスを利用するすべての個人または法人
- **コンテンツ**: 本サービス上で当社、ユーザーまたは第三者が掲載する情報、データ、テキスト、画像、ソフトウェア等
- **アカウント**: 本サービスを利用するために必要な、ソーシャルログインを通じて作成される利用者識別

---

## 3. ベータ版に関する留意事項

本サービスは現在ベータ版として提供されており、当社は本サービスの仕様を予告なく変更し、または提供を一時停止・終了することがあります。ベータ版利用に伴う以下の事項について、ユーザーはあらかじめ承諾するものとします。

- 機能や UI の予告なき変更
- データの不整合、表示の誤り、通知の遅延または欠落
- 一時的な利用停止やサービス終了

---

## 4. アカウント登録

1. 本サービスの利用には、対応するソーシャルログイン (LINE / Google / X 等) を通じたアカウント作成が必要です。
2. ユーザーは、自己の責任において自身のアカウントを管理するものとし、第三者にアカウントを譲渡、貸与してはなりません。
3. アカウントの不正利用により生じた損害について、当社は一切の責任を負いません。

---

## 5. 提供サービス

当社は、以下のような機能を本サービスとして提供します。

- Cardano ブロックチェーンに関する情報の閲覧 (ガバナンスアクション、DRep、SPO、トレジャリー等)
- ステークアドレスの登録・委任先のモニタリング
- 通知配信 (LINE / メール / Telegram)
- ウォレット連携によるオンチェーン委任トランザクションの構築支援
- ユーザー個別ダッシュボード

提供する具体的な機能は予告なく変更されることがあります。

---

## 6. 有料プラン (サブスクリプション)

### 6-1. 一般

1. 当社は本サービスの一部機能を有料プラン (サブスクリプション) として提供することがあります。
2. 有料プランの価格、内容、契約期間等は、[プラン一覧ページ](/pricing) および [特定商取引法に基づく表記](/tokushoho) に記載の内容に従います。

### 6-2. 決済

1. 決済は Stripe, Inc. を通じて行われ、お支払い方法はクレジットカードに対応します (Visa / Mastercard / JCB / American Express / Diners Club)。
2. 当社はカード情報を直接保持しません。決済情報の取扱いは [Stripe 社のプライバシーポリシー](https://stripe.com/privacy) に従います。

### 6-3. 自動更新

1. 月額プランはお申込み日と同じ日付に**毎月自動更新**されます (例: 5 日に申込 → 翌月 5 日、翌々月 5 日…)。
2. 年額プランは申込み日と同じ日付に**毎年自動更新**されます。
3. 解約の意思表示がない限り、契約は同条件で自動継続するものとします。

### 6-4. 解約

1. ユーザーは、ログイン後の [マイページ > サブスクリプションタブ](/mypage?tab=subscription) からいつでも解約できます。
2. 解約後も、現在の課金期間の末日までは有料機能をご利用いただけます。
3. 次回更新日以降は課金されません。
4. 解約後の再開はいつでも可能ですが、過去の利用期間は引き継がれません。

### 6-5. 価格変更

1. 当社は、合理的な範囲で有料プランの価格を変更することができます。
2. 価格変更時は、変更日の **30 日前まで**に本サービスおよびご登録のメールアドレスにて通知します。
3. 価格変更に同意できない場合、ユーザーは変更日までに解約することができます。

### 6-6. 支払い失敗時の取り扱い

1. 自動更新時にカード会社等の事由で決済が失敗した場合、当社は所定の期間 (3 日後 / 5 日後 / 7 日後) にリトライします。
2. リトライ期間中も繰返し失敗した場合、有料機能の利用を一時停止し、Free プランに自動的にダウングレードされる場合があります。
3. 再度有効な支払い方法を登録すれば、いつでもプランを再開できます。

### 6-7. 返金

1. 既にお支払いいただいた期間分の料金は、法令に別段の定めがある場合または [特定商取引法に基づく表記](/tokushoho) に定める例外事由に該当する場合を除き、**返金いたしません**。
2. 重大なサービス障害等の例外事由が発生した場合、個別に返金等の対応を検討します。

### 6-8. ベータ期間

1. 本サービスはベータ期間中、有料プランの一部機能を全ユーザーに無料で開放することがあります。
2. ベータ期間の終了および機能開放範囲の変更は、当社の裁量で行うことができ、その際は事前に本サービス上で告知します。

### 6-9. プラン変更 (アップグレード / ダウングレード)

1. ユーザーは [マイページ > サブスクリプションタブ](/mypage?tab=subscription) からいつでも他の有料プランへ変更 (アップグレード / ダウングレード) できます。
2. **アップグレード** (上位プランへの変更) は変更操作の完了時点で即時反映され、次回更新日までの残日数に応じた差額が変更時点で課金されます。
3. **ダウングレード** (下位プランまたは Free プランへの変更) は、現在の課金期間の末日まで現プランの機能を維持し、次回更新日から新プランが適用されます。差額の返金は行いません。
4. 請求サイクル変更 (月額 ↔ 年額) も同様の取扱いとし、アップグレードは即時 + 日割り課金、ダウングレードは次回更新日から適用とします。

### 6-10. デジタルコンテンツに関する留意事項

1. 本サービスの有料プランは、特定商取引法に定める「指定権利」に該当しない**デジタルコンテンツ提供サービス**です。
2. 申込み完了 (購入手続きの確定) と同時に提供が開始されるため、**特定商取引法上のクーリングオフは適用されません**。
3. 詳細な販売条件は [特定商取引法に基づく表記](/tokushoho) を参照してください。

### 6-11. 未成年者の利用

1. 未成年者が有料プランに申込む場合、**法定代理人 (親権者等) の同意**を得たうえで申込むものとします。
2. 未成年者が法定代理人の同意を得ずに有料プランに申込んだ場合でも、当社が当該未成年者を成年であると誤認した場合、または未成年者もしくは法定代理人による追認があったとみなされる場合は、未成年者取消権を主張できないものとします。
3. 当社は、申込時にユーザーが満 18 歳未満であり、かつ法定代理人の同意が確認できないと判明した場合、申込みの承諾を拒否し、または契約を解除することがあります。

### 6-12. 申込みの成立と提供開始

1. 有料プランの利用契約は、ユーザーが申込み手続きを行い、**Stripe による決済が完了した時点**で当社とユーザーの間に成立します。
2. 利用契約の成立と同時に有料プランの提供を開始します。これにより、第 6-10 条のとおりクーリングオフは適用されません。
3. 当社は、決済の不成立、申込み内容の不備、その他正当な事由がある場合、申込みの承諾を留保または拒否することがあります。

### 6-13. 領収書および請求書

1. 各回の決済に対する領収書 (Receipt) は、Stripe からご登録のメールアドレスに自動配信されるほか、Stripe Customer Portal からいつでもダウンロードできます。
2. 適格請求書 (インボイス制度に基づく適格請求書) の発行を希望する場合は、第 16 章のお問い合わせ窓口までご連絡ください。当社の適格請求書発行事業者としての登録状況および対応可否については、お問い合わせ時にご案内します。
3. 領収書または請求書の再発行は、Stripe Customer Portal からの自己発行で対応いただくものとし、当社による個別再発行は原則として行いません。

---

## 7. ユーザーの責任

1. ユーザーは、自己の判断と責任で本サービスを利用するものとし、本サービスの利用により得られる情報の正確性・完全性について自ら確認するものとします。
2. ユーザーは、ウォレット秘密鍵、シードフレーズを含む認証情報を自身で管理するものとし、当社はこれらを保管しません。
3. ウォレット連携によるトランザクション (委任、投票等) はユーザー自身の判断と署名で実行されるものであり、当社は実行結果について一切責任を負いません。

---

## 8. 禁止事項

ユーザーは、本サービスの利用にあたって、以下の行為をしてはなりません。

1. 法令または公序良俗に違反する行為
2. 犯罪行為に関連する行為
3. マネーロンダリング、テロ資金供与その他金融犯罪に関連する行為、またはその助長
4. 当社、他のユーザー、または第三者の知的財産権、肖像権、プライバシー権、名誉、その他の権利または利益を侵害する行為
5. 当社のサーバーまたはネットワークの機能を破壊・妨害する行為
6. 本サービスのリバースエンジニアリング、逆コンパイル、または逆アセンブル
7. 本サービスを介した不正アクセス、クラッキング、攻撃の試行
8. 不正な手段によりアカウントを取得・利用する行為
9. 当社が許諾しない方法で本サービスを商業目的で利用する行為
10. 他のユーザーになりすます行為
11. その他、当社が不適切と判断する行為

---

## 9. アカウントの削除・利用停止

1. ユーザーは、本サービスからの退会を希望する場合、第 16 章のお問い合わせ窓口よりリクエストを送信してください。当社は合理的期間内にアカウントおよび関連する個人情報を削除します。
2. 当社は、ユーザーが以下のいずれかに該当すると判断した場合、事前の通知なくアカウントの利用を一時停止または削除することができます。
    - 本規約に違反した場合
    - アカウント情報に虚偽があることが判明した場合
    - 料金の支払債務を履行しない場合
    - 第 10 章の反社会的勢力に該当することが判明した場合
    - その他、当社が本サービスの利用を適当でないと判断した場合
3. アカウント停止または削除に伴い生じた損害について、当社は一切の責任を負いません。

---

## 10. 反社会的勢力の排除

ユーザーは、自身が現在も将来にわたって、暴力団、暴力団員、暴力団員でなくなったときから 5 年を経過しない者、暴力団準構成員、暴力団関係企業、総会屋、社会運動標榜ゴロ、特殊知能暴力集団、その他これらに準ずる者 (以下「反社会的勢力」といいます。) のいずれにも該当しないこと、および反社会的勢力と関係を有しないことを表明し保証します。これに違反した場合、当社は何らの催告なく直ちに本サービスの利用契約を解除することができます。

---

## 11. 知的財産権

1. 本サービスおよび当社が掲載するコンテンツに関する著作権その他の知的財産権は、当社または当該コンテンツの権利者に帰属します。
2. ユーザーは、本サービスを利用する目的の範囲内において、これらを利用することができます。
3. ブロックチェーン上の公開情報やユーザーが投稿した情報は、それぞれの権利者または投稿者に帰属します。

---

## 12. 免責事項

1. 当社は、本サービスの内容、提供されるコンテンツの正確性、完全性、有用性、特定目的への適合性、合法性等について、いかなる保証も行いません。
2. 当社は以下の事由による損害について一切責任を負いません。
    - 本サービスの利用または利用不能から生じた損害
    - 通知の遅延、誤配信、欠落、または重複配信
    - 第三者サービス (Koios / LINE / Telegram / OpenAI / SMTP / Google Analytics 等) の不具合、停止、仕様変更による影響
    - ウォレット連携によって構築されたトランザクションの送信結果 (失敗、二重送信、想定外の効果等)
    - Cardano ブロックチェーン自体の障害、ハードフォーク、ネットワーク混雑等
    - ユーザーが本サービスから得た情報をもとに行った判断・行動の結果
3. **AI 生成コンテンツに関する免責**

    本サービスは、ガバナンス提案の要約や Cardano 憲法の参考訳など、生成 AI (OpenAI 等の大規模言語モデルを含みます。以下「AI」といいます。) を用いて自動生成されたコンテンツを含みます。AI 生成コンテンツについて、ユーザーは以下の事項にあらかじめ同意するものとします。

    - AI 生成コンテンツはその性質上、**不正確・不完全・偏った内容、または事実と異なる内容（いわゆるハルシネーション）を含む可能性があります**。当社はその正確性・完全性・最新性を保証しません。
    - AI 生成コンテンツは**情報提供のみを目的としたものであり、投資判断、税務、法務、その他いかなる専門的助言にも該当しません**。ガバナンス投票、委任先 (SPO / DRep) の選択、ウォレット署名を伴うトランザクション実行を含む、本サービスから得た情報に基づく一切の意思決定は、ユーザー自身の責任で行うものとします。
    - AI の提供事業者によるモデルの仕様変更、廃止、出力規制等により、AI 生成コンテンツの品質・内容・継続提供が予告なく変動または停止する可能性があります。
    - AI 生成コンテンツに、第三者の著作権、商標権、肖像権、プライバシー権その他の権利を侵害する内容が含まれる可能性を完全に排除することはできません。当該コンテンツに起因してユーザーまたは第三者に損害が生じた場合でも、当社は一切責任を負いません。
4. 当社が責任を負う場合であっても、当社の責任の範囲は、当該ユーザーが直近 12 か月間に当社に支払った料金の総額を上限とします。

---

## 13. サービスの変更・停止

当社は、ユーザーへの通知なく本サービスの内容を変更し、または提供を停止・終了することができます。これにより生じた損害について当社は責任を負いません。

---

## 14. 規約の変更

当社は、必要に応じて本規約を変更することがあります。変更後の規約は本サービス上に掲示した時点で効力を生じ、ユーザーが本サービスの利用を継続することにより、変更後の規約に同意したものとみなします。

---

## 15. 準拠法および管轄裁判所

1. 本規約の解釈および適用は、日本法に準拠します。
2. 本サービスに関して当社とユーザーとの間で紛争が生じた場合、横浜地方裁判所を第一審の専属的合意管轄裁判所とします。

---

## 16. お問い合わせ

本規約に関するお問い合わせは、以下までご連絡ください。

- 事業者名: 株式会社クヒト
- 代表者: 加賀谷 侑
- 所在地: 神奈川県横浜市西区北幸二丁目10番48号 むつみビル3階
- メール: contact@kuhito.co.jp
"""


_TERMS_EN = """\
# Terms of Service

These Terms of Service ("Terms") govern the use of Cardanoism (the "Service") provided by Kuhito Co., Ltd. ("we", "our", or "us"). By using the Service, all users are deemed to have agreed to these Terms.

Last updated: May 18, 2026

---

## 1. Application

These Terms apply to all relationships between users and us regarding use of the Service. If we establish individual rules for specific features, those apply in addition to these Terms.

---

## 2. Definitions

The following terms are used in these Terms with the meanings indicated:

- **Service**: Cardanoism, the Cardano blockchain information and notification service provided by us
- **User**: Any individual or legal entity who uses the Service
- **Content**: Information, data, text, images, software, etc. posted on the Service by us, users, or third parties
- **Account**: User identification created through social login required to use the Service

---

## 3. Beta Status

The Service is currently provided in beta. We may change specifications without notice and may suspend or terminate the Service. Users acknowledge and accept the following beta-related conditions:

- Changes to features or UI without prior notice
- Data inconsistencies, display errors, notification delays or losses
- Temporary suspension or termination of service

---

## 4. Account Registration

1. To use the Service, users must create an account through supported social login providers (LINE / Google / X, etc.).
2. Users are responsible for managing their own accounts and must not transfer or lend their account to third parties.
3. We are not liable for any damages arising from unauthorized use of an account.

---

## 5. Service Description

We provide the following features as part of the Service:

- Browsing Cardano blockchain information (governance actions, DReps, SPOs, treasury, etc.)
- Stake address registration and delegation monitoring
- Notification delivery (LINE / Email / Telegram)
- Wallet integration for on-chain delegation transaction building
- User-specific dashboards

The specific features may change without notice.

---

## 6. Paid Plans (Subscriptions)

### 6-1. General

1. We may offer some features of the Service as paid plans (subscriptions).
2. Pricing, contents, and contract period are listed on the [Pricing page](/pricing) and the [Commercial Transactions Notice](/tokushoho).

### 6-2. Payments

1. Payments are processed through Stripe, Inc. and accepted via credit cards (Visa / Mastercard / JCB / American Express / Diners Club).
2. We do not directly hold card details. Stripe handles them in accordance with the [Stripe Privacy Policy](https://stripe.com/privacy).

### 6-3. Auto-renewal

1. Monthly plans **renew automatically every month** on the same date as the original signup.
2. Yearly plans **renew automatically every year** on the same date.
3. Unless cancelled, the contract continues automatically under the same terms.

### 6-4. Cancellation

1. You can cancel anytime from [My Page > Subscription tab](/mypage?tab=subscription) after signing in.
2. After cancellation, you may continue to use paid features until the end of the current billing period.
3. You will not be charged for the next billing cycle.
4. You can resubscribe at any time, but past usage periods are not carried over.

### 6-5. Price changes

1. We may change paid plan prices within reasonable bounds.
2. We will notify you of any price change via the Service and the registered email address **at least 30 days in advance**.
3. If you do not agree to the new price, you may cancel before the change takes effect.

### 6-6. Failed payments

1. If a renewal payment fails (e.g., due to card issuer reasons), we will retry on a defined schedule (3 / 5 / 7 days later).
2. If retries continue to fail, paid features may be suspended and the account may be downgraded to the Free plan.
3. Once a valid payment method is registered, you can resume the plan at any time.

### 6-7. Refunds

1. Fees already paid for the elapsed billing period are **non-refundable**, except as required by law or as specified in the [Commercial Transactions Notice](/tokushoho).
2. In the case of a major service outage or other exceptional events, we will consider refunds on a case-by-case basis.

### 6-8. Beta period

1. During the beta period, we may offer paid-plan features for free to all users.
2. Termination of the beta period and changes to the scope of free features are at our discretion, and will be announced on the Service in advance.

### 6-9. Plan changes (upgrade / downgrade)

1. Users may change their paid plan (upgrade or downgrade) at any time from [My Page > Subscription tab](/mypage?tab=subscription).
2. **Upgrades** (to a higher plan) take effect immediately upon completion of the change. The prorated difference for the remaining days until the next renewal is charged at the time of the change.
3. **Downgrades** (to a lower plan or to the Free plan) maintain the current plan's features through the end of the current billing period; the new plan takes effect from the next renewal date. No refund is issued for the difference.
4. Changing the billing cycle (monthly ↔ yearly) follows the same rules: upgrades take effect immediately with a prorated charge; downgrades take effect from the next renewal.

### 6-10. Digital content notice

1. The paid plans of the Service are **digital content delivery services** and do not constitute "designated rights" under the Japanese Act on Specified Commercial Transactions.
2. Because service provision begins immediately upon order completion, **the cooling-off right under the Act on Specified Commercial Transactions does not apply**.
3. For detailed sales terms, please refer to the [Commercial Transactions Notice](/tokushoho).

### 6-11. Use by minors

1. Minors may subscribe to paid plans only with the consent of a **legal representative (such as a parent or guardian)**.
2. If a minor subscribes without legal representative consent, and either we reasonably believe the user to be an adult, or the minor or legal representative is deemed to have ratified the subscription, the minor may not invoke the right to rescind on grounds of minority.
3. If we discover at the time of application that a user is under 18 years old and that legal representative consent cannot be verified, we may refuse to accept the application or terminate the contract.

### 6-12. Formation of contract and start of service

1. A paid-plan service contract between us and the user is formed at the moment **payment via Stripe is successfully completed** after the user submits the application.
2. The paid plan is provided immediately upon formation of the contract. As such, the cooling-off right does not apply, as stated in § 6-10.
3. We may withhold or refuse acceptance of an application in the event of failed payment, deficient application details, or other reasonable grounds.

### 6-13. Receipts and invoices

1. A receipt for each payment is automatically sent by Stripe to the registered email address and is also downloadable at any time from the Stripe Customer Portal.
2. If you require a qualified invoice (適格請求書) under the Japanese Qualified Invoice System, please contact us via the channel in § 16. We will inform you of our registration status as a qualified invoice issuer and the available options when you contact us.
3. Re-issuance of receipts or invoices is handled via self-service at the Stripe Customer Portal; we do not, as a rule, re-issue them on an individual basis.

---

## 7. User Responsibilities

1. Users use the Service at their own discretion and responsibility, and must verify the accuracy and completeness of any information obtained through the Service.
2. Users are responsible for managing their wallet private keys, seed phrases, and other authentication credentials. We do not store these.
3. Wallet-integrated transactions (delegation, voting, etc.) are executed by the user's own decision and signature; we bear no responsibility for the results.

---

## 8. Prohibited Conduct

When using the Service, users must not engage in any of the following:

1. Acts that violate laws or public order and morals
2. Acts related to criminal activities
3. Acts related to or facilitating money laundering, terrorist financing, or other financial crimes
4. Acts that infringe intellectual property rights, portrait rights, privacy rights, honor, or other rights or interests of us, other users, or third parties
5. Acts that destroy or interfere with the functioning of our servers or networks
6. Reverse engineering, decompilation, or disassembly of the Service
7. Unauthorized access, cracking, or attack attempts via the Service
8. Acquiring or using accounts through fraudulent means
9. Using the Service for commercial purposes in ways not permitted by us
10. Impersonating other users
11. Other acts deemed inappropriate by us

---

## 9. Account Deletion and Suspension

1. Users wishing to withdraw from the Service may submit a request through the contact information in Section 16. We will delete the account and related personal information within a reasonable period.
2. We may suspend or delete a user's account without prior notice if we determine that the user falls under any of the following:
    - Violation of these Terms
    - Falsification of account information
    - Failure to pay fees
    - Falling under the anti-social forces described in Section 10
    - Any other case where we deem the use of the Service inappropriate
3. We are not liable for any damages arising from account suspension or deletion.

---

## 10. Exclusion of Anti-Social Forces

Users represent and warrant that they do not currently and will not in the future fall under organized crime groups, members of organized crime groups, persons for whom less than five years have passed since they ceased to be members of organized crime groups, quasi-members of organized crime groups, companies related to organized crime groups, sokaiya (corporate extortionists), groups engaging in criminal activities under the pretext of conducting social campaigns, crime groups specialized in intellectual crimes, or other persons equivalent thereto (collectively, "Anti-Social Forces"), nor have any relationship with Anti-Social Forces. If a user breaches this representation, we may immediately terminate the Service contract without any notice.

---

## 11. Intellectual Property

1. Copyrights and other intellectual property rights related to the Service and the content we publish belong to us or the rightful owners of such content.
2. Users may use these only within the scope of using the Service.
3. Public on-chain information and information posted by users belong to their respective rights holders or contributors.

---

## 12. Disclaimer

1. We make no warranties regarding the content of the Service, the accuracy, completeness, usefulness, fitness for a particular purpose, or legality of provided content.
2. We are not liable for any damages arising from the following:
    - Damages caused by use or inability to use the Service
    - Notification delays, misdelivery, loss, or duplication
    - Effects of third-party service (Koios / LINE / Telegram / OpenAI / SMTP / Google Analytics, etc.) failures, suspensions, or specification changes
    - Results of transactions built via wallet integration (failures, double-sending, unintended effects, etc.)
    - Failures of the Cardano blockchain itself, hard forks, network congestion, etc.
    - Decisions or actions made based on information obtained from the Service
3. **Disclaimer regarding AI-generated content**

    The Service includes content automatically generated by generative AI (including large language models provided by OpenAI and others; hereinafter "AI"), such as summaries of governance actions and reference translations of the Cardano Constitution. With respect to AI-generated content, the user agrees in advance to the following:

    - AI-generated content may, by its nature, **contain inaccurate, incomplete, biased, or factually incorrect information (so-called hallucinations)**. We make no warranty as to its accuracy, completeness, or currency.
    - AI-generated content is provided **for informational purposes only and does not constitute investment, tax, legal, or any other professional advice**. All decisions made based on information obtained from the Service — including governance voting, delegation choice (SPO / DRep), and execution of wallet-signed transactions — are the sole responsibility of the user.
    - The quality, content, or continued availability of AI-generated content may change or be discontinued without notice due to model specification changes, deprecations, or output restrictions imposed by the AI provider.
    - We cannot completely rule out the possibility that AI-generated content may include material that infringes the copyright, trademark, portrait, privacy, or other rights of third parties. We bear no liability for any damage caused to the user or third parties arising from such content.
4. Even if we are liable, our liability is limited to the total amount paid by the user to us in the most recent 12 months.

---

## 13. Service Modifications and Suspension

We may change, suspend, or terminate the Service without notice to users. We are not liable for any damages arising therefrom.

---

## 14. Changes to Terms

We may revise these Terms as necessary. Revised Terms take effect when posted on the Service, and continued use by the user constitutes agreement to the revised Terms.

---

## 15. Governing Law and Jurisdiction

1. These Terms shall be interpreted and applied in accordance with the laws of Japan.
2. Any disputes arising between us and a user regarding the Service shall be subject to the exclusive jurisdiction of the Yokohama District Court as the court of first instance.

---

## 16. Contact

For inquiries regarding these Terms, please contact us at:

- Company: Kuhito Co., Ltd.
- Representative: Yu Kagaya
- Address: Mutsumi Building 3F, 2-10-48 Kitasaiwai, Nishi-ku, Yokohama, Kanagawa, Japan
- Email: contact@kuhito.co.jp
"""


@template(route="/terms", title="Terms of Service | Cardanoism")
def terms_page() -> rx.Component:
    return bilingual_markdown(_TERMS_JA, _TERMS_EN)
