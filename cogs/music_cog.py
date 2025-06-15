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
        self.playlist_per_page = 5  # 播放清單每頁顯示歌曲數量
        self.current_playlist_page = 1
        self.total_playlist_pages = 1
        self.total_playlist_songs = 0
        self.last_voice_channel = None  # 保存最後連接的語音頻道
        self.manual_disconnect = False  # 標記是否為手動斷開連接
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 15  # 增加到15次重試
        self.reconnect_backoff_threshold = 5  # 第5次後開始延長間隔

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

    async def cog_unload(self):
        await self.cleanup_resources()
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
            
            # 根據手動斷開狀態決定是否重置語音頻道
            if self.manual_disconnect:
                self.last_voice_channel = None

            logger.info("成功清理資源並重置狀態。")
        except Exception as e:
            logger.error(f"清理資源時發生錯誤：{e}")

    async def on_song_end(self):
        """
        播放完成後的處理邏輯，確保所有情況下更新嵌入訊息與按鈕狀態
        此方法只有在歌曲自然播放結束時才會被調用（手動停止時不會觸發）
        """
        logger.debug("歌曲自然播放結束，準備處理下一首...")
        current_time = time.time()
        time_since_last_manual_operation = current_time - self.player_controller.last_manual_operation_time
        if time_since_last_manual_operation < 1.0:
            logger.debug(f"檢測到最近的手動操作 ({time_since_last_manual_operation:.2f}秒前)，忽略自動切歌callback")
            return
            
        # 如果播放清單為空
        if not self.playlist_manager.playlist:
            logger.debug("播放清單為空，停止播放")
            self.player_controller.is_playing = False
            self.player_controller.current_song = None
            embed = self.embed_manager.error_embed("播放清單中無音樂")
            embed.set_author(name="")
            embed.description = "無音樂可播放"
            embed.set_field_at(0, name="狀態", value="請透過指令\n[音樂-新增音樂到播放清單]\n來新增音樂", inline=False)
            
            # 禁用所有按鈕
            await self.buttons_view.update_buttons({
                "play_pause": {"disabled": True},
                "next": {"disabled": True},
                "previous": {"disabled": True},
                "loop": {"disabled": True}
            })
            
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
            # 記錄當前歌曲索引，以便在錯誤時移除
            current_song_index = next_song['index']
            logger.info(f"自動切換到下一首: {next_song['title']}")
            
            # 檢查檔案是否已存在，存在就直接播放
            opus_path = os.path.join("./temp/music", f"{next_song['id']}.opus")
            if os.path.exists(opus_path):
                await self.player_controller.play_song(next_song["id"])
                embed = self.embed_manager.playing_embed(next_song, is_looping=self.playlist_manager.loop, is_playing=True)
                await self.update_buttons_view()
                if self.player_message:
                    await self.player_message.edit(embed=embed, view=self.buttons_view)
                return
                
            # 檔案不存在，需要下載
            # 先切換嵌入到新歌資訊，狀態顯示下載中
            embed = self.embed_manager.playing_embed(next_song, is_looping=self.playlist_manager.loop, is_playing=False)
            embed.set_field_at(0, name="狀態", value="下載中...", inline=False)
            if self.player_message:
                await self.player_message.edit(embed=embed, view=self.buttons_view)
                
            # 下載新歌
            song_info, file_path = await self.yt_dlp_manager.async_download(next_song["url"])
            
            # 檢查下載結果，處理可能的錯誤
            if not file_path and isinstance(song_info, dict) and song_info.get("success") is False:
                # 取得錯誤資訊
                error_type = song_info.get("error_type", "unknown")
                display_message = song_info.get("display_message", "影片無法播放")
                
                logger.warning(f"歌曲無法下載: {next_song['title']} - {display_message}")
                
                # 使用通用的錯誤處理方法
                has_songs = await self._handle_song_playback_error(next_song, display_message, current_song_index)
                
                # 如果還有歌曲，繼續處理下一首
                if has_songs:
                    await self.on_song_end()
                return
            
            # 一般下載失敗
            elif not song_info or not file_path:
                # 使用通用的錯誤處理方法處理未知錯誤
                has_songs = await self._handle_song_playback_error(next_song, "未知原因", current_song_index)
                
                # 如果還有歌曲，繼續處理下一首
                if has_songs:
                    await self.on_song_end()
                return
            
            # 下載成功
            await self.player_controller.play_song(next_song["id"])
            current_song = next_song
            is_playing = True
            await self.update_buttons_view()
            if self.player_message:
                await self.player_message.edit(embed=embed, view=self.buttons_view)
            return
            
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
            await interaction.followup.send("FFmpeg 尚未初始化，請稍後再試。")
            return
        # 檢查用戶是否在語音頻道中
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("請先加入語音頻道再執行此指令。")
            return
        # 檢查播放器是否正在運行
        if (
            self.player_controller.voice_client and
            self.player_controller.voice_client.is_connected() and
            self.player_message
        ):
            await interaction.followup.send("播放器已經啟動，請使用 \"音樂-新增音樂至播放清單\" 功能。")
            return
        try:
            is_playlist = self.yt_dlp_manager.is_playlist(url)
            original_msg = await interaction.original_response()
            self.player_message = await original_msg.channel.fetch_message(original_msg.id)
            if is_playlist:
                await interaction.followup.send("⏳ 正在解析撥放清單，請稍候...")
                await self._handle_playlist_start(interaction, url)
            else:
                await self._handle_single_song_start(interaction, url)
        except Exception as e:
            logger.error(f"啟動播放器時發生錯誤：{e}")
            if self.player_message:
                embed = self.embed_manager.error_embed(f"啟動播放器時發生錯誤：{e}")
                await self.player_message.edit(content=None, embed=embed, view=None)
            else:
                await interaction.followup.send(f"啟動播放器時發生錯誤：{e}")

    async def _handle_single_song_start(self, interaction, url):
        try:
            # 下載音樂資源（不先顯示embed，等下載好才顯示）
            song_info, file_path = await self.yt_dlp_manager.async_download(url)
            
            # 檢查下載結果，處理可能的錯誤
            if not file_path and isinstance(song_info, dict) and song_info.get("success") is False:
                # 取得錯誤資訊
                error_type = song_info.get("error_type", "unknown")
                display_message = song_info.get("display_message", "影片無法播放")
                
                logger.warning(f"啟動播放器 - 歌曲無法下載: {url} - {display_message}")
                
                # 顯示錯誤訊息
                embed = self.embed_manager.error_embed(f"❌ {display_message}\n\n請嘗試其他影片或檢查 YouTube 連結是否正確。")
                await self.player_message.edit(content=None, embed=embed, view=None)
                return
            # 一般下載失敗
            elif not song_info or not file_path:
                embed = self.embed_manager.error_embed("下載音樂失敗，請確認 URL 是否正確。")
                await self.add_musicplayer_message.edit(content=None, embed=embed, view=None)
                return
                
            # 新增歌曲到播放清單，並用 add 回傳的 song_info（含 index）
            song_info = self.playlist_manager.add(song_info)
            # 嘗試加入語音頻道
            try:
                channel = interaction.user.voice.channel
                voice_client = await channel.connect()
                self.last_voice_channel = channel
                self.manual_disconnect = False
                await self.player_controller.set_voice_client(voice_client)
            except discord.ClientException as e:
                logger.error(f"連接語音頻道失敗：{e}")
                embed = self.embed_manager.error_embed("無法加入語音頻道，請確認機器人是否有權限。")
                await self.player_message.edit(content=None, embed=embed, view=None)
                return
            await self.player_controller.play_song(song_info["id"])
            # 這裡一定要用 add 後的 song_info
            embed = self.embed_manager.playing_embed(song_info, is_looping=False, is_playing=True)
            await self.update_buttons_view()
            await self.player_message.edit(content=None, embed=embed, view=self.buttons_view)
            if not self.update_task.is_running():
                self.update_task.start()
        except Exception as e:
            logger.error(f"啟動單曲播放時發生錯誤：{e}")
            embed = self.embed_manager.error_embed(f"啟動播放器時發生錯誤：{e}")
            await self.player_message.edit(content=None, embed=embed, view=None)

    async def _handle_playlist_start(self, interaction, url):
        try:
            # 解析播放清單
            playlist_entries = await self.yt_dlp_manager.async_extract_playlist_info(url)
            if not playlist_entries or (isinstance(playlist_entries, dict) and playlist_entries.get("success") is False):
                # 檢查是否返回的是錯誤訊息
                if isinstance(playlist_entries, dict) and playlist_entries.get("success") is False:
                    error_type = playlist_entries.get("error_type", "unknown")
                    display_message = playlist_entries.get("display_message", "播放清單無法解析")
                    logger.warning(f"無法解析播放清單: {url} - {display_message}")
                    embed = self.embed_manager.error_embed(f"❌ {display_message}")
                else:
                    embed = self.embed_manager.error_embed("無法解析播放清單或播放清單為空，請確認 URL 是否正確。")
                await self.player_message.edit(content=None, embed=embed, view=None)
                return
                
            # 下載第一首歌曲（不先顯示embed，等下載好才顯示）
            first_song = playlist_entries[0]
            song_info, file_path = await self.yt_dlp_manager.async_download(first_song["url"])
            
            # 檢查下載結果，處理可能的錯誤
            if not file_path and isinstance(song_info, dict) and song_info.get("success") is False:
                # 取得錯誤資訊
                error_type = song_info.get("error_type", "unknown")
                display_message = song_info.get("display_message", "第一首歌曲無法播放")
                
                logger.warning(f"播放清單第一首歌曲無法下載: {first_song['title']} - {display_message}")
                
                # 檢查播放清單是否還有其他歌曲
                if len(playlist_entries) > 1:
                    # 顯示正在嘗試下一首的訊息
                    await self.player_message.edit(content=None, embed=self.embed_manager.error_embed(f"⚠️ 播放清單第一首歌曲 {first_song['title']} 無法播放: {display_message}\n\n正在嘗試下一首..."), view=None)
                    
                    # 移除第一首歌曲，使用第二首作為起始歌曲
                    playlist_entries = playlist_entries[1:]
                    first_song = playlist_entries[0]
                    
                    # 嘗試下載新的第一首
                    song_info, file_path = await self.yt_dlp_manager.async_download(first_song["url"])
                    
                    # 檢查新的第一首是否可以下載
                    if not song_info or not file_path:
                        embed = self.embed_manager.error_embed(f"❌ 播放清單前兩首歌曲都無法播放。請嘗試其他播放清單。")
                        await self.player_message.edit(content=None, embed=embed, view=None)
                        return
                else:
                    # 如果播放清單只有一首歌，並且無法播放
                    embed = self.embed_manager.error_embed(f"❌ {display_message}\n\n播放清單只有一首歌曲且無法播放。請嘗試其他播放清單。")
                    await self.player_message.edit(content=None, embed=embed, view=None)
                    return
            # 一般下載失敗
            elif not song_info or not file_path:
                embed = self.embed_manager.error_embed("下載第一首歌曲失敗，請稍後再試。")
                await self.player_message.edit(content=None, embed=embed, view=None)
                return
                
            # 批次 add 進 playlist_manager，並取得 add 後的第一首（含 index）
            added_entries = self.playlist_manager.add_many(playlist_entries)
            first_added_song = added_entries[0] if added_entries else None
            # 嘗試加入語音頻道
            try:
                channel = interaction.user.voice.channel
                voice_client = await channel.connect()
                self.last_voice_channel = channel
                self.manual_disconnect = False
                await self.player_controller.set_voice_client(voice_client)
            except discord.ClientException as e:
                logger.error(f"連接語音頻道失敗：{e}")
                embed = self.embed_manager.error_embed("無法加入語音頻道，請確認機器人是否有權限。")
                await self.player_message.edit(content=None, embed=embed, view=None)
                return
            await self.player_controller.play_song(song_info["id"])
            # 這裡一定要用 add 後的 first_added_song
            embed = self.embed_manager.playing_embed(first_added_song, is_looping=False, is_playing=True)
            await self.update_buttons_view()
            await self.player_message.edit(content=None, embed=embed, view=self.buttons_view)
            if not self.update_task.is_running():
                self.update_task.start()
        except Exception as e:
            logger.error(f"啟動播放清單時發生錯誤：{e}")
            embed = self.embed_manager.error_embed(f"啟動播放清單時發生錯誤：{e}")
            await self.player_message.edit(content=None, embed=embed, view=None)

    @discord.app_commands.command(name="音樂-新增音樂到播放清單", description="新增音樂到播放清單")
    @discord.app_commands.describe(url="YouTube 影片或播放清單的網址")
    @discord.app_commands.rename(url="youtube網址")
    async def add_music(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer()

        # 檢查播放器是否已啟用
        if not self.player_controller or not self.player_controller.voice_client:
            await interaction.followup.send("播放器尚未啟用，請先使用 `/音樂-啟動播放器` 指令。", ephemeral=True)
            return

        try:
            # 記錄用戶的語音頻道（如果用戶在語音頻道中）
            if interaction.user.voice and interaction.user.voice.channel:
                self.last_voice_channel = interaction.user.voice.channel
                logger.debug(f"更新最後連接的語音頻道: {self.last_voice_channel.name}")
                
            # 檢查是否是播放清單
            is_playlist = self.yt_dlp_manager.is_playlist(url)
            
            if is_playlist:
                await self._handle_playlist_add(interaction, url)
            else:
                await self._handle_single_song_add(interaction, url)
                
        except Exception as e:
            logger.error(f"新增音樂時發生錯誤：{e}")
            await interaction.followup.send("無法新增音樂，請稍後再試。", ephemeral=True)
            
    async def _handle_single_song_add(self, interaction, url):
        """處理單首歌曲的新增邏輯"""
        try:
            # 下載音樂資訊
            song_info, file_path = await self.yt_dlp_manager.async_download(url)
            
            # 檢查下載結果，處理可能的錯誤
            if not file_path and isinstance(song_info, dict) and song_info.get("success") is False:
                # 取得錯誤資訊
                error_type = song_info.get("error_type", "unknown")
                display_message = song_info.get("display_message", "影片無法播放")
                
                logger.warning(f"無法新增歌曲: {url} - {display_message}")
                
                # 建立錯誤嵌入
                embed = discord.Embed(
                    title="❌ 無法新增歌曲",
                    description=f"**原因:** {display_message}",
                    color=discord.Color.red()
                )
                
                await interaction.followup.send(embed=embed)
                return
            # 一般下載失敗
            elif not song_info or not file_path:
                await interaction.followup.send("無法下載音樂，請確認 URL 是否正確。", ephemeral=True)
                return

            # 新增音樂到播放清單
            song_info = self.playlist_manager.add(song_info)
            embed = self.embed_manager.added_song_embed(song_info)

            # 🆕 若已播完最後一首又加新歌，就自動切到新加的那一首
            if not self.player_controller.is_playing and not self.playlist_manager.loop:
                # 直接讓 current_index 指向最後一首
                self.playlist_manager.current_index = len(self.playlist_manager.playlist) - 1
                logger.debug(f"播放已結束，自動將 current_index 移至新歌曲：{self.playlist_manager.current_index}")
                
                # 開始播放新加入的歌曲
                await self.player_controller.play_song(song_info["id"])
                
                # 更新播放訊息
                if self.player_message:
                    play_embed = self.embed_manager.playing_embed(song_info, is_looping=False, is_playing=True)
                    await self.player_message.edit(embed=play_embed, view=self.buttons_view)

            # 更新按鈕狀態
            await self.update_buttons_view()
            if self.player_message:
                await self.player_message.edit(view=self.buttons_view)
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"新增單曲時發生錯誤：{e}")
            await interaction.followup.send("無法新增音樂，請稍後再試。", ephemeral=True)
            
    async def _handle_playlist_add(self, interaction, url):
        """處理播放清單的新增邏輯"""
        try:
            # 提取播放清單資訊
            await interaction.followup.send("正在解析播放清單，請稍候...", ephemeral=True)
            playlist_entries = await self.yt_dlp_manager.async_extract_playlist_info(url)
            
            # 檢查播放清單解析結果
            if isinstance(playlist_entries, dict) and playlist_entries.get("success") is False:
                # 取得錯誤資訊
                error_type = playlist_entries.get("error_type", "unknown")
                display_message = playlist_entries.get("display_message", "播放清單無法解析")
                
                logger.warning(f"無法解析播放清單: {url} - {display_message}")
                
                # 顯示錯誤訊息
                embed = discord.Embed(
                    title="❌ 無法新增播放清單",
                    description=f"**原因:** {display_message}",
                    color=discord.Color.red()
                )
                
                await interaction.followup.send(embed=embed)
                return
            
            # 播放清單為空
            if not playlist_entries or len(playlist_entries) == 0:
                await interaction.followup.send("無法解析播放清單或播放清單為空，請確認 URL 是否正確。", ephemeral=True)
                return
                
            # 批次加入播放清單
            added_entries = self.playlist_manager.add_many(playlist_entries)
            added_count = len(added_entries)
            
            # 如果沒有成功添加任何歌曲
            if added_count == 0:
                await interaction.followup.send("播放清單中沒有可播放的歌曲，請嘗試其他播放清單。", ephemeral=True)
                return
            
            # 統計有效和無效歌曲數量
            filtered_count = len(playlist_entries) - added_count
            
            # 顯示添加結果
            playlist_msg = f"已將播放清單新增至佇列，共 {added_count} 首歌曲。"
            if filtered_count > 0:
                playlist_msg += f"\n⚠️ {filtered_count} 首歌曲因無法播放或已存在而被過濾。"
                
            embed = discord.Embed(
                title="✅ 已新增播放清單",
                description=playlist_msg,
                color=discord.Color.green()
            )
            
            # 若當前無播放，自動播放第一首
            if not self.player_controller.is_playing and not self.playlist_manager.loop:
                # 取得新增後的第一首歌曲的索引
                first_new_song_index = len(self.playlist_manager.playlist) - added_count
                self.playlist_manager.current_index = first_new_song_index
                logger.debug(f"播放已結束，自動將 current_index 移至播放清單第一首：{self.playlist_manager.current_index}")
                
                # 取得歌曲資訊
                first_song = self.playlist_manager.get_current_song()
                if first_song:
                    # 開始播放
                    await self.player_controller.play_song(first_song["id"])
                    
                    # 更新播放訊息
                    if self.player_message:
                        play_embed = self.embed_manager.playing_embed(first_song, is_looping=False, is_playing=True)
                        await self.player_message.edit(embed=play_embed, view=self.buttons_view)
            
            # 更新按鈕狀態
            await self.update_buttons_view()
            if self.player_message:
                await self.player_message.edit(view=self.buttons_view)
            
            # 發送結果訊息
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"新增播放清單時發生錯誤：{e}")
            logger.exception(e)
            await interaction.followup.send(f"無法新增播放清單，請稍後再試。", ephemeral=True)

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

            # 保存歌曲ID用於更安全的移除操作
            song_id = song_to_remove.get("id", "")
            
            # 移除歌曲 - 優先使用ID移除，若無ID則使用索引
            if song_id:
                logger.info(f"通過ID移除歌曲: {song_to_remove['title']} (ID: {song_id})")
                self.playlist_manager.remove_by_id(song_id)
            else:
                logger.info(f"通過索引移除歌曲: {song_to_remove['title']} (索引: {index})")
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
        # 直接處理按鈕動作，不再使用鎖保護
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
                await self.player_controller.stop()
                next_song = self.playlist_manager.switch_to_next_song()
                logger.debug(f"下一首歌曲：{next_song}")
                if next_song:
                    # 記錄當前歌曲索引，以便在錯誤時移除
                    current_song_index = next_song['index']
                    opus_path = os.path.join("./temp/music", f"{next_song['id']}.opus")
                    if os.path.exists(opus_path):
                        await self.player_controller.play_song(next_song["id"])
                        current_song = next_song
                        is_playing = True
                    else:
                        # 先切換嵌入到新歌資訊，狀態顯示下載中
                        embed = self.embed_manager.playing_embed(next_song, is_looping=self.playlist_manager.loop, is_playing=False)
                        embed.set_field_at(0, name="狀態", value="下載中...", inline=False)
                        if self.player_message:
                            await self.player_message.edit(embed=embed, view=self.buttons_view)
                        # 下載新歌
                        song_info, file_path = await self.yt_dlp_manager.async_download(next_song["url"])
                        
                        # 檢查下載結果，處理可能的錯誤
                        if not file_path and isinstance(song_info, dict) and song_info.get("success") is False:
                            # 取得錯誤資訊
                            error_type = song_info.get("error_type", "unknown")
                            display_message = song_info.get("display_message", "影片無法播放")
                            
                            logger.warning(f"按鈕動作 - 歌曲無法下載: {next_song['title']} - {display_message}")
                            
                            # 使用通用的錯誤處理方法
                            has_songs = await self._handle_song_playback_error(next_song, display_message, current_song_index)
                            
                            # 如果還有歌曲，繼續處理下一首
                            if has_songs:
                                await self.on_song_end()
                            return
                        
                        # 一般下載失敗
                        elif not song_info or not file_path:
                            # 使用通用的錯誤處理方法處理未知錯誤
                            has_songs = await self._handle_song_playback_error(next_song, "未知原因", current_song_index)
                            
                            # 如果還有歌曲，繼續處理下一首
                            if has_songs:
                                await self.on_song_end()
                            return
                        
                        # 下載成功
                        await self.player_controller.play_song(next_song["id"])
                        current_song = next_song
                        is_playing = True
                else:
                    current_song = self.playlist_manager.get_current_song()
                await self.update_buttons_view()
            elif action == "previous":
                logger.debug("按下上一首按鈕")
                await self.player_controller.stop()
                prev_song = self.playlist_manager.switch_to_previous_song()
                logger.debug(f"上一首歌曲：{prev_song}")
                if prev_song:
                    # 記錄當前歌曲索引，以便在錯誤時移除
                    current_song_index = prev_song['index']
                    opus_path = os.path.join("./temp/music", f"{prev_song['id']}.opus")
                    if os.path.exists(opus_path):
                        await self.player_controller.play_song(prev_song["id"])
                        current_song = prev_song
                        is_playing = True
                    else:
                        # 先切換嵌入到新歌資訊，狀態顯示下載中
                        embed = self.embed_manager.playing_embed(prev_song, is_looping=self.playlist_manager.loop, is_playing=False)
                        embed.set_field_at(0, name="狀態", value="下載中...", inline=False)
                        if self.player_message:
                            await self.player_message.edit(embed=embed, view=self.buttons_view)
                        # 下載新歌
                        song_info, file_path = await self.yt_dlp_manager.async_download(prev_song["url"])
                        
                        # 檢查下載結果，處理可能的錯誤
                        if not file_path and isinstance(song_info, dict) and song_info.get("success") is False:
                            # 取得錯誤資訊
                            error_type = song_info.get("error_type", "unknown")
                            display_message = song_info.get("display_message", "影片無法播放")
                            
                            logger.warning(f"按鈕動作 - 歌曲無法下載: {prev_song['title']} - {display_message}")
                            
                            # 使用通用的錯誤處理方法
                            has_songs = await self._handle_song_playback_error(prev_song, display_message, current_song_index)
                            
                            # 如果還有歌曲，使用 on_song_end 而不是重試上一首
                            if has_songs:
                                await self.on_song_end()
                            return
                        
                        # 一般下載失敗
                        elif not song_info or not file_path:
                            # 使用通用的錯誤處理方法處理未知錯誤
                            has_songs = await self._handle_song_playback_error(prev_song, "未知原因", current_song_index)
                            
                            # 如果還有歌曲，使用 on_song_end 而不是重試上一首
                            if has_songs:
                                await self.on_song_end()
                            return
                        
                        # 下載成功
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
                self.manual_disconnect = True  # 標記為手動斷開連接
                embed = self.embed_manager.clear_playlist_embed()
                await self.player_message.edit(embed=embed, view=None)
                await self.cleanup_resources()
                return
            # 更新嵌入和按鈕狀態
            embed = self.embed_manager.playing_embed(
                current_song,
                is_looping=self.playlist_manager.loop,
                is_playing=is_playing,
                current_time=0 if action in ("next", "previous") else current_status["current_sec"]
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
        """
        try:
            # 如果沒有播放控制器或者沒有在播放，直接跳過
            if not self.player_controller or not self.player_controller.is_playing:
                return

            # 獲取當前狀態
            current_status = self.player_controller.get_current_status()
            current_song = self.playlist_manager.get_current_song()
            
            # 如果沒有當前歌曲，跳過更新
            if not current_song:
                logger.warning("更新嵌入時發現目前無歌曲，跳過嵌入更新")
                return

            # 生成新的嵌入訊息
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
                
        except Exception as e:
            logger.error(f"更新播放嵌入時發生錯誤：{str(e)}")
            logger.exception(e)  # 輸出完整例外

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.id != self.bot.user.id:
            return
        if before.channel is not None and after.channel is None:
            if not self.manual_disconnect:
                logger.warning("Bot 被動斷線，啟動自動重連任務")
                self.reconnect_attempts = 0
                if not self.voice_reconnect_loop.is_running():
                    self.voice_reconnect_loop.start()

    def get_next_reconnect_delay(self):
        """
        根據重連嘗試次數計算下一次重連的延遲時間
        第5次後開始指數增長延遲
        """
        if self.reconnect_attempts < self.reconnect_backoff_threshold:
            return 15  # 前5次固定15秒
        
        # 超過閾值後，延遲時間逐漸增加：15 -> 30 -> 60 -> 120 -> 240 -> 最大300秒
        backoff_factor = self.reconnect_attempts - self.reconnect_backoff_threshold + 1
        delay = min(15 * (2 ** backoff_factor), 300)  # 最大延遲5分鐘
        return delay

    @tasks.loop(seconds=15)
    async def voice_reconnect_loop(self):
        try:
            if self.reconnect_attempts >= self.max_reconnect_attempts:
                logger.error("自動重連已達最大次數，停止重連並通知使用者")
                self.voice_reconnect_loop.stop()
                if self.player_message:
                    embed = self.embed_manager.error_embed("❌ 無法自動重連語音頻道，請手動重新啟動播放器或檢查語音伺服器狀態。")
                    await self.player_message.edit(embed=embed, view=None)
                await self.cleanup_resources()
                return
                
            # 檢查播放控制器是否已初始化
            if self.player_controller is None:
                logger.error("播放控制器尚未初始化，延遲重連嘗試")
                return
                
            voice_client = getattr(self.player_controller, 'voice_client', None)
            if voice_client and voice_client.is_connected():
                logger.info("已成功自動重連，停止重連任務")
                # 額外檢查語音客戶端是否真正可用
                try:
                    # 確認語音客戶端確實在正確的頻道中
                    if voice_client.channel.id == self.last_voice_channel.id:
                        logger.info(f"語音連接確認: 已連接至正確的頻道 ({voice_client.channel.name})")
                    else:
                        logger.warning(f"語音連接警告: 已連接但頻道不符 (當前: {voice_client.channel.name}, 預期: {self.last_voice_channel.name})")
                except Exception as e:
                    logger.warning(f"檢查語音連接時出錯: {e}")
                    
                self.voice_reconnect_loop.stop()
                return
                
            logger.info(f"自動重連語音頻道（第 {self.reconnect_attempts+1}/{self.max_reconnect_attempts} 次）")
            # 狀態顯示於嵌入
            if self.player_message:
                current_song = self.playlist_manager.get_current_song()
                if current_song:
                    embed = self.embed_manager.playing_embed(current_song, is_looping=self.playlist_manager.loop, is_playing=False)
                    embed.set_field_at(0, name="狀態", value=f"重新連線至語音頻道中 (第{self.reconnect_attempts+1}/{self.max_reconnect_attempts}次)...", inline=False)
                    await self.player_message.edit(embed=embed, view=self.buttons_view)
            
            await self.attempt_reconnect()
            self.reconnect_attempts += 1
            
            # 動態調整下一次重連間隔
            if self.reconnect_attempts < self.max_reconnect_attempts:
                next_delay = self.get_next_reconnect_delay()
                logger.info(f"下一次重連將在 {next_delay} 秒後進行")
                
                # 取消當前任務，使用新間隔重新啟動
                self.voice_reconnect_loop.stop()
                self.voice_reconnect_loop.change_interval(seconds=next_delay)
                self.voice_reconnect_loop.start()
                
        except Exception as e:
            logger.error(f"自動重連任務執行時發生錯誤: {e}")
            logger.exception(e)  # 輸出完整堆疊追蹤

    async def attempt_reconnect(self):
        """
        嘗試重新連接到上次的語音頻道
        """
        try:
            # 如果沒有記錄上次的語音頻道，無法重連
            if not self.last_voice_channel:
                logger.error("無法重新連接：未記錄上次的語音頻道")
                return
                
            logger.info(f"嘗試重新連接至語音頻道: {self.last_voice_channel.name}")
            
            # 檢查當前語音狀態
            if self.player_controller is None:
                logger.error("無法重新連接：播放控制器未初始化")
                return
                
            # 獲取當前語音連接狀態
            current_voice_client = getattr(self.player_controller, 'voice_client', None)
            if current_voice_client:
                connection_status = "已連接" if current_voice_client.is_connected() else "已斷開"
                logger.info(f"當前語音連接狀態: {connection_status}")
                guild_connected = getattr(current_voice_client, 'guild', None)
                if guild_connected:
                    logger.info(f"當前連接伺服器: {guild_connected.name}")
            
            # 檢查目標頻道狀態
            try:
                channel_status = f"可見: {self.last_voice_channel.permissions_for(self.last_voice_channel.guild.me).view_channel}"
                channel_status += f", 可連接: {self.last_voice_channel.permissions_for(self.last_voice_channel.guild.me).connect}"
                logger.info(f"目標頻道狀態: {channel_status}")
            except Exception as e:
                logger.error(f"檢查頻道權限時出錯: {e}")
            
            # 嘗試連接語音頻道
            voice_client = await self.last_voice_channel.connect()
            await self.player_controller.set_voice_client(voice_client)
            
            # 如果有當前歌曲，嘗試恢復播放
            current_song = self.playlist_manager.get_current_song()
            if current_song:
                logger.info(f"嘗試恢復播放歌曲: {current_song['title']}")
                # 檢查歌曲檔案是否存在
                opus_path = os.path.join("./temp/music", f"{current_song['id']}.opus")
                if os.path.exists(opus_path):
                    logger.info(f"找到歌曲檔案: {opus_path}")
                else:
                    logger.warning(f"找不到歌曲檔案: {opus_path}，將嘗試重新下載")
                
                await self.player_controller.play_song(current_song["id"])
                
                # 更新播放器訊息
                if self.player_message:
                    embed = self.embed_manager.playing_embed(
                        current_song,
                        is_looping=self.playlist_manager.loop,
                        is_playing=True
                    )
                    await self.update_buttons_view()
                    await self.player_message.edit(embed=embed, view=self.buttons_view)
                    
            logger.info("成功重新連接並恢復播放")
            
        except discord.ClientException as e:
            error_msg = str(e)
            logger.error(f"重新連接語音頻道失敗 (ClientException): {error_msg}")
            
            # 針對特定錯誤提供更詳細的診斷
            if "Already connected to a voice channel" in error_msg:
                logger.error("診斷: Bot 可能已在其他語音頻道中，但狀態未正確更新")
                try:
                    # 嘗試查找當前連接的頻道
                    for guild in self.bot.guilds:
                        voice_client = guild.voice_client
                        if voice_client and voice_client.is_connected():
                            logger.info(f"找到現有的語音連接: 伺服器={guild.name}, 頻道={voice_client.channel.name}")
                            # 嘗試使用現有連接
                            await self.player_controller.set_voice_client(voice_client)
                            logger.info("已重用現有的語音連接")
                            return
                except Exception as inner_e:
                    logger.error(f"嘗試查找現有連接時出錯: {inner_e}")
                    
        except discord.errors.OpusNotLoaded as e:
            logger.error(f"Opus 庫未正確載入: {e}")
            logger.error("診斷: 這可能是系統缺少 libopus 庫或其路徑設定錯誤")
            
        except TimeoutError:
            logger.error("與語音伺服器連接超時")
            logger.error("診斷: Discord 語音伺服器可能不穩定或網路連接問題")
            
        except Exception as e:
            logger.error(f"重新連接過程中發生未知錯誤: {e}")
            logger.exception(e)  # 輸出完整的堆疊追蹤
            
            # 診斷網路狀態
            try:
                import socket
                try:
                    # 嘗試與 Discord 語音伺服器建立連接測試
                    socket.create_connection(("discord.com", 443), timeout=5)
                    logger.info("網路診斷: 可以連接到 Discord 主機")
                except Exception as net_e:
                    logger.error(f"網路診斷: 無法連接到 Discord 主機 - {net_e}")
            except ImportError:
                logger.warning("無法進行網路診斷: socket 模組不可用")

    async def _handle_song_playback_error(self, song, display_message, song_index):
        """
        處理歌曲播放錯誤的通用邏輯
        :param song: dict, 歌曲資訊
        :param display_message: str, 要顯示的錯誤訊息
        :param song_index: int, 歌曲索引
        :return: bool, 是否成功處理（False 表示播放清單已空）
        """
        # 先備份歌曲ID，用於安全檢查
        song_id = song.get('id', '')
        
        # 先從播放清單中移除該歌曲，避免在等待期間用戶能夠回到問題歌曲
        # 優先通過ID移除，失敗則嘗試通過索引移除，確保雙重保障
        logger.info(f"立即移除問題歌曲: {song['title']} (索引: {song_index}, ID: {song_id})")
        
        if song_id:
            self.playlist_manager.remove_by_id(song_id)
        else:
            # 如果沒有ID，退回到通過索引移除
            self.playlist_manager.remove(song_index)
        
        # 更新嵌入訊息顯示錯誤
        embed = self.embed_manager.playing_embed(song, is_looping=self.playlist_manager.loop, is_playing=False)
        embed.set_field_at(
            0, 
            name="狀態", 
            value=f"由於影片有 {display_message} 的關係無法播放\n將於5秒後自動切換至下一首", 
            inline=False
        )
        
        # 更新按鈕狀態，避免用戶點擊上一首回到已移除的歌曲
        await self.update_buttons_view()
        
        if self.player_message:
            await self.player_message.edit(embed=embed, view=self.buttons_view)
        
        # 等待5秒
        await asyncio.sleep(5)
        
        # 如果移除後播放清單為空，更新UI
        if not self.playlist_manager.playlist:
            logger.debug("移除問題歌曲後播放清單為空")
            self.player_controller.is_playing = False
            self.player_controller.current_song = None
            embed = self.embed_manager.error_embed("播放清單中無音樂")
            embed.set_author(name="")
            embed.description = "無音樂可播放"
            embed.set_field_at(0, name="狀態", value="請透過指令\n[音樂-新增音樂到播放清單]\n來新增音樂", inline=False)
            
            # 禁用所有按鈕
            await self.buttons_view.update_buttons({
                "play_pause": {"disabled": True},
                "next": {"disabled": True},
                "previous": {"disabled": True},
                "loop": {"disabled": True}
            })
            
            if self.player_message:
                await self.player_message.edit(embed=embed, view=self.buttons_view)
            return False
        
        return True

async def setup(bot):
    await bot.add_cog(MusicPlayerCog(bot))