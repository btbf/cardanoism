# deploy/ — VPS 用デプロイ資材

新規 VPS で Cardanoism のバックエンドを動かすための **cron + systemd** テンプレート。
`notify_worker.py` (cron)、`ogmios_listener.py` (systemd 常駐)、`ga_ai_worker.py` (systemd 常駐) の 3 系統をすべてカバーする。

| ファイル | 配置先 |
|---------|-------|
| `cron.d-cardanoism-notify` | `/etc/cron.d/cardanoism-notify` (権限 `0644 root:root`) |
| `cardanoism-infisical` | `/usr/local/bin/cardanoism-infisical` (権限 `0755 root:root`) |
| `infisical-agent.yaml` | `/etc/cardanoism/infisical-agent.yaml` (権限 `0644 root:root`) |
| `infisical-agent.service` | `/etc/systemd/system/infisical-agent.service` (権限 `0644 root:root`) |
| `infisical.env.example` | `/etc/cardanoism/infisical.env` のひな形 |

> 詳細仕様は [`docs/realtime-notification-backend.md`](../docs/realtime-notification-backend.md) (Ogmios listener) と [`docs/ga-ai-analysis-backend.md`](../docs/ga-ai-analysis-backend.md) (GA AI worker) を参照。

---

## 初回セットアップ手順

1. **実行ユーザーを確認** (cron / systemd / tmux 共通)

    ```bash
    id btism
    ```

    本テンプレートは既存の `btism` ユーザーで実行する。別ユーザーを使う場合はcronのユーザー欄、
    systemdの `User=`、各ファイルのgroupをすべて同じユーザーへ変更する。

2. **リポジトリ配置 + Python依存関係**

    ```bash
    sudo git clone https://github.com/btbf/cardanoism.git /home/btism/cardanoism_tmp
    sudo chown -R btism:btism /home/btism/cardanoism_tmp
    sudo -u btism /home/btism/.pyenv/shims/python -m pip install \
        -r /home/btism/cardanoism_tmp/requirements.txt
    ```

3. **Infisical Agent** (cron / systemd / tmux 共通)

    Infisical で Universal Auth の Machine Identity を作成し、対象projectへの読み取り権限を付与する。
    Client ID と Client Secret はそれぞれ別ファイルへ保存し、root以外には読ませない:

    ```bash
    sudo install -d -m 0750 -o root -g btism /etc/cardanoism
    sudo touch /etc/cardanoism/infisical-client-id
    sudo touch /etc/cardanoism/infisical-client-secret
    sudo chown root:root /etc/cardanoism/infisical-client-id /etc/cardanoism/infisical-client-secret
    sudo chmod 0600 /etc/cardanoism/infisical-client-id /etc/cardanoism/infisical-client-secret
    sudo $EDITOR /etc/cardanoism/infisical-client-id
    sudo $EDITOR /etc/cardanoism/infisical-client-secret
    ```

    各ファイルにはClient IDまたはClient Secretの値だけを1行で記入する。tokenそのものは保存しない。

    ラッパーが読む非機密設定を配置する:

    ```bash
    sudo install -m 0640 -o root -g btism \
        /home/btism/cardanoism_tmp/deploy/infisical.env.example \
        /etc/cardanoism/infisical.env
    sudo $EDITOR /etc/cardanoism/infisical.env
    ```

    Agent設定・unit・共通ラッパーを配置して起動する:

    ```bash
    sudo install -m 0644 -o root -g root \
        /home/btism/cardanoism_tmp/deploy/infisical-agent.yaml \
        /etc/cardanoism/infisical-agent.yaml
    sudo install -m 0644 -o root -g root \
        /home/btism/cardanoism_tmp/deploy/infisical-agent.service \
        /etc/systemd/system/infisical-agent.service
    sudo install -m 0755 -o root -g root \
        /home/btism/cardanoism_tmp/deploy/cardanoism-infisical \
        /usr/local/bin/cardanoism-infisical

    sudo systemctl daemon-reload
    sudo systemctl enable --now infisical-agent
    sudo systemctl status infisical-agent --no-pager -l
    sudo -u btism /usr/local/bin/cardanoism-infisical env | grep DB_HOST
    ```

    Agentは短期アクセストークンを `/run/cardanoism/infisical-token` に書き出し、
    期限前に自動更新する。`btism`は短期tokenだけを読み、Client Secretにはアクセスできない。
    Universal AuthのClient Secret自体には設定したTTL・使用回数制限が残るため、
    Machine Identity側の設定が常駐運用に適していることを確認する。

