"""
最前面アクティブアプリケーションおよび起動中GUIアプリケーションの統合識別モジュール
Wayland (GNOME Shell / Procfs) および X11 (xdotool / xprop / _NET_ACTIVE_WINDOW) に対応。
"""
import subprocess
import shutil
import logging
import os
import re

logger = logging.getLogger(__name__)

# バックグラウンドシステムプロセスやシステム常駐を除外するためのキーワード
EXCLUDE_COMM = {
    "systemd", "gnome-shell", "wayland", "pipewire", "dbus-daemon", "pulseaudio",
    "xorg", "gdm", "networkmanager", "snapd", "bash", "zsh", "sh", "python3", "pc_agentd.py"
}

class AppTracker:
    def __init__(self):
        self.xdotool_path = shutil.which("xdotool")
        self.xprop_path = shutil.which("xprop")
        self.gdbus_path = shutil.which("gdbus")

    def get_active_app_info(self) -> dict:
        """
        現在最前面でフォーカスされているアプリケーションの情報を取得します。
        """
        # 1. X11 / XWayland (xprop _NET_ACTIVE_WINDOW / xdotool)
        info = self._get_info_via_xprop_active_window()
        if info and info.get("app_key") and info.get("app_key") != "unknown":
            return info

        if self.xdotool_path:
            info = self._get_info_via_xdotool()
            if info and info.get("app_key") and info.get("app_key") != "unknown":
                return info

        # 2. GNOME Shell DBus API (Wayland)
        if self.gdbus_path:
            info = self._get_info_via_gnome_shell()
            if info and info.get("app_key") and info.get("app_key") != "unknown":
                return info

        # 3. Procfs 動的フォールバック (最直近のユーザーアクティブプロセス)
        info = self._get_info_via_procfs_dynamic()
        if info:
            return info

        return {
            "app_key": "unknown",
            "app_name_raw": "Unknown Application",
            "window_title": "",
            "pid": None
        }

    def get_running_gui_apps(self, target_user: str | None = None) -> list[dict]:
        """
        現在ターゲットユーザー（指定がなければ全ユーザー）が起動している GUI アプリケーションの一覧を取得します。
        バックグラウンドで起動しているゲームやブラウザ等を網羅します。
        """
        running_apps = []
        seen_keys = set()

        try:
            # ps コマンドで DISPLAY または WAYLAND_DISPLAY を所有するユーザープロセスを取得
            res = subprocess.run(
                ["ps", "-u", target_user if target_user else "", "-o", "pid,user,comm,args"],
                capture_output=True,
                text=True,
                timeout=3
            ) if target_user else subprocess.run(
                ["ps", "-e", "-o", "pid,user,comm,args"],
                capture_output=True,
                text=True,
                timeout=3
            )

            if res.returncode == 0:
                for line in res.stdout.splitlines()[1:]:
                    parts = line.strip().split(None, 3)
                    if len(parts) < 3:
                        continue
                    pid_str, user, comm = parts[0], parts[1], parts[2]
                    args = parts[3] if len(parts) > 3 else comm

                    comm_clean = comm.lower()
                    if comm_clean in EXCLUDE_COMM or pid_str == str(os.getpid()):
                        continue

                    # DISPLAY環境変数またはGUIアプリケーションの特徴を持つプロセスかを判定
                    if self._is_gui_process(pid_str, comm_clean, args):
                        app_key = comm_clean
                        if app_key not in seen_keys:
                            seen_keys.add(app_key)
                            running_apps.append({
                                "app_key": app_key,
                                "app_name_raw": comm_clean.capitalize(),
                                "pid": int(pid_str),
                                "user": user
                            })
        except Exception as e:
            logger.debug(f"実行中GUIアプリ一覧取得失敗: {e}")

        return running_apps

    def _get_info_via_xprop_active_window(self) -> dict | None:
        """xprop -root _NET_ACTIVE_WINDOW から最前面ウィンドウ情報を正確に取得"""
        if not self.xprop_path:
            return None
        try:
            res = subprocess.run([self.xprop_path, "-root", "_NET_ACTIVE_WINDOW"], capture_output=True, text=True, timeout=2)
            if res.returncode != 0 or "=" not in res.stdout:
                return None
            
            match = re.search(r"window id # (0x[0-9a-fA-F]+)", res.stdout)
            if not match or match.group(1) == "0x0":
                return None
            win_id = match.group(1)

            # ウィンドウの詳細情報 (WM_CLASS, WM_NAME) を取得
            res_detail = subprocess.run([self.xprop_path, "-id", win_id, "WM_CLASS", "WM_NAME"], capture_output=True, text=True, timeout=2)
            if res_detail.returncode != 0:
                return None

            app_key = "unknown"
            window_title = ""

            for line in res_detail.stdout.splitlines():
                if "WM_CLASS" in line and "=" in line:
                    classes = re.findall(r'"([^"]+)"', line)
                    if classes:
                        app_key = classes[-1].lower()
                elif "WM_NAME" in line and "=" in line:
                    match_title = re.search(r'=\s*"(.*)"', line)
                    if match_title:
                        window_title = match_title.group(1)

            # PID の取得
            pid_res = subprocess.run([self.xprop_path, "-id", win_id, "_NET_WM_PID"], capture_output=True, text=True, timeout=2)
            pid = None
            if pid_res.returncode == 0 and "=" in pid_res.stdout:
                match_pid = re.search(r"=\s*(\d+)", pid_res.stdout)
                if match_pid:
                    pid = int(match_pid.group(1))

            if app_key != "unknown":
                return {
                    "app_key": app_key,
                    "app_name_raw": app_key.capitalize(),
                    "window_title": window_title,
                    "pid": pid
                }
        except Exception as e:
            logger.debug(f"xprop _NET_ACTIVE_WINDOW 取得失敗: {e}")
        return None

    def _get_info_via_xdotool(self) -> dict | None:
        try:
            res = subprocess.run([self.xdotool_path, "getwindowfocus"], capture_output=True, text=True, timeout=2)
            if res.returncode != 0 or not res.stdout.strip():
                return None
            win_id = res.stdout.strip()

            res_name = subprocess.run([self.xdotool_path, "getwindowname", win_id], capture_output=True, text=True, timeout=2)
            window_title = res_name.stdout.strip() if res_name.returncode == 0 else ""

            res_pid = subprocess.run([self.xdotool_path, "getwindowpid", win_id], capture_output=True, text=True, timeout=2)
            pid = int(res_pid.stdout.strip()) if res_pid.returncode == 0 and res_pid.stdout.strip().isdigit() else None

            app_key = "unknown"
            if self.xprop_path:
                res_class = subprocess.run([self.xprop_path, "-id", win_id, "WM_CLASS"], capture_output=True, text=True, timeout=2)
                if res_class.returncode == 0 and "=" in res_class.stdout:
                    classes = re.findall(r'"([^"]+)"', res_class.stdout)
                    if classes:
                        app_key = classes[-1].lower()

            if app_key == "unknown" and pid:
                app_key = self._get_process_name(pid) or "unknown"

            if app_key != "unknown":
                return {
                    "app_key": app_key,
                    "app_name_raw": app_key.capitalize(),
                    "window_title": window_title,
                    "pid": pid
                }
        except Exception as e:
            logger.debug(f"xdotool 取得失敗: {e}")
        return None

    def _get_info_via_gnome_shell(self) -> dict | None:
        try:
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

    def _get_info_via_procfs_dynamic(self) -> dict | None:
        """Procfs から現在のアクティブな GUI アプリケーションを直近アクセス時刻順に探査"""
        try:
            candidates = []
            for pid_str in os.listdir("/proc"):
                if not pid_str.isdigit():
                    continue
                comm_path = os.path.join("/proc", pid_str, "comm")
                if os.path.exists(comm_path):
                    with open(comm_path, "r", encoding="utf-8", errors="ignore") as f:
                        comm = f.read().strip().lower()
                    
                    if comm in EXCLUDE_COMM:
                        continue

                    # プロセスの環境変数や GUI 属性をチェック
                    if self._is_gui_process(pid_str, comm, ""):
                        # 最終ステート変化時刻を計測
                        stat_path = os.path.join("/proc", pid_str, "stat")
                        mtime = os.path.getmtime(stat_path) if os.path.exists(stat_path) else 0
                        candidates.append((mtime, comm, int(pid_str)))

            if candidates:
                # 最新の活動があったプロセスを採用
                candidates.sort(key=lambda x: x[0], reverse=True)
                top_comm = candidates[0][1]
                top_pid = candidates[0][2]
                return {
                    "app_key": top_comm,
                    "app_name_raw": top_comm.capitalize(),
                    "window_title": "",
                    "pid": top_pid
                }
        except Exception as e:
            logger.debug(f"procfs dynamic 取得失敗: {e}")
        return None

    def _is_gui_process(self, pid_str: str, comm: str, args: str) -> bool:
        """該当プロセスが GUI アプリケーションであるかを判定"""
        # よくある GUI アプリケーションの特徴パターン
        known_gui = [
            "firefox", "chrome", "chromium", "steam", "code", "vlc", "gimp",
            "godot", "discord", "spotify", "gedit", "nautilus", "gnome-terminal",
            "obs", "blender", "libreoffice", "thunderbird", "lutris", "heroic"
        ]
        if any(k in comm or k in args.lower() for k in known_gui):
            return True

        # 環境変数の DISPLAY や WAYLAND_DISPLAY のチェック
        environ_path = os.path.join("/proc", pid_str, "environ")
        if os.path.exists(environ_path):
            try:
                with open(environ_path, "rb") as f:
                    env_bytes = f.read()
                    if b"DISPLAY=" in env_bytes or b"WAYLAND_DISPLAY=" in env_bytes:
                        return True
            except Exception:
                pass
        return False

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
    running = tracker.get_running_gui_apps()
    print("アクティブアプリ情報:", info)
    print("起動中GUIアプリ一覧:", running)
