"""
Linux 無操作（アイドル）時間測定モジュール
Wayland (GNOME Mutter DBus) および X11 (xprintidle) に対応します。
"""
import subprocess
import shutil
import logging
import re

logger = logging.getLogger(__name__)

class IdleTracker:
    def __init__(self):
        self.xprintidle_path = shutil.which("xprintidle")
        self.gdbus_path = shutil.which("gdbus")
        self.dbus_send_path = shutil.which("dbus-send")

    def get_idle_seconds(self) -> float:
        """
        現在の無操作（アイドル）時間を秒単位で返します。
        取得できない場合は 0.0 を返します。
        """
        # 1. GNOME Wayland / Mutter DBus 経由での取得
        idle_ms = self._get_gnome_mutter_idle_ms()
        if idle_ms is not None:
            return idle_ms / 1000.0

        # 2. X11 (xprintidle) 経由での取得
        if self.xprintidle_path:
            try:
                res = subprocess.run([self.xprintidle_path], capture_output=True, text=True, timeout=2)
                if res.returncode == 0 and res.stdout.strip().isdigit():
                    return float(res.stdout.strip()) / 1000.0
            except Exception as e:
                logger.debug(f"xprintidle 取得失敗: {e}")

        # 3. 取得不可の場合
        return 0.0

    def _get_gnome_mutter_idle_ms(self) -> float | None:
        """GNOME Mutter IdleMonitor DBus API を呼出してミリ秒単位で取得"""
        # dbus-send 試行
        if self.dbus_send_path:
            try:
                cmd = [
                    self.dbus_send_path,
                    "--session",
                    "--print-reply",
                    "--dest=org.gnome.Mutter.IdleMonitor",
                    "/org/gnome/Mutter/IdleMonitor/Core",
                    "org.gnome.Mutter.IdleMonitor.GetIdletime"
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                if res.returncode == 0:
                    # レスポンス例: uint64 15420
                    match = re.search(r"uint64\s+(\d+)", res.stdout)
                    if match:
                        return float(match.group(1))
            except Exception as e:
                logger.debug(f"dbus-send (Mutter.IdleMonitor) 失敗: {e}")

        # gdbus 試行
        if self.gdbus_path:
            try:
                cmd = [
                    self.gdbus_path,
                    "call",
                    "--session",
                    "--dest", "org.gnome.Mutter.IdleMonitor",
                    "--object-path", "/org/gnome/Mutter/IdleMonitor/Core",
                    "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime"
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                if res.returncode == 0:
                    # レスポンス例: (uint64 15420,)
                    match = re.search(r"(\d+)", res.stdout)
                    if match:
                        return float(match.group(1))
            except Exception as e:
                logger.debug(f"gdbus (Mutter.IdleMonitor) 失敗: {e}")

        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tracker = IdleTracker()
    idle_sec = tracker.get_idle_seconds()
    print(f"現在の無操作（アイドル）時間: {idle_sec:.2f} 秒")
