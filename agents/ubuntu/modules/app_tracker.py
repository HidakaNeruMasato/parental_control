"""
最前面アクティブアプリケーション・ウィンドウ識別モジュール
Wayland (GNOME Shell / Procfs) および X11 (xdotool / xprop) に対応します。
"""
import subprocess
import shutil
import logging
import os
import re

logger = logging.getLogger(__name__)

class AppTracker:
    def __init__(self):
        self.xdotool_path = shutil.which("xdotool")
        self.xprop_path = shutil.which("xprop")
        self.gdbus_path = shutil.which("gdbus")

    def get_active_app_info(self) -> dict:
        """
        現在最前面でフォーカスされているアプリケーションの情報を取得します。
        戻り値の辞書フォーマット:
        {
            "app_key": "firefox",        # プロセス名またはクラス名
            "app_name_raw": "Firefox",   # 表示用プロセス名
            "window_title": "Google - Mozilla Firefox", # ウィンドウタイトル
            "pid": 12345
        }
        """
        # 1. X11 / XWayland (xdotool & xprop) による取得を試行
        if self.xdotool_path and self.xprop_path:
            info = self._get_info_via_xdotool()
            if info and info.get("app_key"):
                return info

        # 2. GNOME Shell DBus API (Wayland環境) による取得を試行
        if self.gdbus_path:
            info = self._get_info_via_gnome_shell()
            if info and info.get("app_key"):
                return info

        # 3. Procfs フォールバック (最も直近に動作した主要GUIプロセスを推定)
        info = self._get_info_via_procfs()
        if info:
            return info

        return {
            "app_key": "unknown",
            "app_name_raw": "Unknown Application",
            "window_title": "",
            "pid": None
        }

    def _get_info_via_xdotool(self) -> dict | None:
        try:
            # アクティブウィンドウID取得
            res = subprocess.run([self.xdotool_path, "getactivewindow"], capture_output=True, text=True, timeout=2)
            if res.returncode != 0 or not res.stdout.strip():
                return None
            win_id = res.stdout.strip()

            # PID 取得
            res_pid = subprocess.run([self.xdotool_path, "getwindowpid", win_id], capture_output=True, text=True, timeout=2)
            pid = int(res_pid.stdout.strip()) if res_pid.returncode == 0 and res_pid.stdout.strip().isdigit() else None

            # ウィンドウ名 取得
            res_name = subprocess.run([self.xdotool_path, "getwindowname", win_id], capture_output=True, text=True, timeout=2)
            window_title = res_name.stdout.strip() if res_name.returncode == 0 else ""

            # WM_CLASS 取得
            res_class = subprocess.run([self.xprop_path, "-id", win_id, "WM_CLASS"], capture_output=True, text=True, timeout=2)
            app_key = "unknown"
            if res_class.returncode == 0 and "=" in res_class.stdout:
                classes = re.findall(r'"([^"]+)"', res_class.stdout)
                if classes:
                    app_key = classes[-1].lower()

            if pid and app_key == "unknown":
                app_key = self._get_process_name(pid) or "unknown"

            return {
                "app_key": app_key,
                "app_name_raw": app_key.capitalize(),
                "window_title": window_title,
                "pid": pid
            }
        except Exception as e:
            logger.debug(f"xdotool/xprop 取得失敗: {e}")
            return None

    def _get_info_via_gnome_shell(self) -> dict | None:
        try:
            # GNOME Shell Eval (Securityポリシーによって制限される場合あり)
            cmd = [
                self.gdbus_path, "call", "--session",
                "--dest", "org.gnome.Shell",
                "--object-path", "/org/gnome/Shell",
                "--method", "org.gnome.Shell.Eval",
                "global.get_window_actors().find(a => a.meta_window.has_focus())?.meta_window.get_wm_class()"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and "true" in res.stdout:
                match = re.search(r'"([^"]+)"', res.stdout)
                if match:
                    app_key = match.group(1).lower()
                    return {
                        "app_key": app_key,
                        "app_name_raw": app_key.capitalize(),
                        "window_title": "",
                        "pid": None
                    }
        except Exception as e:
            logger.debug(f"GNOME Shell Eval 取得失敗: {e}")
        return None

    def _get_info_via_procfs(self) -> dict | None:
        """Procfs から現在実行中の代表的な GUI アプリケーションを特定"""
        gui_apps = ["firefox", "chrome", "steam", "code", "vlc", "gimp", "godot", "discord"]
        try:
            for pid_str in os.listdir("/proc"):
                if not pid_str.isdigit():
                    continue
                comm_path = os.path.join("/proc", pid_str, "comm")
                if os.path.exists(comm_path):
                    with open(comm_path, "r", encoding="utf-8", errors="ignore") as f:
                        comm = f.read().strip().lower()
                        for app in gui_apps:
                            if app in comm:
                                return {
                                    "app_key": comm,
                                    "app_name_raw": comm.capitalize(),
                                    "window_title": "",
                                    "pid": int(pid_str)
                                }
        except Exception as e:
            logger.debug(f"procfs 取得失敗: {e}")
        return None

    def _get_process_name(self, pid: int) -> str | None:
        comm_path = f"/proc/{pid}/comm"
        if os.path.exists(comm_path):
            try:
                with open(comm_path, "r", encoding="utf-8") as f:
                    return f.read().strip().lower()
            except Exception:
                pass
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tracker = AppTracker()
    info = tracker.get_active_app_info()
    print("アクティブアプリ情報:", info)
