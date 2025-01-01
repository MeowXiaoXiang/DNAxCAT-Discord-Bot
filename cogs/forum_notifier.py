import discord
from discord.ext import commands, tasks
import json
import os
from module.forum_notifier.scraper import Scraper
from module.forum_notifier.data_manager import load_data, save_data, update_data
from loguru import logger

class ForumNotifier(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.settings = None  # 儲存設定的主變數
        self.data_file = "data/forum_notifier.json"  # 資料儲存位置

        # 嘗試載入設定
        try:
            self.load_settings("config/settings.json")
        except Exception as e:
            logger.error(f"載入設定失敗：{e}")
            raise

        # 動態設置循環間隔並啟動循環任務
        self.check_new_threads.change_interval(minutes=self.settings["interval_minutes"])
        self.check_new_threads.start()

    def cog_unload(self):
        """停止循環任務"""
        self.check_new_threads.cancel()

    def load_settings(self, file_path):
        """載入設定，並檢查參數有效性"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"設定檔案 {file_path} 不存在")

        with open(file_path, "r", encoding="utf-8") as f:
            settings = json.load(f)

        # 確保主結構存在
        if "forum_notifier" not in settings:
            raise KeyError("設定中缺少 'forum_notifier' 鍵")

        notifier_settings = settings["forum_notifier"]

        # 檢查必要參數是否存在
        required_keys = ["channel_id", "interval_minutes", "base_url", "forums"]
        for key in required_keys:
            if key not in notifier_settings:
                raise KeyError(f"設定中缺少必要參數：{key}")

        # 確保 forums 結構正確
        if not isinstance(notifier_settings["forums"], dict):
            raise ValueError("forums 必須是字典")

        for forum_name, forum_config in notifier_settings["forums"].items():
            if "url" not in forum_config or "color" not in forum_config:
                raise KeyError(f"forums 中的 '{forum_name}' 缺少必要鍵 'url' 或 'color'")
            if not isinstance(forum_config["color"], str) or not forum_config["color"].startswith("#"):
                raise ValueError(f"forums 中的 '{forum_name}' 的 'color' 必須是 HEX 顏色字串")

        # 保存設定到類屬性
        self.settings = notifier_settings
        logger.info(f"成功載入設定：{notifier_settings}")

    @tasks.loop(minutes=10)  # 使用預設值，動態設置間隔
    async def check_new_threads(self):
        """定期檢查新文章的任務"""
        logger.info("開始檢查新文章")

        # 加載現有的資料
        existing_data = await load_data(self.data_file)

        # 如果首次啟動，僅初始化資料，不發推播
        if not existing_data:
            logger.info("首次啟動，僅初始化資料，不發推播")
            async with Scraper(self.settings["base_url"], self.settings) as scraper:
                latest_threads = await scraper.FetchThreadIDs(self.settings)
                # 初始化資料
                for forum_id, threads in latest_threads.items():
                    combined_threads = {
                        "stickthread": threads.get("stickthread", []),
                        "normalthread": threads.get("normalthread", []),
                    }
                    _, existing_data = update_data(existing_data, combined_threads, forum_id)
                await save_data(self.data_file, existing_data)
            return

        # 非首次啟動，正常推播
        async with Scraper(self.settings["base_url"], self.settings) as scraper:
            latest_threads = await scraper.FetchThreadIDs(self.settings)
            logger.debug(f"最新文章ID列表：{latest_threads}")

        for forum_id, threads in latest_threads.items():
            logger.debug(f"正在處理板塊 {forum_id}，獲取的文章數據：{threads}")
            combined_threads = {
                "stickthread": threads.get("stickthread", []),
                "normalthread": threads.get("normalthread", []),
            }
            updated_threads, existing_data = update_data(existing_data, combined_threads, forum_id)

            # 推播置頂文章
            for thread in updated_threads["stickthread"]:
                await self.send_notification(forum_id, thread, top_status=True)

            # 推播普通文章
            for thread in updated_threads["normalthread"]:
                await self.send_notification(forum_id, thread, top_status=False)

        await save_data(self.data_file, existing_data)
        logger.info("檢查新文章完成")

    async def send_notification(self, forum_id, thread_id, top_status=False):
        """發送推播通知"""
        logger.info(f"發送推播通知，板塊ID：{forum_id}，文章ID：{thread_id}，置頂狀態：{top_status}")

        # 獲取文章詳細資訊
        async with Scraper(self.settings["base_url"], self.settings) as scraper:
            thread_detail = await scraper.FetchThreadDetail(forum_id, thread_id, top_status=top_status)

        if not thread_detail:
            logger.error(f"無法獲取文章詳細資訊，板塊ID：{forum_id}，文章ID：{thread_id}")
            return

        # 提取板塊資訊
        forum_config = self.settings["forums"].get(thread_detail["forum"]["name"], {})
        forum_color = forum_config.get("color", "#000000")

        embed_color = discord.Color(int(forum_color.replace("#", ""), 16))

        # 建立 Embed
        embed = discord.Embed(
            title=f"{thread_detail['forum']['name']}",
            url=thread_detail['forum']['url'],
            color=embed_color,
        )

        embed.set_author(
            name=thread_detail["author"]["name"],
            url=thread_detail["author"]["url"],
            icon_url=thread_detail["author"]["avatar"],
        )

        description_lines = []
        # 組合置頂和分類在同一行
        status_and_category = ""
        if top_status:
            status_and_category += "[置頂]"
        if thread_detail["category"]["name"]:
            if status_and_category:  # 如果已經有 [置頂]，添加空格
                status_and_category += " "
            status_and_category += f"[[{thread_detail['category']['name']}]]({thread_detail['category']['url']})"
        if status_and_category:
            description_lines.append(status_and_category)

        # 添加標題行
        description_lines.append(
            f"[{thread_detail['title']}]({thread_detail['url']})"
        )
        embed.description = "\n".join(description_lines)
        embed.set_footer(text=f"發佈於: {thread_detail['post_time']}")

        channel = self.bot.get_channel(self.settings["channel_id"])
        if channel:
            await channel.send(embed=embed)
        else:
            logger.error(f"無法找到頻道ID：{self.settings['channel_id']}")

async def setup(bot):
    await bot.add_cog(ForumNotifier(bot))
