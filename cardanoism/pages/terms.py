"""terms.py
利用規約 (/terms)

JA / EN は AuthState.language で切り替え。
本文は長文なのでモジュールレベル定数で保持。
"""
from __future__ import annotations

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState


_TERMS_JA = """\
# 利用規約

本利用規約（以下「本規約」といいます。）は、株式会社クヒト（以下「当社」といいます。）が提供する Cardanoism（以下「本サービス」といいます。）の利用条件を定めるものです。本サービスを利用するすべてのユーザーは、本規約に同意したものとみなします。

最終更新日: 2026 年 5 月 7 日

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

1. 当社は本サービスの一部機能を有料プラン (サブスクリプション) として提供することがあります。
2. 有料プランの価格、内容、契約期間、更新方法、解約方法等は、本サービス上に別途掲示する条件によります。
3. 一度支払われた料金は、法令に別段の定めがある場合を除き返金されません。
4. ユーザーが料金の支払いを怠った場合、当社は当該ユーザーの有料機能の利用を停止することができます。

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
3. 当社が責任を負う場合であっても、当社の責任の範囲は、当該ユーザーが直近 12 か月間に当社に支払った料金の総額を上限とします。

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

Last updated: May 7, 2026

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

1. We may offer some features of the Service as paid plans (subscriptions).
2. The pricing, content, contract period, renewal, and cancellation terms of paid plans are governed by separately posted conditions on the Service.
3. Once paid, fees are non-refundable except as required by law.
4. If a user fails to pay fees, we may suspend the user's access to paid features.

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
3. Even if we are liable, our liability is limited to the total amount paid by the user to us in the most recent 12 months.

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
    return rx.box(
        rx.cond(
            AuthState.language == "ja",
            rx.markdown(_TERMS_JA),
            rx.markdown(_TERMS_EN),
        ),
        max_width="900px",
        width="100%",
        margin_x="auto",
        padding_x="16px",
        padding_y="24px",
    )
