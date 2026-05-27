"""POC: GA per-axis tag classification (drep-match v3)

指定した proposal_id 群について新プロンプトで axis_tags を AI 抽出し、
ターミナルに整形表示する。DB 書き込みは行わない (spot-check 専用)。

使い方:
  infisical run -- python scripts/poc_ga_axis_tags.py

PROPOSAL_IDS を編集して試したい GA を指定する。
"""
from __future__ import annotations

import json
import sys
import os

# プロジェクトルートを path に追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cardanoism.backend.db_connect import get_db
from cardanoism.backend.ai_client import _get_client, _send_with_retry, DEFAULT_MODEL  # noqa: E501


# spot-check 対象の proposal_id (10 件)
PROPOSAL_IDS: list[str] = [
    "gov_action1w0shrfxqwv95kk0v4cn34wylz25a2cmqkq5jpc0e2yrahhqava3qx4njfhm",
    "gov_action1hkgl5l4fknsf7aktmcatkz6kfl7xpvn7rzh5vnxwexl0n3cc6zrsqt5459v",
    "gov_action10dp9wzmgt2nqshyrghufff4sfhcxedhmzluly5k0azguatnsthwqqs84cjf",
    "gov_action1cp0w6zwgwpj98jtu3r2q838lgwmhs6j49l58zx4q05lx220lmzaqqztnljz",
    "gov_action142ndnn9hycuuwld5ddemash2l709ln06qjgfeudq77z45nf3fpdqqn7pwux",
    "gov_action1kj6ghzuz9wcq88f3y72cyyeekdcemlq0dqk4zpjd4eck5assuypqq0pckkw",
    "gov_action1pvv5wmjqhwa4u85vu9f4ydmzu2mgt8n7et967ph2urhx53r70xusqnmm525",
    "gov_action15ce4qnwug759939wqv782pvh6qg68khspg8kh02gmex99mcsytwqqqr7jkr",
    "gov_action1ggr2uz7prwn5l84cdn2krwngfez0p7wluy4u3u3ez9pz5ls2whesqnsjly8",
    "gov_action14u26vcn3wmcnhc5pqrt6494ypugr7c7f3e2ns60r32cntl6zjtxsqqgeu8p",
]


_SYSTEM = """\
You analyze a Cardano Governance Action (GA) and classify it along multiple axes
for use in a DRep matching diagnostic. Your job is to identify the GA's
intrinsic attributes (who benefits, what it does, its risk character) — NOT to
judge it as good or bad.

You receive:
- proposal_id, proposal_type, title, abstract

You output STRICTLY this JSON structure (no extra text):

{
  "treasury_size":     "large" | "small" | "n_a",
  "priority":          "technical" | "adoption" | "both" | "n_a",
  "org_recipient":     [array of org tags, possibly empty],
  "protocol_change":   "hard_fork" | "param_change" | "n_a",
  "marketing_purpose": "yes" | "no",
  "kpi_clarity":       "clear" | "unclear" | "n_a",
  "risk_level":        "high" | "low" | "n_a",
  "summary_ja":        "1 行で何の提案か (≤80 chars)",
  "reasoning": {
    "treasury_size":     "なぜそう判定したか (≤80 chars)",
    "priority":          "...",
    "org_recipient":     "...",
    "protocol_change":   "...",
    "marketing_purpose": "...",
    "kpi_clarity":       "...",
    "risk_level":        "..."
  }
}

# Classification rules

## treasury_size
- "large" : Treasury withdrawal で総額 >= 10,000,000 ADA (1000 万 ADA 以上)
- "small" : Treasury withdrawal で総額 < 10,000,000 ADA
- "n_a"   : Treasury 系ではない (ParameterChange / HardFork / InfoAction 等)

## priority (提案の目的軸)
- "technical" : プロトコル R&D、研究、セキュリティ、ノード/インフラ、開発者ツール、
                ライブラリ開発、コア保守
- "adoption"  : dApp、DeFi、ウォレット、ユーザー獲得、教育 / トレーニング
                (実用スキル向上)
- "both"      : **本当に 50:50 で両方が等しく主目的の場合のみ** 使う。
                迷ったら "both" ではなく「より強い側」を選ぶ。
                - 開発者ツール / ライブラリ / インフラ R&D → 常に technical
                - プロトコル研究 / セキュリティ / コア保守 → 常に technical
                - dApp / DeFi / ウォレット 開発 → 常に adoption
- "n_a"       : 以下は priority 軸の対象外 (marketing 軸で扱うため重複を避ける)。
                - イベント / サミット / カンファレンス / スポンサーシップ
                - 啓蒙 / 認知拡大 / 広告 / PR キャンペーン
                - コミュニティ拡大 (一般認知向上目的)
                その他 procedure-only / 抽象的 InfoAction なども n_a。

## org_recipient (受益組織を多重 array で。author ではなく実際に予算を受け取る組織)
- "IO"       : Input Output (IOG / IOHK)
- "CF"       : Cardano Foundation
- "Intersect": **実際に予算を Intersect 自身が受領して内部運営に使う場合のみ**。
               以下は "Intersect" に含めない:
                 - Intersect が代理で他組織のために提出している
                 - Intersect が管理 / 取りまとめ / オーケストレーション役割
                 - Intersect が事務局的に予算を流して別組織が実行
               迷ったら "Intersect" は **含めない**。
               (例: 「IO と Ensurable の保守予算を Intersect が管理」→ ["IO", "other"]
                のみ。Intersect は含めない)
- "Emurgo"   : Emurgo
- "Midnight" : Midnight (IO 系列だが別組織扱い)
- "new_team" : Cardano エコシステム内の新興 / 個別開発チーム。
               例: DeFi の DEX チーム、独立 dApp 開発、オープンソース貢献団体
                   (Harmonic Labs / DeltaDeFi / Andamio / Aiken team 等)。
               規模感: Cardano コミュニティ発で、上記 5 大組織よりも小さい。
- "individual": 個人開発者 / フリーランス
- "other"    : Cardano エコシステム外の **既存の大企業** (例: Tweag, Fireblocks,
               Chainlink 等)、または上記 6 区分に明確に当てはまらない既存団体。
               **Cardano 発の新興チームには使わない (それは new_team)**。
- []         : 組織受益が無い (InfoAction、ParameterChange 等)
- 複数該当する場合は ["IO", "CF"] のように複数指定。

## protocol_change
- "hard_fork"   : HardForkInitiation
- "param_change": ParameterChange
- "n_a"         : それ以外

## marketing_purpose
- "yes" : PR / イベント / カンファレンス / 認知拡大 / スポンサーシップが主目的
- "no"  : 開発・運営・研究等の主目的、マーケは副次的または無し

## kpi_clarity
- "clear"  : 明確な KPI、マイルストーン、成果検証手順が記述されている
- "unclear": KPI が抽象的、達成基準不明、報告義務不明
- "n_a"    : 性質上 KPI が適用されない (InfoAction、ParameterChange、HardFork)

## risk_level
- "high" : 実験的 / 未検証技術 / 単一エンティティへの大型出資 / 不確実性大
- "low"  : 既存技術 / 実績ある運営 / 分散実行 / 既存契約継続
- "n_a"  : 評価困難 (InfoAction 等)

# 重要な原則
- 提案の中身 (title + abstract) から判定する。author 情報には依存しない。
- 表面的なキーワードマッチではなく、提案の意図を理解する。
  例: "risk" という単語が文中にあっても、リスクへの対処を述べているなら risk_level=low の可能性あり。
- 不確かな場合は "n_a" / "unclear" を使うことを恐れない。
- 全フィールド必須。reasoning も全項目必須。
"""


