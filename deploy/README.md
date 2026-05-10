# deploy/ — VPS 用デプロイ資材

新規 VPS で Cardanoism の **Koios ポーリング系 (notify_worker.py)** を cron で定期実行するためのテンプレート。
`cron.d-cardanoism-notify` を編集して `/etc/cron.d/` に置けば動く形。

| ファイル | 配置先 |
|---------|-------|
| `cron.d-cardanoism-notify` | `/etc/cron.d/cardanoism-notify` (権限 `0644 root:root`) |

> Ogmios listener (リアルタイム通知) と GA AI worker (常駐) は **systemd 管理**。それぞれ [`docs/realtime-notification-backend.md`](../docs/realtime-notification-backend.md) と [`docs/ga-ai-analysis-backend.md`](../docs/ga-ai-analysis-backend.md) を参照。

---

## 初回セットアップ手順

1. **専用システムユーザを作成** (cron / systemd の実行ユーザ)

    ```bash
    sudo useradd -r -m -s /bin/bash cardanoism
    sudo passwd -l cardanoism                  # ログイン無効化 (任意、推奨)
    ```

2. **リポジトリ配置 + venv**

    ```bash
    sudo git clone https://github.com/btbf/cardanoism.git /opt/cardanoism
    sudo chown -R cardanoism:cardanoism /opt/cardanoism
    sudo -u cardanoism python3 -m venv /opt/cardanoism/.venv
    sudo -u cardanoism /opt/cardanoism/.venv/bin/pip install -r /opt/cardanoism/requirements.txt
    ```

3. **Infisical 認証** (cron 実行ユーザーで 1 回だけ)

    ```bash
    sudo -u cardanoism infisical login
    # ブラウザ or デバイス認証フローを完了 → ~/.infisical/ に credentials が保存される
    sudo -u cardanoism infisical run --env=mainnet -- env | grep DB_HOST   # 動作確認
    ```

4. **ログディレクトリ**

    ```bash
    sudo mkdir -p /var/log/cardanoism
    sudo chown cardanoism:cardanoism /var/log/cardanoism
    ```

5. **cron 定義をコピーして編集**

    ```bash
    sudo install -m 0644 -o root -g root \
        /opt/cardanoism/deploy/cron.d-cardanoism-notify \
        /etc/cron.d/cardanoism-notify
    sudo $EDITOR /etc/cron.d/cardanoism-notify
    ```

    ファイル冒頭の **デプロイ時に書き換える 3 行** を編集:

    | 変数 | 内容 |
    |------|------|
    | `ENV` | `mainnet` / `preview` |
    | `WORKDIR` | リポジトリの配置先 (デフォルト `/opt/cardanoism`) |
    | `PY` | venv の Python フルパス |

6. **cron daemon に反映**

    ```bash
    sudo systemctl reload cron       # Debian/Ubuntu
    # sudo systemctl reload crond    # RHEL/Rocky
    ```

7. **疎通確認**

    ```bash
    # 1 イベントだけ手動で叩く (cron を待たない)
    sudo -u cardanoism bash -c 'cd /opt/cardanoism && \
        infisical run --env=mainnet -- \
        /opt/cardanoism/.venv/bin/python notify_worker.py --event fiat_sync'
    ```

