import aiofiles
import os
import json
from loguru import logger

async def ensure_data_file(file_path):
    """檢查並確保資料檔案存在"""
    if not os.path.exists(file_path):
        logger.warning(f"資料檔 {file_path} 不存在，正在創建...")
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write("{}")
            logger.debug(f"已創建空的資料檔案：{file_path}")
        except Exception as e:
            logger.error(f"創建資料檔 {file_path} 時發生錯誤：{e}")

async def load_data(file_path):
    """讀取 JSON 文件"""
    await ensure_data_file(file_path)  # 確保檔案存在
    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
            data = json.loads(content)
            logger.debug(f"成功加載資料檔：{file_path}")
            return data
    except Exception as e:
        logger.error(f"讀取資料檔 {file_path} 時發生錯誤：{e}")
        return {}

async def save_data(file_path, data):
    """寫入 JSON 文件"""
    try:
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=4))
            logger.debug(f"成功儲存資料到檔案：{file_path}")
    except Exception as e:
        logger.error(f"儲存資料檔 {file_path} 時發生錯誤：{e}")

def update_data(existing_data, new_threads, board_id):
    """
    比對並更新數據，處理新增和移除的文章
    new_threads 應包含 `stickthread` 和 `normalthread` 鍵，每個鍵的值為 ID 列表。
    """
    logger.debug(f"開始比對與更新板塊 {board_id} 的文章數據")

    # 確保板塊存在
    if board_id not in existing_data:
        existing_data[board_id] = {"stickthread": [], "normalthread": []}
        logger.debug(f"初始化板塊 {board_id} 的數據結構")

    # 初始化結果數據
    updated = {"stickthread": [], "normalthread": []}
    removed = {"stickthread": [], "normalthread": []}

    # 比對置頂文章
    current_stickthread = set(existing_data[board_id]["stickthread"])
    new_stickthread = set(new_threads.get("stickthread", []))

    # 找到新增和移除的置頂文章
    added_stickthread = new_stickthread - current_stickthread
    removed_stickthread = current_stickthread - new_stickthread

    # 更新結果數據和本地存儲
    updated["stickthread"].extend(added_stickthread)
    removed["stickthread"].extend(removed_stickthread)
    existing_data[board_id]["stickthread"] = list(new_stickthread)

    # 比對非置頂文章
    current_normalthread = set(existing_data[board_id]["normalthread"])
    new_normalthread = set(new_threads.get("normalthread", []))

    # 找到新增和移除的非置頂文章
    added_normalthread = new_normalthread - current_normalthread
    removed_normalthread = current_normalthread - new_normalthread

    # 更新結果數據和本地存儲
    updated["normalthread"].extend(added_normalthread)
    removed["normalthread"].extend(removed_normalthread)
    existing_data[board_id]["normalthread"] = list(new_normalthread)

    # 日誌輸出
    if not added_stickthread and not removed_stickthread and not added_normalthread and not removed_normalthread:
        logger.info(f"板塊 {board_id} 無任何變化")
    else:
        log_message = [f"\n板塊 {board_id} 更新完成："]
        if added_stickthread:
            log_message.append(f"新增置頂文章 {len(added_stickthread)} 篇：{', '.join(added_stickthread)}")
        if removed_stickthread:
            log_message.append(f"移除置頂文章 {len(removed_stickthread)} 篇：{', '.join(removed_stickthread)}")
        if added_normalthread:
            log_message.append(f"新增非置頂文章 {len(added_normalthread)} 篇：{', '.join(added_normalthread)}")
        if removed_normalthread:
            log_message.append(f"移除非置頂文章 {len(removed_normalthread)} 篇：{', '.join(removed_normalthread)}")
        logger.info("\n".join(log_message))

    return updated, existing_data
