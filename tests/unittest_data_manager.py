import unittest
import os
import json
import aiofiles
from unittest.mock import patch
from loguru import logger

# 設定模組路徑
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from module.forum_notifier.data_manager import ensure_data_file, load_data, save_data, update_data


class TestDataManager(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        """在每個測試前執行，設定測試用檔案路徑"""
        self.test_file = "tests/data/test_data.json"
        self.test_data = {
            "板塊A": {
                "stickthread": ["12345"],
                "normalthread": ["54321"]
            }
        }
        if not os.path.exists("tests/data"):
            os.makedirs("tests/data")

    async def asyncTearDown(self):
        """在每個測試後執行，清理測試用檔案"""
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    async def test_ensure_data_file_creates_file(self):
        """測試：檔案不存在時自動創建"""
        await ensure_data_file(self.test_file)
        self.assertTrue(os.path.exists(self.test_file), "應該創建缺失的檔案")
        async with aiofiles.open(self.test_file, "r", encoding="utf-8") as f:
            content = json.loads(await f.read())
        self.assertEqual(content, {}, "新創建的檔案應該是空的 JSON")

    async def test_load_data_creates_missing_file(self):
        """測試：加載缺失檔案時，自動創建"""
        data = await load_data(self.test_file)
        self.assertTrue(os.path.exists(self.test_file), "應該自動創建缺失的檔案")
        self.assertEqual(data, {}, "新創建的檔案應該是空的 JSON")

    async def test_load_data_reads_existing_file(self):
        """測試：加載現有檔案"""
        async with aiofiles.open(self.test_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(self.test_data, ensure_ascii=False, indent=4))
        data = await load_data(self.test_file)
        self.assertEqual(data, self.test_data, "加載的資料應該與檔案內容一致")

    async def test_save_data_writes_to_file(self):
        """測試：儲存資料到檔案"""
        await save_data(self.test_file, self.test_data)
        self.assertTrue(os.path.exists(self.test_file), "應該創建並儲存檔案")
        async with aiofiles.open(self.test_file, "r", encoding="utf-8") as f:
            content = json.loads(await f.read())
        self.assertEqual(content, self.test_data, "檔案內容應該與儲存的資料一致")

    def test_update_data(self):
        """測試：更新資料邏輯"""
        existing_data = {
            "板塊A": {
                "stickthread": ["12345"],
                "normalthread": ["54321"]
            }
        }
        new_threads = {
            "stickthread": ["12345", "67890"],
            "normalthread": ["54321", "09876"]
        }
        updated, updated_data = update_data(existing_data, new_threads, "板塊A")

        # 驗證更新邏輯
        self.assertEqual(len(updated["stickthread"]), 1, "應該只有一篇新的置頂文章")
        self.assertEqual(updated["stickthread"][0], "67890", "新增的置頂文章 ID 應該是 67890")
        self.assertEqual(len(updated["normalthread"]), 1, "應該只有一篇新的非置頂文章")
        self.assertEqual(updated["normalthread"][0], "09876", "新增的非置頂文章 ID 應該是 09876")

        self.assertIn("67890", updated_data["板塊A"]["stickthread"], "應該新增置頂文章到板塊資料中")
        self.assertIn("09876", updated_data["板塊A"]["normalthread"], "應該新增非置頂文章到板塊資料中")


if __name__ == "__main__":
    unittest.main()