def fetch_ga(proposal_id: str) -> dict | None:
    with get_db() as (cur, _):
        cur.execute(
            """
            SELECT proposal_id, proposal_type,
                   COALESCE(title_ja, title, '')     AS title,
                   COALESCE(abstract_ja, abstract, '') AS abstract
              FROM governance_actions
             WHERE proposal_id = %s
            """,
            (proposal_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def classify(ga: dict) -> dict:
    payload = {
        "proposal_id":   ga["proposal_id"],
        "proposal_type": ga["proposal_type"],
        "title":         ga["title"][:200],
        "abstract":      ga["abstract"][:3000],
    }
    user_text = json.dumps(payload, ensure_ascii=False)
    client = _get_client()
    resp = _send_with_retry(
        client,
        model=DEFAULT_MODEL,
        system_text=_SYSTEM,
        user_text=user_text,
        max_tokens=1500,
    )
    raw = resp.choices[0].message.content or ""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        return {"_error": f"JSON parse failed: {e}", "_raw": raw}


def print_result(ga: dict, tags: dict) -> None:
    print("=" * 78)
    print(f"proposal_id: {ga['proposal_id']}")
    print(f"type:        {ga['proposal_type']}")
    print(f"title:       {ga['title'][:120]}")
    print()
    if "_error" in tags:
        print(f"  [ERROR] {tags['_error']}")
        print(f"  raw: {tags.get('_raw', '')[:500]}")
        return
    print(f"  summary_ja:        {tags.get('summary_ja', '')}")
    print()
    fields = [
        "treasury_size", "priority", "org_recipient", "protocol_change",
        "marketing_purpose", "kpi_clarity", "risk_level",
    ]
    reasoning = tags.get("reasoning", {})
    for f in fields:
        v = tags.get(f, "?")
        r = reasoning.get(f, "")
        v_str = json.dumps(v, ensure_ascii=False) if isinstance(v, list) else str(v)
        print(f"  {f:18s}: {v_str:25s}  ← {r}")
    print()


def main() -> None:
    for pid in PROPOSAL_IDS:
        ga = fetch_ga(pid)
        if not ga:
            print(f"!! Not found in DB: {pid}\n")
            continue
        try:
            tags = classify(ga)
        except Exception as e:  # noqa: BLE001
            print(f"!! Classify failed: {pid}: {e}\n")
            continue
        print_result(ga, tags)


if __name__ == "__main__":
    main()
