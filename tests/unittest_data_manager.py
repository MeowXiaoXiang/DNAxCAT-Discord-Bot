import unittest
import os
import json
from unittest.mock import patch, mock_open
from loguru import logger

# 設定模組路徑
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from module.forum_notifier.data_manager import ensure_data_file, load_data, save_data, update_data


class TestDataManager(unittest.TestCase):
    def setUp(self):
        """在每個測試前執行，設定測試用檔案路徑"""
        self.test_file = "tests/data/test_data.json"
        self.test_data = {
            "板塊A": {
                "12345": "2024-11-14 10:00:00"
            }
        }
        if not os.path.exists("tests/data"):
            os.makedirs("tests/data")

    def tearDown(self):
        """在每個測試後執行，清理測試用檔案"""
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_ensure_data_file_creates_file(self):
        """測試：檔案不存在時自動創建"""
        ensure_data_file(self.test_file)
        self.assertTrue(os.path.exists(self.test_file), "應該創建缺失的檔案")
        with open(self.test_file, "r", encoding="utf-8") as f:
            content = json.load(f)
        self.assertEqual(content, {}, "新創建的檔案應該是空的 JSON")

    def test_load_data_creates_missing_file(self):
        """測試：加載缺失檔案時，自動創建"""
        data = load_data(self.test_file)
        self.assertTrue(os.path.exists(self.test_file), "應該自動創建缺失的檔案")
        self.assertEqual(data, {}, "新創建的檔案應該是空的 JSON")

    def test_load_data_reads_existing_file(self):
        """測試：加載現有檔案"""
        with open(self.test_file, "w", encoding="utf-8") as f:
            json.dump(self.test_data, f, ensure_ascii=False, indent=4)
        data = load_data(self.test_file)
        self.assertEqual(data, self.test_data, "加載的資料應該與檔案內容一致")

    def test_save_data_writes_to_file(self):
        """測試：儲存資料到檔案"""
        save_data(self.test_file, self.test_data)
        self.assertTrue(os.path.exists(self.test_file), "應該創建並儲存檔案")
        with open(self.test_file, "r", encoding="utf-8") as f:
            content = json.load(f)
        self.assertEqual(content, self.test_data, "檔案內容應該與儲存的資料一致")

    def test_update_data(self):
        """測試：更新資料邏輯"""
        existing_data = {
            "板塊A": {
                "12345": "2024-11-14 10:00:00"
            }
        }
        new_threads = [
            {"article_id": "12346", "post_time": "2024-11-15 11:00:00"},
            {"article_id": "12345", "post_time": "2024-11-14 10:00:00"},
        ]
        updated, updated_data = update_data(existing_data, new_threads, "板塊A")

        # 驗證更新邏輯
        self.assertEqual(len(updated), 1, "應該只有一篇新文章")
        self.assertEqual(updated[0]["article_id"], "12346", "新增的文章 ID 應該是 12346")
        self.assertIn("12346", updated_data["板塊A"], "應該新增文章到板塊資料中")
        self.assertEqual(updated_data["板塊A"]["12346"], "2024-11-15 11:00:00", "文章時間應該正確更新")


if __name__ == "__main__":
    unittest.main()
