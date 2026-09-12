"""
Linux ログインユーザー追跡モジュール
現在アクティブなグラフィカルセッションのユーザーを識別します。
"""
import subprocess
import shutil
import json
import logging
import os

logger = logging.getLogger(__name__)

class UserTracker:
    def __init__(self):
        self.loginctl_path = shutil.which("loginctl")

    def get_active_user(self) -> str | None:
        """
        現在アクティブなGUIセッションのユーザー名を取得します。
        """
        # 1. loginctl を試行 (systemd 採用ディストリビューション向け)
        if self.loginctl_path:
            try:
                # JSON形式がサポートされているか試す (Ubuntu 22.04+, 26.04)
                res = subprocess.run(
                    [self.loginctl_path, "list-sessions", "--json=short"],
                    capture_output=True,
                    text=True,
                    timeout=3
                )
                if res.returncode == 0 and res.stdout.strip():
                    sessions = json.loads(res.stdout)
                    for s in sessions:
                        session_id = str(s.get("session", ""))
                        if not session_id:
                            continue
                        # セッションの詳細情報を確認
                        show_res = subprocess.run(
                            [self.loginctl_path, "show-session", session_id, "-p", "Type", "-p", "Active", "-p", "Name", "-p", "State"],
                            capture_output=True,
                            text=True,
                            timeout=3
                        )
                        if show_res.returncode == 0:
                            props = {}
                            for line in show_res.stdout.splitlines():
                                if "=" in line:
                                    k, v = line.split("=", 1)
                                    props[k] = v
                            
                            # グラフィカルセッション (wayland/x11) かつ Active == yes
                            session_type = props.get("Type", "")
                            is_active = props.get("Active", "") == "yes" or props.get("State", "") == "active"
                            username = props.get("Name", "")
                            
                            if session_type in ["wayland", "x11"] and is_active and username:
                                return username
            except Exception as e:
                logger.debug(f"loginctl 経由のユーザー取得エラー: {e}")

        # 2. フォールバック: who または w コマンドから :0 または tty 経由のグラフィカルセッションを取得
        try:
            res = subprocess.run(["who"], capture_output=True, text=True, timeout=3)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        user = parts[0]
                        line_info = parts[1]
                        # :0 などの X/Wayland ディスプレイ
                        if ":0" in line or "tty" in line_info:
                            return user
        except Exception as e:
            logger.debug(f"who コマンド経由のユーザー取得エラー: {e}")

        # 3. 最終フォールバック: 環境変数 SUDO_USER または LOGNAME / USER
        return os.environ.get("SUDO_USER") or os.environ.get("USER") or os.environ.get("LOGNAME")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tracker = UserTracker()
    active_user = tracker.get_active_user()
    print(f"現在のアクティブユーザー: {active_user}")
