"""tokushoho.py
特定商取引法に基づく表記 (/tokushoho)

日本の有料サービス事業者に法令で求められる開示事項を掲載する。
Stripe 等の決済プロバイダ申込時にもこのページの URL を提示する。

JA / EN は AuthState.language で切り替え。
"""
from __future__ import annotations

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.components.markdown_doc import bilingual_markdown


_TOKUSHOHO_JA = """\
# 特定商取引法に基づく表記

特定商取引に関する法律 第 11 条に基づき、当社が運営する Cardanoism（以下「本サービス」）の有料プランに関する事項を以下のとおり表示します。

最終更新日: 2026 年 5 月 9 日

---

## 販売事業者

株式会社クヒト

## 代表者

加賀谷 侑

## 所在地

〒 220-0004
神奈川県横浜市西区北幸二丁目 10 番 48 号 むつみビル 3 階

## 電話番号

045-900-6867

（受付時間: 平日 10:00〜18:00、土日祝・年末年始を除く）

ご請求があった場合は遅滞なく開示いたします。お問い合わせは下記メールアドレスを推奨します。

## メールアドレス

contact@kuhito.co.jp

## ホームページ URL

https://cardanoism.com

---

## 販売価格

各プランの月額・年額は [プラン一覧ページ](/pricing) に表示しています（すべて消費税込）。

| プラン | 月額 | 年額 (2 ヶ月分割引) |
|--------|------|---------------------|
| Free | ¥0 | ¥0 |
| Light | ¥330 | ¥3,300 |
| Standard | ¥880 | ¥8,800 |
| Plus | ¥1,580 | ¥15,800 |
| Pro | ¥2,980 | ¥29,800 |

価格は予告なく変更される場合があります。変更の場合は事前に本サービスおよびご登録のメールアドレスにて通知します。

## 商品・サービス代金以外の必要料金

- インターネット接続料金、通信料金等はお客様のご負担となります。
- 国際取引に伴う為替手数料・カード会社所定の手数料が発生する場合があります。

---

## 支払方法

クレジットカード（Visa / Mastercard / JCB / American Express / Diners Club）

決済処理は Stripe, Inc. を通じて行われます。当社はカード番号等の決済情報を直接保持しません。

## 支払時期

- **月額プラン**: お申込み時にご請求し、以降毎月同日に自動更新されます。
- **年額プラン**: お申込み時にご請求し、以降毎年同日に自動更新されます。

## 役務の提供時期

決済完了後、即時にご利用いただけます。

---

## キャンセル・返金について

### 解約方法

ログイン後の [マイページ > サブスクリプションタブ](/mypage?tab=subscription) よりいつでも解約申請が可能です。

### 解約のタイミング

- 解約申請後も、現在の課金期間の末日までサービスをご利用いただけます。
- 次回更新日以降は課金されません。

### 返金ポリシー

当社の役務はデジタル情報サービスの性質上、原則として **既にお支払いいただいた期間分の返金はいたしかねます**。ただし、以下の場合はお客様に返金等の対応を行います。

- 当社の責に帰すべき重大な障害により、サービスが長時間（連続 24 時間以上）利用できなかった場合
- 二重決済等、決済システム上の明らかな誤りがあった場合
- その他、法令で返金が義務づけられる場合

返金をご希望の場合は contact@kuhito.co.jp 宛てにご連絡ください。

---

## 動作環境

- **推奨ブラウザ**: Google Chrome、Safari、Microsoft Edge、Firefox の最新版
- **対応 OS**: Windows 10 以降、macOS 11 以降、iOS 15 以降、Android 10 以降
- 古いブラウザ・OS では一部機能が動作しない場合があります。

---

## サービスの利用条件

- 本サービスのご利用には会員登録（LINE / Google / X いずれかでのログイン）が必要です。
- 利用にあたっては [利用規約](/terms) および [プライバシーポリシー](/privacy) に同意していただく必要があります。
- 反社会的勢力に該当する方、または当社が不適切と判断した方のご利用はお断りすることがあります。

---

## 個人情報の取り扱い

[プライバシーポリシー](/privacy) をご参照ください。
"""


_TOKUSHOHO_EN = """\
# Notation Based on the Specified Commercial Transaction Act

Pursuant to Article 11 of the Act on Specified Commercial Transactions of Japan, the following information is provided regarding the paid plans of Cardanoism (hereinafter, the "Service") operated by Kuhito Co., Ltd.

Last updated: May 9, 2026

---

## Seller

Kuhito Co., Ltd.

## Representative

Yu Kagaya

## Address

3F Mutsumi Building, 2-10-48 Kitasaiwai, Nishi-ku, Yokohama, Kanagawa 220-0004, Japan

## Phone

+81-45-900-6867

(Office hours: 10:00–18:00 JST, weekdays only, excluding national holidays and year-end period)

We will disclose the phone number without delay upon request. We recommend contacting us via email below.

## Email

contact@kuhito.co.jp

## Website

https://cardanoism.com

---

## Prices

Monthly and yearly prices for each plan are listed on the [Pricing page](/pricing) (all prices include consumption tax).

| Plan | Monthly | Yearly (2 months free) |
|------|---------|------------------------|
| Free | ¥0 | ¥0 |
| Light | ¥330 | ¥3,300 |
| Standard | ¥880 | ¥8,800 |
| Plus | ¥1,580 | ¥15,800 |
| Pro | ¥2,980 | ¥29,800 |

Prices may change without prior notice. We will notify you of any changes via the Service and the registered email address in advance.

## Additional fees

- Internet and communication fees are the user's responsibility.
- Foreign exchange and card-network fees may apply for international transactions.

---

## Payment methods

Credit card (Visa / Mastercard / JCB / American Express / Diners Club).

Payments are processed through Stripe, Inc. We do not directly hold card details.

## Payment timing

- **Monthly plan**: Charged at signup, then auto-renewed on the same day each month.
- **Yearly plan**: Charged at signup, then auto-renewed on the same day each year.

## Service availability

Available immediately after payment is completed.

---

## Cancellation and refunds

### How to cancel

You can cancel anytime from [My Page > Subscription tab](/mypage?tab=subscription) after signing in.

### Cancellation timing

- After requesting cancellation, you can continue to use the Service until the end of the current billing period.
- You will not be charged for the next billing cycle.

### Refund policy

Due to the nature of digital information services, we generally **do not refund payments already made for the elapsed billing period**. However, we will provide refunds in the following cases:

- A major outage caused by us made the Service unavailable for an extended period (24 consecutive hours or more)
- Clear errors in the payment system, such as double charges
- Other cases where a refund is required by law

To request a refund, please contact contact@kuhito.co.jp.

---

## System requirements

- **Recommended browsers**: Latest versions of Google Chrome, Safari, Microsoft Edge, and Firefox
- **Supported OS**: Windows 10+, macOS 11+, iOS 15+, Android 10+
- Some features may not work on older browsers / operating systems.

---

## Conditions of use

- Account registration via LINE / Google / X is required to use the Service.
- You must agree to the [Terms of Service](/terms) and the [Privacy Policy](/privacy).
- We may decline service to any person identified as antisocial forces or otherwise deemed inappropriate by us.

---

## Personal information

Please see our [Privacy Policy](/privacy).
"""


@template(
    route="/tokushoho",
    title="特定商取引法に基づく表記 | Cardanoism",
)
def tokushoho_page() -> rx.Component:
    return bilingual_markdown(_TOKUSHOHO_JA, _TOKUSHOHO_EN)
