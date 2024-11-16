import json
import os
from loguru import logger

def ensure_data_file(file_path):
    """檢查並確保資料檔案存在"""
    if not os.path.exists(file_path):
        logger.warning(f"資料檔 {file_path} 不存在，正在創建...")
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=4)
            logger.info(f"已創建空的資料檔案：{file_path}")
        except Exception as e:
            logger.error(f"創建資料檔 {file_path} 時發生錯誤：{e}")

def load_data(file_path):
    """讀取 JSON 文件"""
    ensure_data_file(file_path)  # 確保檔案存在
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info(f"成功加載資料檔：{file_path}")
            return data
    except Exception as e:
        logger.error(f"讀取資料檔 {file_path} 時發生錯誤：{e}")
        return {}

def save_data(file_path, data):
    """寫入 JSON 文件"""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            logger.info(f"成功儲存資料到檔案：{file_path}")
    except Exception as e:
        logger.error(f"儲存資料檔 {file_path} 時發生錯誤：{e}")

def update_data(existing_data, new_threads, board_id):
    """比對並更新數據"""
    logger.debug(f"開始比對與更新板塊 {board_id} 的文章數據")
    updated = []
    if board_id not in existing_data:
        existing_data[board_id] = {}

    for thread in new_threads:
        article_id = thread["article_id"]
        if article_id not in existing_data[board_id]:
            logger.info(f"新文章發現 (ID: {article_id})")
            updated.append(thread)
        existing_data[board_id][article_id] = thread["post_time"]

    logger.info(f"板塊 {board_id} 更新完成，共新增 {len(updated)} 篇新文章")
    return updated, existing_data