4. **ログディレクトリ**

    ```bash
    sudo mkdir -p /home/btism/cardanoism_log
    sudo chown btism:btism /home/btism/cardanoism_log
    ```

5. **cron 定義をコピーして編集**

    ```bash
    sudo install -m 0644 -o root -g root \
        /home/btism/cardanoism_tmp/deploy/cron.d-cardanoism-notify \
        /etc/cron.d/cardanoism-notify
    sudo $EDITOR /etc/cron.d/cardanoism-notify
    ```

    ファイル冒頭の **デプロイ時に書き換える 3 行** を編集:

    | 変数 | 内容 |
    |------|------|
    | `INFISICAL_RUN` | 共通ラッパーのフルパス |
    | `WORKDIR` | リポジトリの配置先 (デフォルト `/home/btism/cardanoism_tmp`) |
    | `PY` | 使用する Python のフルパス |

6. **cron daemon に反映**

    ```bash
    sudo systemctl reload cron       # Debian/Ubuntu
    # sudo systemctl reload crond    # RHEL/Rocky
    ```

7. **疎通確認**

    ```bash
    # 1 イベントだけ手動で叩く (cron を待たない)
    sudo -u btism bash -c 'cd /home/btism/cardanoism_tmp && \
        /usr/local/bin/cardanoism-infisical \
        /home/btism/.pyenv/shims/python notify_worker.py --event fiat_sync'
    ```

8. **初回データ投入** (cron が回るまで待たず DB を満たす)

    新規 VPS では DB が空なので、cron 開始前に各 sync を 1 回ずつ手動で流す。順序に依存があるので **以下の順** で実行する。Koios コール量が多い ((6) 投票履歴は数分〜十数分) ので、画面が固まらないよう `tmux` / `screen` を使うのを推奨。

    ```bash
    sudo -u btism bash <<'EOF'
    set -euo pipefail
    cd /home/btism/cardanoism_tmp
    INF=/usr/local/bin/cardanoism-infisical
    PY=/home/btism/.pyenv/shims/python

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

9. **systemd 常駐ワーカー起動** (Ogmios listener + GA AI worker)

    cron だけでは不十分。**Ogmios listener** がリアルタイム通知を、**GA AI worker** が `ga_ai_initial_sync` で enqueue した GA を順次処理する。両方とも systemd で常駐させる。

    手順 3 で共通ラッパーと Infisical の認証・接続設定を配置済みである前提。

    **Ogmios listener** `/etc/systemd/system/ogmios-listener.service`:

    ```ini
    [Unit]
    Description=Cardanoism Ogmios Chain Listener
    After=network.target ogmios.service infisical-agent.service
    Wants=infisical-agent.service
    Requires=ogmios.service

    [Service]
    Type=simple
    User=btism
    WorkingDirectory=/home/btism/cardanoism_tmp
    ExecStart=/usr/local/bin/cardanoism-infisical /home/btism/.pyenv/shims/python ogmios_listener.py
    Restart=always
    RestartSec=10
    StandardOutput=journal
    StandardError=journal

    [Install]
    WantedBy=multi-user.target
    ```

    **GA AI worker** `/etc/systemd/system/ga-ai-worker.service`:

    ```ini
    [Unit]
    Description=Cardanoism GA AI Worker
    After=network.target mysql.service infisical-agent.service
    Wants=infisical-agent.service

    [Service]
    Type=simple
    User=btism
    WorkingDirectory=/home/btism/cardanoism_tmp
    ExecStart=/usr/local/bin/cardanoism-infisical /home/btism/.pyenv/shims/python ga_ai_worker.py
    Restart=always
    RestartSec=10
    StandardOutput=journal
    StandardError=journal

    [Install]
    WantedBy=multi-user.target
    ```

    **起動と疎通確認**:

    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable --now ogmios-listener ga-ai-worker

    # 状態確認
    sudo systemctl status infisical-agent ogmios-listener ga-ai-worker

    # リアルタイムログ
    sudo journalctl -u ga-ai-worker -f
    sudo journalctl -u ogmios-listener -f
    sudo journalctl -u infisical-agent -f
    ```

    **Reflex (tmux)**:

    ```bash
    sudo -u btism tmux new-session -d -s cardanoism \
        'cd /home/btism/cardanoism_tmp && exec /usr/local/bin/cardanoism-infisical reflex run'
    ```

    tmux内でも直接 `infisical run` は呼ばず、cron / systemd と同じラッパーを使う。

    > preview ネットワーク用には `INFISICAL_ENV=preview` を設定した別の環境ファイルを用意し、
    > unit に `Environment=CARDANOISM_INFISICAL_ENV_FILE=/etc/cardanoism/infisical-preview.env` を追加して、
    > 別 unit (`ogmios-listener-preview.service` / `ga-ai-worker-preview.service`) として登録する。

