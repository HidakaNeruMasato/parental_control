#!/usr/bin/env python3
"""
Ubuntu Agent メイン監視デーモン (pc_agentd)
ユーザー追跡、最前面アプリ識別、離席（アイドル）計測、UsageSession の定期集計と記録を行います。
"""
import sys
import os
import time
import argparse
import logging
from datetime import datetime, timezone

# 自作モジュールのインポート対応
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.user_tracker import UserTracker
from modules.app_tracker import AppTracker
from modules.idle_tracker import IdleTracker
from modules.logger import UsageLogger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("pc_agentd")

class ParentalControlAgent:
    def __init__(self, device_id: str = "ubuntu-default-pc", log_dir: str = "/var/log/parental_control", poll_interval: float = 2.0):
        self.device_id = device_id
        self.poll_interval = poll_interval
        self.user_tracker = UserTracker()
        self.app_tracker = AppTracker()
        self.idle_tracker = IdleTracker()
        self.logger_inst = UsageLogger(log_dir=log_dir)

        # セッション保持変数
        self.current_user = None
        self.current_app_key = None
        self.current_app_info = None
        self.session_start_time = None
        self.accumulated_idle_sec = 0.0

    def run_once(self) -> dict | None:
        """1ステップ分のモニタリングを実行して状態を返します（テスト・デバッグ用）"""
        active_user = self.user_tracker.get_active_user() or "offline"
        app_info = self.app_tracker.get_active_app_info()
        running_apps = self.app_tracker.get_running_gui_apps(target_user=active_user if active_user != "offline" else None)
        idle_sec = self.idle_tracker.get_idle_seconds()

        running_keys = [a["app_key"] for a in running_apps]
        logger.info(f"[監視中] ユーザー: {active_user} | 最前面アプリ: {app_info['app_key']} ({app_info['window_title']}) | 起動中GUIアプリ: {running_keys} | 無操作: {idle_sec:.1f}s")
        return {
            "user": active_user,
            "app": app_info,
            "running_apps": running_apps,
            "idle_sec": idle_sec
        }

    def start_loop(self, flush_interval_sec: int = 60):
        """監視ループを開始します（アプリ切り替え時および一定時間ごとにセッションログを書き出し）"""
        logger.info(f"Ubuntu Parental Control Agent 開始 (DeviceID: {self.device_id}, Poll: {self.poll_interval}s)")

        last_flush_time = time.time()
        self.session_start_time = datetime.now(timezone.utc)

        try:
            while True:
                now_utc = datetime.now(timezone.utc)
                active_user = self.user_tracker.get_active_user() or "nobody"
                app_info = self.app_tracker.get_active_app_info()
                running_apps = self.app_tracker.get_running_gui_apps(target_user=active_user if active_user != "nobody" else None)
                idle_sec = self.idle_tracker.get_idle_seconds()

                # アイドル検知 (無操作判定閾値 5秒以上の場合累積)
                if idle_sec >= 5.0:
                    self.accumulated_idle_sec += self.poll_interval

                # 初回またはユーザー/アプリ切替の検出
                app_changed = (self.current_app_key != app_info["app_key"])
                user_changed = (self.current_user != active_user)
                time_flushed = (time.time() - last_flush_time >= flush_interval_sec)

                if self.current_user and (app_changed or user_changed or time_flushed):
                    duration = int((now_utc - self.session_start_time).total_seconds())
                    if duration > 0 and self.current_user != "nobody":
                        self.logger_inst.record_session(
                            child_user=self.current_user,
                            device_id=self.device_id,
                            app_info=self.current_app_info,
                            start_time=self.session_start_time,
                            end_time=now_utc,
                            duration_seconds=duration,
                            idle_seconds=int(self.accumulated_idle_sec),
                            running_gui_apps=running_apps
                        )

                    # リセット
                    self.session_start_time = now_utc
                    self.accumulated_idle_sec = 0.0
                    last_flush_time = time.time()

                self.current_user = active_user
                self.current_app_key = app_info["app_key"]
                self.current_app_info = app_info

                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            logger.info("Agent 停止リクエストを受信しました。終了します。")


def main():
    parser = argparse.ArgumentParser(description="Ubuntu Parental Control Agent Daemon")
    parser.add_argument("--once", action="store_true", help="1回だけ状態を取得して表示")
    parser.add_argument("--device-id", default="ubuntu-pc-01", help="デバイス識別ID")
    parser.add_argument("--log-dir", default="./logs", help="セッションログ出力先ディレクトリ")
    parser.add_argument("--interval", type=float, default=2.0, help="監視ポーリング間隔 (秒)")
    args = parser.parse_args()

    agent = ParentalControlAgent(
        device_id=args.device_id,
        log_dir=args.log_dir,
        poll_interval=args.interval
    )

    if args.once:
        result = agent.run_once()
        print("\n--- 監視結果サマリー ---")
        print(f"アクティブユーザー: {result['user']}")
        print(f"最前面アプリKey  : {result['app']['app_key']}")
        print(f"アプリ表示名     : {result['app']['app_name_raw']}")
        print(f"ウィンドウタイトル: {result['app']['window_title']}")
        print(f"起動中GUIアプリ  : {[a['app_key'] for a in result['running_apps']]}")
        print(f"無操作アイドル時間: {result['idle_sec']:.2f} 秒")
    else:
        agent.start_loop()

if __name__ == "__main__":
    main()
