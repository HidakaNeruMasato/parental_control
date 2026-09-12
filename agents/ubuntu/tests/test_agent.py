"""
Phase 1 Agent モジュールの単体テスト
"""
import unittest
import os
import shutil
import json
from datetime import datetime, timezone
import sys

# テスト対象ディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.user_tracker import UserTracker
from modules.app_tracker import AppTracker
from modules.idle_tracker import IdleTracker
from modules.logger import UsageLogger

class TestAgentModules(unittest.TestCase):
    def setUp(self):
        self.test_log_dir = os.path.join(os.path.dirname(__file__), "tmp_test_logs")
        if os.path.exists(self.test_log_dir):
            shutil.rmtree(self.test_log_dir)

    def tearDown(self):
        if os.path.exists(self.test_log_dir):
            shutil.rmtree(self.test_log_dir)

    def test_user_tracker(self):
        tracker = UserTracker()
        active_user = tracker.get_active_user()
        # クラッシュせず型が正しく返ることを確認
        self.assertTrue(active_user is None or isinstance(active_user, str))

    def test_app_tracker(self):
        tracker = AppTracker()
        info = tracker.get_active_app_info()
        self.assertIn("app_key", info)
        self.assertIn("app_name_raw", info)
        self.assertIn("window_title", info)

    def test_idle_tracker(self):
        tracker = IdleTracker()
        idle_sec = tracker.get_idle_seconds()
        self.assertIsInstance(idle_sec, float)
        self.assertGreaterEqual(idle_sec, 0.0)

    def test_usage_logger(self):
        logger_inst = UsageLogger(log_dir=self.test_log_dir)
        now = datetime.now(timezone.utc)
        record = logger_inst.record_session(
            child_user="child1",
            device_id="test-pc",
            app_info={"app_key": "firefox", "app_name_raw": "Firefox", "window_title": "Test Title"},
            start_time=now,
            end_time=now,
            duration_seconds=60,
            idle_seconds=5
        )

        self.assertEqual(record["child_user"], "child1")
        self.assertEqual(record["active_seconds"], 55)
        self.assertIsNotNone(record["event_id"])

        # 生成された JSONL ファイルの検証
        files = os.listdir(self.test_log_dir)
        self.assertEqual(len(files), 1)
        
        filepath = os.path.join(self.test_log_dir, files[0])
        with open(filepath, "r", encoding="utf-8") as f:
            line = f.readline()
            data = json.loads(line)
            self.assertEqual(data["event_id"], record["event_id"])
            self.assertEqual(data["app_key"], "firefox")


if __name__ == "__main__":
    unittest.main()
