"""DRep マッチング診断 (v2)

7 axis (treasury / priority / org / protocol / transparency / risk / marketing)
の価値観モデルに基づく DRep マッチング診断のバックエンド。

DRep プロファイルは AI (OpenAI) が投票履歴 + rationale を直接読んで生成し、
ユーザー回答との axis 距離でマッチ度を算出する。

公開 API は drep_compass.api を参照。
パッケージ内モジュール:
  - taxonomy:     7 axis の定義
  - questionnaire: 9 問の Likert 質問定義 + ベクトル化
  - config:       version / 閾値などの定数
  - profile:      AI を呼んで drep_profiles に保存する処理
  - match:        ユーザーベクトルと DRep プロファイルの距離計算
  - api:          ページ層が呼ぶ薄い public API
"""
