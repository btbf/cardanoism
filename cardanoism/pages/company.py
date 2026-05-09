"""company.py
会社概要ページ (/company)

Cardanoism を運営する株式会社クヒトの基本情報を掲載。
Stripe / LINE / 各種サービス審査時に提出する公式情報源として機能する。

JA / EN は AuthState.language で切り替え。
"""
from __future__ import annotations

import reflex as rx

from cardanoism.templates import template
from cardanoism.backend.auth_state import AuthState
from cardanoism.components.markdown_doc import bilingual_markdown


_COMPANY_JA = """\
# 会社概要

Cardanoism は **株式会社クヒト** が運営しています。

---

## 会社情報

| 項目 | 内容 |
|------|------|
| 商号 | 株式会社クヒト (Kuhito Co., Ltd.) |
| 代表者 | 代表取締役 加賀谷 侑 |
| 所在地 | 〒 220-0004<br/>神奈川県横浜市西区北幸二丁目 10 番 48 号 むつみビル 3 階 |
| 電話番号 | 045-900-6867 |
| メールアドレス | contact@kuhito.co.jp |
| ホームページ | [https://cardanoism.com](https://cardanoism.com) |
| 事業内容 | ・Cardano エコシステム向け Web サービス「Cardanoism」の企画・開発・運営<br/>・ブロックチェーン関連情報サービスの提供<br/>・ステーキングプール (SPO) 運営支援 |

---

## ミッション

Cardanoism は、Cardano ブロックチェーンに参加するすべての ADA ホルダーに対して、**「ガバナンス・ステーキング・Catalyst をひとつのダッシュボードで」** という体験を提供することを目指しています。

ブロックチェーン技術の専門知識がなくても、自分の委任先の状況を確認したり、新しいガバナンスアクションに気づいたり、安心して報酬を受け取り続けられる環境を整えることが、私たちの役目です。

---

## 提供サービス

### Cardanoism (https://cardanoism.com)

Cardano ブロックチェーンに関する以下の機能を提供する Web サービスです。

- ガバナンスアクションの閲覧と AI 要約
- 登録 DRep の投票マトリクス表示
- ステークプールの統計情報・委任先選定支援
- リアルタイム通知 (LINE / Telegram / メール)
- ステーキング報酬・プール状態の自動アラート
- Catalyst 提案の検索・お気に入り管理
- Cardano 憲法の日本語訳

無料プランから始められ、機能に応じて月額のサブスクリプションプランをご用意しています。

---

## お問い合わせ

サービスに関するご質問・お問い合わせは下記までお願いします。

- **メール**: contact@kuhito.co.jp
- **電話**: 045-900-6867 (平日 10:00〜18:00、土日祝・年末年始除く)
- **問い合わせフォーム**: [/contact](/contact)
"""


_COMPANY_EN = """\
# Company Information

Cardanoism is operated by **Kuhito Co., Ltd.**

---

## Company details

| Item | Content |
|------|---------|
| Company name | Kuhito Co., Ltd. (株式会社クヒト) |
| Representative | Yu Kagaya, Representative Director |
| Address | 3F Mutsumi Building, 2-10-48 Kitasaiwai, Nishi-ku, Yokohama, Kanagawa 220-0004, Japan |
| Phone | +81-45-900-6867 |
| Email | contact@kuhito.co.jp |
| Website | [https://cardanoism.com](https://cardanoism.com) |
| Business | • Planning, development, and operation of Cardanoism — a web service for the Cardano ecosystem<br/>• Information services related to blockchain<br/>• Stake pool (SPO) operation support |

---

## Mission

Cardanoism aims to give every ADA holder a single dashboard for **governance, staking, and Catalyst**.

You don't need to be a blockchain expert to keep track of your delegations, notice new governance actions, or steadily collect your rewards. Our role is to make that environment effortless.

---

## What we offer

### Cardanoism (https://cardanoism.com)

A web service providing the following features for the Cardano blockchain:

- Browse governance actions with AI summaries
- DRep vote matrix at a glance
- Stake pool statistics and delegation tools
- Real-time notifications via LINE / Telegram / Email
- Automatic alerts for staking rewards and pool status
- Catalyst proposal search and favorites
- Japanese translation of the Cardano Constitution

Available from a free plan, with paid monthly subscription tiers for advanced features.

---

## Contact

For questions or inquiries about our services, please reach out:

- **Email**: contact@kuhito.co.jp
- **Phone**: +81-45-900-6867 (Mon–Fri 10:00–18:00 JST, excluding national holidays)
- **Contact form**: [/contact](/contact)
"""


@template(
    route="/company",
    title="会社概要 | Cardanoism",
)
def company_page() -> rx.Component:
    return bilingual_markdown(_COMPANY_JA, _COMPANY_EN)
