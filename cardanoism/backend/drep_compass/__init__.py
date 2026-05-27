"""DRep マッチング診断 (v4)

8 axis (large_treasury / incumbent_org / new_team / technical / adoption /
marketing / protocol_change / rationale_disclosure) の outcome-first モデル。

各 axis は「DRep の観察可能な振る舞い」と 1:1 対応する。
DRep プロファイルは GA pre-classification (governance_ai_analysis.axis_tags_json)
を集計して算出 (rationale_disclosure のみ DRep プロパティ直接参照)。

ユーザーは 8 問の Likert (強く反対〜強く賛成) に回答し、axis 距離でマッチ度を算出。

公開 API は drep_compass.api を参照。
パッケージ内モジュール:
  - taxonomy:     8 axis の定義
  - questionnaire: 8 問の Likert 質問定義 (q_id = axis 1:1)
  - config:       version / 閾値などの定数
  - profile:      GA タグを集計して drep_profiles に保存する処理
  - match:        ユーザーベクトルと DRep プロファイルの距離計算
  - api:          ページ層が呼ぶ薄い public API
"""
