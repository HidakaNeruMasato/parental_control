# Phase 1 実機テスト手順書 (Ubuntu Agent 利用状況取得の検証)

本手順書は、Ubuntu 26.04 LTS ノートPC上で Ubuntu Agent プロトタイプを実行し、**ユーザー識別・最前面アプリ判定・無操作アイドル計測・セッションログ出力**が正しく機能することを実機テストするためのガイドです。

---

## 1. 事前準備

### 1-1. テスト用 Linux ユーザーの確認 / 作成
実機上の管理者アカウントにて、テスト用子どもユーザーが未作成の場合は以下のように作成します。

```bash
# 子ども用 Linux アカウント作成 (例: child1, child2)
sudo adduser child1
sudo adduser child2

# 注意: sudo 権限 (wheel/sudo グループ) は付与しません。
```

---

## 2. Agent モジュールの動作確認 (ワンショット表示)

まずは管理者アカウントまたは一般ユーザーアカウント上で、1回だけ状態を取得する `--once` オプションを実行して表示内容を確認します。

```bash
cd /path/to/parental_control/agents/ubuntu
python3 pc_agentd.py --once
```

### 期待される出力例:
```text
INFO:pc_agentd:[監視中] ユーザー: child1 | アプリ: firefox (YouTube - Mozilla Firefox) | 無操作: 0.0s

--- 監視結果サマリー ---
アクティブユーザー: child1
最前面アプリKey  : firefox
アプリ表示名     : Firefox
ウィンドウタイトル: YouTube - Mozilla Firefox
無操作アイドル時間: 0.00 秒
```

---

## 3. 実機シナリオテスト手順

### シナリオ A: フォーカスアプリ切り替えテスト
1. デスクトップ上で **Firefox** を起動してアクティブにします。
2. ターミナルで `./pc_agentd.py --log-dir ./test_logs` をバックグラウンドまたは別ウィンドウで開始します。
3. Firefox で特定のページを閲覧します。
4. **VS Code** や **テキストエディタ** に切り替えて 10秒間操作します。
5. Agent ログ (`./test_logs/usage_YYYYMMDD.jsonl`) を確認します。

**確認用コマンド**:
```bash
cat ./test_logs/usage_*.jsonl | jq .
```
`app_key` が `firefox` から `code` や `gedit` に変化し、それぞれの開始・終了タイムスタンプが記録されていることを確認します。

---

### シナリオ B: 無操作 (離席アイドル) テスト
1. PC を **5分間操作せず**（マウス・キーボードに触れず）そのまま放置します。
2. 5分経過後、再び操作を再開します。
3. ログファイル内の `idle_seconds` の値が 300秒程度（約5分）として記録され、純粋な操作時間 `active_seconds` から除外されていることを確認します。

---

### シナリオ C: Linux ユーザー切り替えテスト
1. `child1` ユーザーでログインし、数分アプリを操作します。
2. セッションを維持したまま `child2` にユーザー切り替え（Switched User）を行います。
3. `child2` でログインしてアプリを操作します。
4. Agent のログで、`child_user` が `child1` から `child2` へ誤りなく記録が分離されていることを確認します。

---

## 4. 問題発生時のログ確認と確認結果の報告

もし動作しない場合、以下のログを出力して報告してください。

```bash
python3 pc_agentd.py --once --log-dir ./test_logs
```
