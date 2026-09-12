"""
UsageSession セッションログ保存・ローカル管理モジュール
JSONL 形式でローカルディスクに保存し、重複防止用の event_id を自動生成します。
"""
import json
import os
import uuid
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

class UsageLogger:
    def __init__(self, log_dir: str = "/var/log/parental_control"):
        self.log_dir = log_dir
        self._ensure_log_dir()
        self.current_log_file = os.path.join(self.log_dir, f"usage_{datetime.now().strftime('%Y%m%d')}.jsonl")

    def _ensure_log_dir(self):
        """ログディレクトリが存在しない場合は作成（権限がない場合はローカルフォールバック）"""
        try:
            os.makedirs(self.log_dir, exist_ok=True)
        except PermissionError:
            fallback_dir = os.path.expanduser("~/.cache/parental_control/logs")
            logger.warning(f"ログディレクトリ {self.log_dir} への作成権限がないため、{fallback_dir} にフォールバックします。")
            self.log_dir = fallback_dir
            os.makedirs(self.log_dir, exist_ok=True)

    def record_session(self, child_user: str, device_id: str, app_info: dict, start_time: datetime, end_time: datetime, duration_seconds: int, idle_seconds: int = 0) -> dict:
        """
        UsageSession レコードを作成し、JSONL ファイルに保存します。
        """
        event_id = str(uuid.uuid4())
        record = {
            "event_id": event_id,
            "child_user": child_user,
            "device_id": device_id,
            "app_key": app_info.get("app_key", "unknown"),
            "app_name_raw": app_info.get("app_name_raw", "Unknown Application"),
            "window_title": app_info.get("window_title", ""),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": max(0, duration_seconds),
            "idle_seconds": max(0, idle_seconds),
            "active_seconds": max(0, duration_seconds - idle_seconds),
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        log_file = os.path.join(self.log_dir, f"usage_{datetime.now().strftime('%Y%m%d')}.jsonl")
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            logger.info(f"セッション記録保存: User={child_user}, App={record['app_key']}, Active={record['active_seconds']}s (EventID={event_id})")
        except Exception as e:
            logger.error(f"セッション書き込みエラー: {e}")

        return record


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger_inst = UsageLogger(log_dir="./test_logs")
    now = datetime.now(timezone.utc)
    logger_inst.record_session(
        child_user="child1",
        device_id="ubuntu-test-pc",
        app_info={"app_key": "firefox", "app_name_raw": "Firefox", "window_title": "YouTube"},
        start_time=now,
        end_time=now,
        duration_seconds=60,
        idle_seconds=5
    )
