#--------------------------Discord---------------------------------
import discord
from discord.ext import commands, tasks
#--------------------------Module----------------------------------
from module.ffmpeg.ffmpeg_manager import check_and_download_ffmpeg
from module.music_player import (
    MusicPlayerController,
    MusicPlaylistManager,
    YTDLPDownloader,
    MusicEmbedManager,
    MusicPlayerButtons,
    PaginationButtons
)
#--------------------------Other-----------------------------------
import asyncio
from loguru import logger
import time
import shutil
import subprocess
import os
#------------------------------------------------------------------

class MusicPlayerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ffmpeg_path = None
        self.player_controller = None
        self.yt_dlp_manager = None
        self.playlist_manager = MusicPlaylistManager()
        self.embed_manager = MusicEmbedManager()
        self.buttons_view = MusicPlayerButtons(self.button_action_handler)
        self.player_message = None
        self.playlist_message = None
        self.last_yt_dlp_check = None # 上次檢查 yt-dlp 更新的時間戳
        self.update_task = self.update_embed
        self.song_switch_lock = asyncio.Lock()  # 新增切歌鎖
        self.playlist_per_page = 5  # 播放清單每頁顯示歌曲數量
        self.current_playlist_page = 1
        self.total_playlist_pages = 1
        self.total_playlist_songs = 0

    async def cog_load(self):
        os.makedirs("./temp/music", exist_ok=True)
        logger.info("確認 ./temp/music 目錄存在")
        result = await check_and_download_ffmpeg()
        if result["status_code"] == 0:
            self.ffmpeg_path = result["relative_path"] # 使用相對路徑，如果異常就改成絕對路徑吧 absolute_path
            self.player_controller = MusicPlayerController(
                self.ffmpeg_path,
                "./temp/music",
                loop=asyncio.get_event_loop(),
                on_song_end=self.on_song_end  # 設置callback
            )
            self.yt_dlp_manager = YTDLPDownloader("./temp/music", self.ffmpeg_path)
        else:
            logger.error("FFmpeg 初始化失敗，無法正常啟動音樂播放器！")

    def cog_unload(self):
        asyncio.create_task(self.cleanup_resources())
        logger.info("[MusicPlayerCog] 已卸載，資源已清理。")

    async def cleanup_resources(self):
        """
        清理資源，包括斷開語音連接、重置狀態等
        """
        try:
            # 停止播放並斷開語音連接
            if self.player_controller and self.player_controller.voice_client:
                await self.player_controller.stop()
                await self.player_controller.voice_client.disconnect()

            # 清空播放清單
            if self.playlist_manager:
                self.playlist_manager.clear()

            # 停止嵌入更新任務
            if self.update_task.is_running():
                self.update_task.stop()
                logger.info("已停止嵌入更新任務")

            # 清空下載目錄的暫存檔案
            self.yt_dlp_manager.clear_temp_files()

            # 重置與播放相關的狀態
            self.player_message = None
            self.playlist_message = None
            self.current_playlist_page = 1
            self.total_playlist_pages = 1
            self.total_playlist_songs = 0

            logger.info("成功清理資源並重置狀態。")
        except Exception as e:
            logger.error(f"清理資源時發生錯誤：{e}")

    async def on_song_end(self):
        """
        播放完成後的處理邏輯，確保所有情況下更新嵌入訊息與按鈕狀態
        此方法只有在歌曲自然播放結束時才會被調用（手動停止時不會觸發）
        """
        logger.debug("歌曲自然播放結束，準備處理下一首...")
        
        # 檢查是否為最近手動操作引起的callback
        current_time = time.time()
        time_since_last_manual_operation = current_time - self.player_controller.last_manual_operation_time
        if time_since_last_manual_operation < 1.0:  # 如果在最近1秒內有手動操作，則忽略此callback
            logger.debug(f"檢測到最近的手動操作 ({time_since_last_manual_operation:.2f}秒前)，忽略自動切歌callback")
            return
            
        async with self.song_switch_lock:
            # 如果播放清單為空
            if not self.playlist_manager.playlist:
                logger.debug("播放清單為空，停止播放")
                self.player_controller.is_playing = False
                self.player_controller.current_song = None
                embed = self.embed_manager.error_embed("播放清單中無音樂")
                await self.update_buttons_view()
                if self.player_message:
                    await self.player_message.edit(embed=embed, view=self.buttons_view)
                return

            # 如果播放清單只有一首
            if len(self.playlist_manager.playlist) == 1:
                logger.debug("播放清單僅有一首，處理單首邏輯")
                current_song = self.playlist_manager.get_current_song()
                if not current_song:
                    logger.error("邏輯錯誤：播放清單長度為1但無法獲取歌曲")
                    return
                
                # 單首歌重複播放模式
                if self.playlist_manager.loop:
                    logger.debug("單首歌循環模式，重新播放同一首")
                    await self.player_controller.play_song(current_song["id"])
                # 單首不重複，播放完就不再播放
                else:
                    logger.debug("單首歌非循環模式，播放結束後停止")
                    self.player_controller.is_playing = False
                    embed = self.embed_manager.playing_embed(
                        current_song,
                        is_looping=self.playlist_manager.loop,
                        is_playing=False
                    )
                    await self.update_buttons_view()
                    if self.player_message:
                        await self.player_message.edit(embed=embed, view=self.buttons_view)
                return
            
            # 多首歌情況
            logger.debug("播放清單有多首歌，嘗試切換到下一首")
            next_song = self.playlist_manager.switch_to_next_song()
            if next_song:
                logger.info(f"自動切換到下一首: {next_song['title']}")
                await self.player_controller.play_song(next_song["id"])
                embed = self.embed_manager.playing_embed(
                    next_song,
                    is_looping=self.playlist_manager.loop,
                    is_playing=True
                )
                await self.update_buttons_view()
                if self.player_message:
                    await self.player_message.edit(embed=embed, view=self.buttons_view)
            else:
                logger.warning("無法切換到下一首歌曲（可能是播放清單已播放完）")
                self.player_controller.is_playing = False
                current_song = self.playlist_manager.get_current_song()
                if current_song:
                    embed = self.embed_manager.playing_embed(
                        current_song,
                        is_looping=self.playlist_manager.loop,
                        is_playing=False
                    )
                    await self.update_buttons_view()
                    if self.player_message:
                        await self.player_message.edit(embed=embed, view=self.buttons_view)

    async def check_and_update_yt_dlp(self):
        """
        檢查 yt-dlp 是否有更新，並自動更新至最新版（若有需要）
        """
        try:
            yt_dlp_path = shutil.which("yt-dlp")
            if yt_dlp_path:
                logger.info("[YT-DLP] 檢查 yt-dlp 是否需要更新...")
                result = subprocess.run(
                    ["yt-dlp", "-U"],  # 自動更新
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                logger.debug(f"[YT-DLP] 更新輸出：\n{result.stdout.strip()}")
            else:
                logger.warning("[YT-DLP] 找不到 yt-dlp，可執行檔未加入 PATH 或尚未安裝。")
        except Exception as e:
            logger.error(f"[YT-DLP] 檢查或更新 yt-dlp 時發生錯誤：{e}")

    @discord.app_commands.command(name="音樂-啟動播放器", description="啟動音樂播放器並播放指定的 URL")
    @discord.app_commands.rename(url="youtube網址")
    @discord.app_commands.describe(url="YouTube 影片或播放清單的網址")
    async def start_player(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer()
        if time.time() - (self.last_yt_dlp_check or 0) > 86400:  # 每 24 小時檢查一次更新
            await self.check_and_update_yt_dlp() # 檢查 yt-dlp 更新
            self.last_yt_dlp_check = time.time()

        # 檢查 FFmpeg 初始化
        if not self.ffmpeg_path or not self.player_controller:
            await interaction.followup.send("FFmpeg 尚未初始化，請稍後再試。", ephemeral=True)
            return

        # 檢查用戶是否在語音頻道中
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("請先加入語音頻道再執行此指令。", ephemeral=True)
            return

        # 檢查播放器是否正在運行
        if self.player_controller.is_playing:
            await interaction.followup.send("播放器已經啟動，請使用 \"音樂-新增音樂至播放清單\" 功能。", ephemeral=True)
            return

        try:
            # 下載音樂資源
            song_info, file_path = await self.yt_dlp_manager.async_download(url)
            if not song_info or not file_path:
                await interaction.followup.send("下載音樂失敗，請確認 URL 是否正確。", ephemeral=True)
                return

            # 新增歌曲到播放清單
            song_info = self.playlist_manager.add(song_info)
            
            # 嘗試加入語音頻道
            try:
                channel = interaction.user.voice.channel
                voice_client = await channel.connect()
                await self.player_controller.set_voice_client(voice_client)
            except discord.ClientException as e:
                logger.error(f"連接語音頻道失敗：{e}")
                await interaction.followup.send("無法加入語音頻道，請確認機器人是否有權限。", ephemeral=True)
                return

            # 播放音樂
            await self.player_controller.play_song(song_info["id"])

            # 生成嵌入並更新按鈕狀態
            embed = self.embed_manager.playing_embed(song_info, is_looping=False, is_playing=True)
            await self.update_buttons_view()
            await interaction.followup.send(embed=embed, view=self.buttons_view)
            response = await interaction.original_response()
            self.player_message = await response.channel.fetch_message(response.id)

            # 啟動更新任務
            if not self.update_task.is_running():
                self.update_task.start()

        except Exception as e:
            logger.error(f"啟動播放器時發生錯誤：{e}")
            await interaction.followup.send(f"啟動播放器時發生錯誤：{e}", ephemeral=True)

    @discord.app_commands.command(name="音樂-新增音樂到播放清單", description="新增音樂到播放清單")
    @discord.app_commands.describe(url="YouTube 影片的網址")
    @discord.app_commands.rename(url="youtube網址")
    async def add_music(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer()

        # 檢查播放器是否已啟用
        if not self.player_controller or not self.player_controller.voice_client:
            await interaction.followup.send("播放器尚未啟用，請先使用 `/音樂-啟動播放器` 指令。", ephemeral=True)
            return

        try:
            # 下載音樂資訊
            song_info, file_path = await self.yt_dlp_manager.async_download(url)
            if not song_info or not file_path:
                await interaction.followup.send("無法下載音樂，請確認 URL 是否正確。", ephemeral=True)
                return

            # 新增音樂到播放清單
            song_info = self.playlist_manager.add(song_info)
            embed = self.embed_manager.added_song_embed(song_info)

            # 🆕 若已播完最後一首又加新歌，就自動切到新加的那一首
            async with self.song_switch_lock:
                if not self.player_controller.is_playing and not self.playlist_manager.loop:
                    # 直接讓 current_index 指向最後一首
                    self.playlist_manager.current_index = len(self.playlist_manager.playlist) - 1
                    logger.debug(f"播放已結束，自動將 current_index 移至新歌曲：{self.playlist_manager.current_index}")

            # 更新按鈕狀態
            await self.update_buttons_view()
            if self.player_message:
                await self.player_message.edit(view=self.buttons_view)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"新增音樂時發生錯誤：{e}")
            await interaction.followup.send("無法新增音樂，請稍後再試。", ephemeral=True)

    @discord.app_commands.command(name="音樂-查看播放清單", description="查看當前播放清單")
    async def view_playlist(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            # 如果已有播放清單視圖，先清除舊的按鈕
            if self.playlist_message:
                try:
                    await self.playlist_message.edit(view=None)
                    logger.debug("已清除舊的播放清單按鈕")
                except Exception as e:
                    logger.error(f"清除舊播放清單按鈕時發生錯誤：{e}")
                self.playlist_message = None

            # 獲取第一頁清單資料
            playlist_page = self.playlist_manager.get_playlist_paginated(page=1, per_page=self.playlist_per_page)
            embed = self.embed_manager.playlist_embed(playlist_page)
            
            # 保存當前頁面信息到實例屬性中
            self.current_playlist_page = 1
            self.total_playlist_pages = playlist_page["total_pages"]
            self.total_playlist_songs = playlist_page["total_songs"]
            logger.debug(f"初始化播放清單分頁狀態: 當前頁={self.current_playlist_page}, 總頁數={self.total_playlist_pages}, 總歌曲數={self.total_playlist_songs}")

            # 初始化翻頁按鈕
            self.pagination_buttons = PaginationButtons(
                self.pagination_button_callback, self.playlist_view_timeout_callback)

            # 更新按鈕狀態 - 根據總頁數禁用按鈕
            # 如果只有一頁或沒有歌曲，禁用所有翻頁按鈕
            if self.total_playlist_pages <= 1:
                await self.pagination_buttons.update_buttons({
                    "previous_page": {"disabled": True},
                    "next_page": {"disabled": True}
                })
                logger.debug(f"播放清單只有 {self.total_playlist_pages} 頁，禁用所有翻頁按鈕")
            else:
                await self.pagination_buttons.update_buttons({
                    "previous_page": {"disabled": self.current_playlist_page == 1},
                    "next_page": {"disabled": self.current_playlist_page >= self.total_playlist_pages}
                })
                logger.debug(f"播放清單有 {self.total_playlist_pages} 頁，設置翻頁按鈕狀態：previous={self.current_playlist_page == 1}, next={self.current_playlist_page >= self.total_playlist_pages}")

            # 發送訊息並保存原始訊息
            await interaction.followup.send(embed=embed, view=self.pagination_buttons)
            response = await interaction.original_response()
            self.playlist_message = await response.channel.fetch_message(response.id)
        except Exception as e:
            logger.error(f"查看播放清單時發生錯誤：{e}")
            await interaction.followup.send("無法查看播放清單，請稍後再試。", ephemeral=True)

    async def pagination_button_callback(self, interaction: discord.Interaction, action: str):
        """
        翻頁按鈕的callback
        """
        try:
            # 確保 playlist_message 存在
            if not self.playlist_message:
                logger.error("沒有找到對應的 playlist 訊息！")
                await interaction.response.send_message("無法找到播放清單，請重新執行查看播放清單指令。", ephemeral=True)
                return

            # 獲取最新的播放清單數據
            temp_page = self.playlist_manager.get_playlist_paginated(page=1, per_page=self.playlist_per_page)
            self.total_playlist_pages = temp_page["total_pages"]
            self.total_playlist_songs = temp_page["total_songs"]
            logger.debug(f"翻頁操作獲取最新狀態: 當前頁={self.current_playlist_page}, 總頁數={self.total_playlist_pages}, 總歌曲數={self.total_playlist_songs}")

            # 計算新頁碼
            new_page = self.current_playlist_page - 1 if action == "previous_page" else self.current_playlist_page + 1
            logger.debug(f"計算新頁碼: {new_page} (從 {self.current_playlist_page})")
            
            # 頁碼範圍檢查
            if new_page < 1:
                new_page = 1
                logger.debug(f"頁碼小於1，設置為第1頁")
            elif new_page > self.total_playlist_pages:
                new_page = self.total_playlist_pages 
                logger.debug(f"頁碼大於總頁數，設置為最後一頁 {self.total_playlist_pages}")
                
            # 獲取新頁面的數據
            playlist_page = self.playlist_manager.get_playlist_paginated(page=new_page, per_page=self.playlist_per_page)
            logger.debug(f"獲取第{new_page}頁資料，實際返回頁碼:{playlist_page['current_page']}, 總頁數:{playlist_page['total_pages']}")

            # 更新當前頁面
            self.current_playlist_page = playlist_page["current_page"]
            logger.debug(f"更新當前頁面編號為: {self.current_playlist_page}")

            # 生成新嵌入
            embed = self.embed_manager.playlist_embed(playlist_page)

            # 更新按鈕狀態
            await self.pagination_buttons.update_buttons({
                "previous_page": {"disabled": self.current_playlist_page <= 1},
                "next_page": {"disabled": self.current_playlist_page >= self.total_playlist_pages}
            })

            # 編輯原始訊息
            await self.playlist_message.edit(embed=embed, view=self.pagination_buttons)
            logger.debug(f"頁面已更新至第{self.current_playlist_page}頁")

        except Exception as e:
            logger.error(f"翻頁處理時發生未預期錯誤：{e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("翻頁時發生錯誤，請稍後再試。", ephemeral=True)
            else:
                await interaction.followup.send("翻頁時發生錯誤，請稍後再試。", ephemeral=True)

    async def playlist_view_timeout_callback(self):
        logger.info("翻頁按鈕已超時，清理按鈕")
        if self.playlist_message:
            await self.playlist_message.edit(view=None)  # 清除按鈕視圖

    @discord.app_commands.command(name="音樂-清理播放清單", description="清空播放清單")
    async def clear_playlist(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            # 停止播放並清空播放清單
            async with self.song_switch_lock:
                if self.player_controller.is_playing:
                    await self.player_controller.stop()
                self.playlist_manager.clear()
            # 更新按鈕狀態
            await self.update_buttons_view()
            if self.player_message:
                await self.player_message.edit(view=None)
            # 發送清空訊息
            embed = self.embed_manager.clear_playlist_embed()
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"清理播放清單時發生錯誤：{e}")
            await interaction.followup.send("清理播放清單時發生錯誤，請稍後再試。", ephemeral=True)

    async def song_index_autocomplete(self, interaction: discord.Interaction, current: str):
        """
        提供播放清單歌曲編號的 Autocomplete
        """
        try:
            # 過濾符合當前輸入的歌曲（根據歌曲名稱或編號）
            suggestions = [
                discord.app_commands.Choice(name=f"{song['index']}. {song['title']}", value=song['index'])
                for song in self.playlist_manager.playlist if current in str(song["index"])
            ]
            return suggestions[:25]  # 限制返回的選項數量為 25
        except Exception as e:
            logger.error(f"Autocomplete 過程中發生錯誤：{e}")
            return []

    # 斜線指令 - 移除播放清單中的特定音樂
    @discord.app_commands.command(name="音樂-移除播放清單特定音樂", description="移除播放清單中的特定音樂")
    @discord.app_commands.describe(index="輸入要移除的歌曲編號")
    @discord.app_commands.rename(index="歌曲編號")
    @discord.app_commands.autocomplete(index=song_index_autocomplete)
    async def remove_song_from_playlist(self, interaction: discord.Interaction, index: int):
        await interaction.response.defer()

        try:
            # 嘗試移除指定的歌曲
            song_to_remove = next((song for song in self.playlist_manager.playlist if song["index"] == index), None)
            if not song_to_remove:
                await interaction.followup.send(f"找不到編號為 `{index}` 的歌曲。", ephemeral=True)
                return

            # 移除歌曲
            self.playlist_manager.remove(index)
            embed = self.embed_manager.removed_song_embed(song_to_remove)

            # 更新播放器按鈕狀態
            await self.update_buttons_view()
            if self.player_message:
                await self.player_message.edit(view=self.buttons_view)

            # 回應用戶
            await interaction.followup.send(embed=embed,)

        except Exception as e:
            logger.error(f"移除播放清單中的音樂時發生錯誤：{e}")
            await interaction.followup.send("移除音樂時發生錯誤，請稍後再試。", ephemeral=True)

    async def button_action_handler(self, interaction: discord.Interaction, action: str):
        # 只針對 next/previous/leave 做鎖保護，其他分支不進鎖
        if action in ("next", "previous", "leave"):
            async with self.song_switch_lock:
                await self._button_action_handler_core(interaction, action)
        else:
            await self._button_action_handler_core(interaction, action)

    async def _button_action_handler_core(self, interaction: discord.Interaction, action: str):
        try:
            current_song = self.playlist_manager.get_current_song()
            current_status = self.player_controller.get_current_status()
            is_playing = current_status["is_playing"]

            if action == "play_pause":
                logger.debug(f"按下播放/暫停按鈕，當前播放狀態：{is_playing}")
                if self.player_controller.is_paused:
                    await self.player_controller.resume()
                    is_playing = True
                    await self.update_buttons_view()
                elif not self.player_controller.is_playing:
                    next_song = self.playlist_manager.get_current_song()
                    if next_song:
                        logger.info(f"重新播放: {next_song['title']}")
                        await self.player_controller.play_song(next_song["id"])
                        is_playing = True
                        await self.update_buttons_view()
                    else:
                        logger.warning("播放清單為空，無法播放")
                        embed = self.embed_manager.error_embed("播放清單為空，請新增歌曲")
                        await self.update_buttons_view()
                        return
                else:
                    await self.player_controller.pause()
                    is_playing = False
                    await self.update_buttons_view()
            elif action == "next":
                logger.debug("按下下一首按鈕")
                # 記錄操作時間戳 - 在 player_controller.stop() 已經隱含更新
                await self.player_controller.stop()
                next_song = self.playlist_manager.switch_to_next_song()
                logger.debug(f"下一首歌曲：{next_song}")
                if next_song:
                    await self.player_controller.play_song(next_song["id"])
                    current_song = next_song
                    is_playing = True
                else:
                    current_song = self.playlist_manager.get_current_song()
                await self.update_buttons_view()

            elif action == "previous":
                logger.debug("按下上一首按鈕")
                # 記錄操作時間戳 - 在 player_controller.stop() 已經隱含更新
                await self.player_controller.stop()
                prev_song = self.playlist_manager.switch_to_previous_song()
                logger.debug(f"上一首歌曲：{prev_song}")
                if prev_song:
                    await self.player_controller.play_song(prev_song["id"])
                    current_song = prev_song
                    is_playing = True
                else:
                    current_song = self.playlist_manager.get_current_song()
                await self.update_buttons_view()

            elif action == "loop":
                logger.debug("按下循環開關按鈕")
                self.playlist_manager.loop = not self.playlist_manager.loop
                current_song = self.playlist_manager.get_current_song()
                is_playing = current_status["is_playing"]
                logger.debug(f"循環模式：{self.playlist_manager.loop}")
                await self.update_buttons_view()

            elif action == "leave":
                logger.debug("按下離開按鈕")
                embed = self.embed_manager.clear_playlist_embed()
                await self.player_message.edit(embed=embed, view=None)
                await self.cleanup_resources()
                return

            # 更新嵌入和按鈕狀態
            embed = self.embed_manager.playing_embed(
                current_song,
                is_looping=self.playlist_manager.loop,
                is_playing=is_playing,
                current_time=0 if action in ("next", "previous") else current_status["current_sec"]  # 切換歌曲時重置進度
            )
            await self.update_buttons_view()
            await self.buttons_view.update_buttons({
                "loop": {"style": discord.ButtonStyle.green if self.playlist_manager.loop else discord.ButtonStyle.grey}
            })
            await self.player_message.edit(embed=embed, view=self.buttons_view)

        except Exception as e:
            logger.error(f"處理按鈕動作時發生錯誤：{e}")
            embed = self.embed_manager.error_embed(f"處理按鈕動作時發生錯誤：{e}")
            await self.player_message.edit(embed=embed)

    async def update_buttons_view(self):
        """
        更新按鈕狀態，根據播放清單和當前索引的狀態禁用/啟用按鈕。
        - play_pause: 清單為空時禁用
        - next: 只查詢下一首（不切歌），若無下一首則禁用
        - previous: 只查詢上一首（不切歌），若無上一首則禁用
        """
        is_empty = len(self.playlist_manager.playlist) == 0
        is_single = len(self.playlist_manager.playlist) == 1

        button_updates = {
            "play_pause": {"disabled": is_empty},
            "next": {"disabled": is_single or self.playlist_manager.get_next_song_info() is None},
            "previous": {"disabled": is_single or self.playlist_manager.get_previous_song_info() is None}
        }
        await self.buttons_view.update_buttons(button_updates)

    @tasks.loop(seconds=15)
    async def update_embed(self):
        """
        定期更新嵌入訊息，顯示當前播放狀態
        使用song_switch_lock確保與切歌操作不會發生衝突
        """
        try:
            # 如果正在播放
            if not self.player_controller or not self.player_controller.is_playing:
                return

            # 嘗試獲取鎖，但使用短暫的超時以避免與操作阻塞
            try:
                # 使用0.5秒超時嘗試獲取鎖，如果無法獲取則跳過本次更新
                acquired = await asyncio.wait_for(self.song_switch_lock.acquire(), timeout=0.5)
                if not acquired:
                    logger.debug("無法獲取切歌鎖，跳過本次嵌入更新")
                    return
            except asyncio.TimeoutError:
                logger.debug("獲取切歌鎖超時，跳過本次嵌入更新")
                return

            try:
                # 雙重檢查，確保在獲取鎖之後仍然在播放中
                if not self.player_controller.is_playing:
                    return

                current_status = self.player_controller.get_current_status()
                current_song = self.playlist_manager.get_current_song()
                
                if not current_song:
                    logger.warning("更新嵌入時發現目前無歌曲，跳過嵌入更新")
                    return

                embed = self.embed_manager.playing_embed(
                    current_song,
                    is_looping=self.playlist_manager.loop,
                    is_playing=self.player_controller.is_playing and not self.player_controller.is_paused,
                    current_time=current_status["current_sec"]
                )
                
                # 更新按鈕狀態
                await self.update_buttons_view()
                
                # 更新嵌入訊息
                if self.player_message:
                    await self.player_message.edit(embed=embed, view=self.buttons_view)
                    logger.debug(f"更新播放嵌入成功：{current_song['title']} - {current_status['current_sec']}秒")
            finally:
                # 在任何情況下都釋放鎖
                self.song_switch_lock.release()
        except Exception as e:
            logger.error(f"更新播放嵌入時發生錯誤：{str(e)}")
            logger.exception(e)  # 輸出完整例外

async def setup(bot):
    await bot.add_cog(MusicPlayerCog(bot))