8. **初回データ投入** (cron が回るまで待たず DB を満たす)

    新規 VPS では DB が空なので、cron 開始前に各 sync を 1 回ずつ手動で流す。順序に依存があるので **以下の順** で実行する。Koios コール量が多い ((6) 投票履歴は数分〜十数分) ので、画面が固まらないよう `tmux` / `screen` を使うのを推奨。

    ```bash
    sudo -u cardanoism bash <<'EOF'
    set -euo pipefail
    cd /opt/cardanoism
    INF="infisical run --env=mainnet --"
    PY=/opt/cardanoism/.venv/bin/python

    # (1) プロトコルパラメータ + CC メンバー (他の sync の前提)
    $INF $PY notify_worker.py --event params_sync

    # (2) GA 本体 (CIP-100/108 メタデータ含む)
    $INF $PY cardanoism/backend/governance.py

    # (3) 法定通貨レート (CoinGecko)
    $INF $PY notify_worker.py --event fiat_sync

    # (4) トレジャリー残高 + 履歴 + NCL
    $INF $PY notify_worker.py --event treasury_sync

    # (5) DRep 一覧
    $INF $PY notify_worker.py --event drep_sync

    # (6) 投票履歴 + 集計
    $INF $PY notify_worker.py --event vote_sync
    $INF $PY notify_worker.py --event summary_sync

    # (7) SPO 一覧 + ブロック履歴
    $INF $PY notify_worker.py --event pool_sync
    $INF $PY notify_worker.py --event pool_block_history_sync

    # (8) stake_addresses.spo_pool_id を一斉判定 (新環境のみ)
    $INF $PY notify_worker.py --event spo_role_initial_sync

    # (9) 投票理由メタ + OpenAI 翻訳 (--translate-limit でコスト抑制可)
    $INF $PY notify_worker.py --event vote_rationale_sync --fetch-limit 100 --translate-limit 30

    # (10) 憲法本文 + 翻訳
    $INF $PY notify_worker.py --event constitution_sync

    # (11) 既存 GA を AI 分析キューへ bulk enqueue (空 DB のとき必要)
    $INF $PY notify_worker.py --event ga_ai_initial_sync
    EOF
    ```

    | # | event | 備考 |
    |---|-------|------|
    | 1 | `params_sync` | (2) 以降の前提 (NCL 計算等) |
    | 2 | `governance.py` | GA 本体投入 + AI 分析 enqueue を兼ねる |
    | 3 | `fiat_sync` | 軽量、UI で常時必要 |
    | 4 | `treasury_sync` | 直近 6 epoch を /totals で取得 |
    | 5 | `drep_sync` | DRep 一覧 + メタデータ |
    | 6 | `vote_sync` → `summary_sync` | DRep / SPO / CC 投票 |
    | 7 | `pool_sync` → `pool_block_history_sync` | SPO 一覧 + 直近 5 ep のブロック履歴 |
    | 8 | `spo_role_initial_sync` | **新環境専用**: stake_addresses の SPO 判定を一括計算 |
    | 9 | `vote_rationale_sync` | OpenAI 翻訳 (コスト次第で `--translate-limit` を絞る) |
    | 10 | `constitution_sync` | IPFS から憲法本文取得 + 翻訳 |
    | 11 | `ga_ai_initial_sync` | Active / Ratified / Enacted な GA を AI 分析キューへ |

    > 並列実行は **しない**。Koios の rate limit に引っかかりやすく、また (1) → (2) のように依存もあるため。

---

## cron スケジュール一覧

詳細は [`docs/koios-polling-backend.md § 4`](../docs/koios-polling-backend.md)。

### 常時 cron

| 頻度 | event | 内容 |
|------|-------|------|
| 5 分 | `drep` | status_change + **drep_unvoted_ga** (DRep 本人の未投票 GA リマインダー)。drep_unvoted_ga は DB only |
| 5 分 | `fiat_sync` | CoinGecko レート |
| 10 分 | `pool` | saturation / pledge / reward |
| 15 分 | `summary_sync` | **Active GA 限定**で投票集計 (drep_yes_pct 等) を最新化。`pre_ratify` トリガーの前提 |
| 15 分 | `reminder` | 委任長期リマインダー + stake_addresses 委任先リフレッシュ |
| 15 分 | `treasury` | 引き出し提案の enacted 検知 |
| 6 時間 | `relay_check` | プール relay TCP 疎通 |
| 4 時間 | `vote_rationale_sync` | OpenAI 翻訳 |

### フォールバック cron (24h、深夜 03:00–07:00)

`governance` (`governance.py --no-translate`) → `params_sync` → `treasury_sync` → `drep_sync` → `pool_sync` → `pool_block_history_sync` → `vote_sync` → `constitution_sync`

通常は Ogmios listener が `epoch_start` を検知して各 `*_sync` を発火するため、listener 動作中はほぼ no-op (= 既に最新)。
`summary_sync` は常時 15 min cron で回しているのでフォールバックには含めない。

---

## 運用 Tips

### ログを見る

```bash
sudo tail -F /var/log/cardanoism/notify-pool.log
sudo tail -F /var/log/cardanoism/notify-drep.log

# 全イベント横断で異常を grep
sudo grep -RHn -i 'error\|exception\|traceback' /var/log/cardanoism/
```

### 一時停止 / 再開

```bash
sudo mv /etc/cron.d/cardanoism-notify /etc/cron.d/cardanoism-notify.disabled
# 再開:
sudo mv /etc/cron.d/cardanoism-notify.disabled /etc/cron.d/cardanoism-notify
sudo systemctl reload cron
```

### Infisical 再認証

`~/.infisical/` の credentials が期限切れになったら:

```bash
sudo -u cardanoism infisical login
```

cron file の編集は不要 (token をファイルに置いていないため)。