10. **動作確認 — AI 分析キューが流れているか**

    `ga_ai_initial_sync` で enqueue した GA が `analyzed` 状態に進んでいるか確認：

    ```bash
    mysql -u $DB_USER -p$DB_PASS $DB_NAME -e "
    SELECT status, COUNT(*) cnt
    FROM governance_ai_analysis
    GROUP BY status"
    ```

    `pending` がじわじわ減って `analyzed` が増えれば worker が動いている。`pending` だけ大量に残ってたら worker が落ちているか、未起動。

---

## cron スケジュール一覧

詳細は [`docs/koios-polling-backend.md § 4`](../docs/koios-polling-backend.md)。

### 常時 cron

| 頻度 | event | 内容 |
|------|-------|------|
| 5 分 | `drep` | status_change + **drep_unvoted_ga** (DRep 本人の未投票 GA リマインダー)。drep_unvoted_ga は DB only |
| 5 分 | `fiat_sync` | CoinGecko レート |
| 10 分 | `pool` | saturation / pledge / reward。APYは`pools.apy_history_7ep`を参照し、Koiosへ再取得しない |
| 15 分 | `governance.py --retry-metadata --limit 20` | Ogmios後のIPFSメタデータ取得失敗分だけ再試行（Koios不使用） |
| 15 分 | `drep_dirty_sync` | listenerがdirty markしたactive DRepの委任量だけ差分更新 |
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

cron 系（ファイル出力）:

```bash
sudo tail -F /var/log/cardanoism/notify-pool.log
sudo tail -F /var/log/cardanoism/notify-drep.log

# 全イベント横断で異常を grep
sudo grep -RHn -i 'error\|exception\|traceback' /var/log/cardanoism/
```

systemd 系（journal）:

```bash
sudo journalctl -u ga-ai-worker -f       # GA AI worker
sudo journalctl -u ogmios-listener -f    # Ogmios listener

# 過去 24h でエラーだけ
sudo journalctl -u ga-ai-worker --since "24 hours ago" -p err
```

### 一時停止 / 再開

cron:

```bash
sudo mv /etc/cron.d/cardanoism-notify /etc/cron.d/cardanoism-notify.disabled
# 再開:
sudo mv /etc/cron.d/cardanoism-notify.disabled /etc/cron.d/cardanoism-notify
sudo systemctl reload cron
```

systemd 常駐ワーカー:

```bash
# 停止
sudo systemctl stop ga-ai-worker ogmios-listener

# 再開
sudo systemctl start ga-ai-worker ogmios-listener

# コード更新後の再起動
sudo systemctl restart ga-ai-worker ogmios-listener
```

### Infisical Agent の認証更新

短期アクセストークンはAgentが自動更新するため、手作業は不要。
Universal AuthのClient Secret自体をローテーションするときだけ、root専用ファイルを更新してAgentを再起動する:

```bash
sudo $EDITOR /etc/cardanoism/infisical-client-secret
sudo systemctl restart infisical-agent
sudo systemctl status infisical-agent --no-pager -l
```

Infisical上のアプリケーションsecretを変更した場合、cronは次回実行から反映される。
systemdワーカーとtmuxのReflexは起動時にsecretを注入するため、それぞれ再起動して反映する。
