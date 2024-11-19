import discord
from discord.ext import commands, tasks
from discord import app_commands
import yt_dlp
import random
import platform
import os
import asyncio
from loguru import logger
import time
from module.ffmpeg.checker import async_check_and_download_ffmpeg

# 設定 ffmpeg 的路徑
FFMPEG_PATH = "module/ffmpeg/Windows/ffmpeg.exe" if platform.system() == "Windows" else "module/ffmpeg/Linux/ffmpeg"

# 播放清單管理
class PlaylistManager:
    def __init__(self):
        self.playlist = []
        self.current_index = 0
        self.is_repeat = False
        self.play_mode = "順序播放"

    def add_song(self, song):
        self.playlist.append(song)

    def get_current_song(self):
        if self.playlist and 0 <= self.current_index < len(self.playlist):
            return self.playlist[self.current_index]
        return None

    def get_next_index(self):
        if self.play_mode == "順序播放":
            self.current_index += 1
            if self.current_index >= len(self.playlist):
                if self.is_repeat:
                    self.current_index = 0
                else:
                    self.current_index = len(self.playlist) - 1  # 調整為最後一個有效索引
        elif self.play_mode == "隨機播放":
            self.current_index = random.choice(range(len(self.playlist)))
        return self.current_index

    def get_previous_index(self):
        if self.current_index > 0:
            self.current_index -= 1
        else:
            self.current_index = len(self.playlist) - 1 if self.is_repeat else 0
        return self.current_index

    def clear(self):
        self.playlist.clear()
        self.current_index = 0

# EmbedManager 嵌入訊息管理
class EmbedManager:
    def __init__(self, player):
        self.player = player
        self.current_message = None
        self.last_update_time = 0  # 上次更新時間

    async def update_embed(self, interaction=None, force_update=False):
        current_time = time.time()
        if not force_update and current_time - self.last_update_time < 10:
            return
        self.last_update_time = current_time

        # 準備嵌入訊息內容
        if not self.player.voice_client or not self.player.voice_client.is_connected():
            logger.warning("播放器未啟動，無法更新嵌入訊息。")
            return

        # 生成嵌入訊息
        embed = self._generate_embed()
        view = MusicControls(self.player)
        view.update_buttons()

        # 優先使用現有訊息進行更新
        if self.current_message:
            try:
                await self.current_message.edit(embed=embed, view=view)
                return
            except discord.HTTPException as e:
                logger.warning(f"嵌入訊息更新失敗：{e}")

        # 若無法更新現有訊息，嘗試綁定互動訊息
        if interaction:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, view=view)
            self.current_message = await interaction.original_response()


    def _generate_embed(self):
        song = self.player.playlist_manager.get_current_song()

        # 確認播放器狀態
        if self.player.voice_client is None or song is None:
            # 播放器未啟動或播放清單為空時顯示
            return discord.Embed(description="目前沒有播放中的音樂。", color=discord.Color.red())

        # 正常生成嵌入訊息
        current_time = time.time()
        elapsed = int(current_time - self.player.start_time)
        elapsed = min(elapsed, song['duration'])

        embed = discord.Embed(color=discord.Color.blurple())
        embed.set_author(name=song['uploader'])
        embed.description = f"{self.player.playlist_manager.current_index + 1}. [{song['title']}]({song['url']})"
        embed.add_field(
            name="狀態",
            value=f"{'正在播放 ▶️' if self.player.voice_client.is_playing() else '已暫停 ⏸️'}\n"
                f"{elapsed // 60}:{elapsed % 60:02d} {self.create_progress_bar(elapsed, song['duration'])} {song['duration'] // 60}:{song['duration'] % 60:02d}",
            inline=False
        )
        embed.set_thumbnail(url=song['thumbnail'])
        embed.set_footer(
            text=f"播放模式: {self.player.playlist_manager.play_mode} | 循環播放: {'開啟' if self.player.playlist_manager.is_repeat else '關閉'}"
        )
        return embed

    @staticmethod
    def create_progress_bar(elapsed, total, length=20):
        """
        建立進度條。
        """
        progress = int(length * elapsed / total) if total else 0
        bar = '▇' * progress + '—' * (length - progress)
        return f"`{bar}`"

# 按鈕互動控制
class MusicControls(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=None)
        self.player = player

    def update_buttons(self):
        current_song = self.player.playlist_manager.get_current_song()
        playlist_length = len(self.player.playlist_manager.playlist)

        if current_song:
            is_playing = self.player.voice_client.is_playing() if self.player.voice_client else False
            self.play_pause_button.emoji = "⏸️" if is_playing else "▶️"
            self.toggle_play_mode_button.emoji = "🔁" if self.player.playlist_manager.play_mode == "順序播放" else "🔀"
            self.toggle_repeat_button.style = discord.ButtonStyle.success if self.player.playlist_manager.is_repeat else discord.ButtonStyle.secondary
            self.play_pause_button.disabled = False
            
            # 如果只有一首音樂，禁用「上一首」和「下一首」按鈕
            self.previous_button.disabled = playlist_length <= 1
            self.next_button.disabled = playlist_length <= 1

            self.toggle_play_mode_button.disabled = False
            self.toggle_repeat_button.disabled = False
        else:
            self.play_pause_button.disabled = True
            self.previous_button.disabled = True
            self.next_button.disabled = True
            self.toggle_play_mode_button.disabled = True
            self.toggle_repeat_button.disabled = True
    
    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.player.play_previous(interaction)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.primary)
    async def play_pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.player.toggle_play_pause(interaction)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.player.play_next(interaction)

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.success)
    async def toggle_play_mode_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.player.toggle_play_mode(interaction)

    @discord.ui.button(emoji="🔄", style=discord.ButtonStyle.success)
    async def toggle_repeat_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.player.toggle_repeat(interaction)

    @discord.ui.button(emoji="🚪", label="離開頻道", style=discord.ButtonStyle.danger)
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.player.leave_voice_channel(interaction)

class MusicPlayer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.playlist_manager = PlaylistManager()
        self.embed_manager = EmbedManager(self)
        self.voice_client = None
        self.start_time = time.time()
        self.download_folder = "music_downloads"
        os.makedirs(self.download_folder, exist_ok=True)
        self.update_task = self.progress_updater  # 正確指向 tasks.loop 實例  # 用於定期更新嵌入訊息的任務
        self.is_stopping = False
        self.current_song_id = None  # 當前播放歌曲的唯一 ID

    @staticmethod
    async def check_ffmpeg():
        """檢查並下載 FFmpeg"""
        from module.ffmpeg.checker import async_check_and_download_ffmpeg

        logger.info("[MusicPlayer] 檢查並下載 FFmpeg")
        status = await async_check_and_download_ffmpeg()
        if status != 0:
            logger.error("[MusicPlayer] FFmpeg 檢查失敗")
            raise RuntimeError("[MusicPlayer] FFmpeg 檢查失敗，無法啟動音樂功能")
        logger.info("[MusicPlayer] FFmpeg 檢查完成")

    def clear_downloads(self):
        for file in os.listdir(self.download_folder):
            file_path = os.path.join(self.download_folder, file)
            if os.path.isfile(file_path):
                os.remove(file_path)

    async def join_voice_channel(self, interaction):
        try:
            if not interaction.user.voice or not interaction.user.voice.channel:
                await interaction.followup.send(
                    embed=discord.Embed(description="請先加入語音頻道。", color=discord.Color.red()), ephemeral=True
                )
                return False
            channel = interaction.user.voice.channel
            if not self.voice_client or not self.voice_client.is_connected():
                self.voice_client = await channel.connect()
            elif self.voice_client.channel != channel:
                await self.voice_client.move_to(channel)
            return True
        except Exception as e:
            logger.error(f"加入語音頻道錯誤: {e}")
            await interaction.followup.send(
                embed=discord.Embed(description="無法加入語音頻道。", color=discord.Color.red()), ephemeral=True
            )
            return False

    async def play_handler(self, interaction=None):
        song = self.playlist_manager.get_current_song()
        if not song:
            if interaction:
                await interaction.followup.send("播放清單為空。", ephemeral=True)
            return

        # 確保歌曲已下載
        if not song.get('filepath') or not os.path.exists(song['filepath']):
            logger.info(f"歌曲未下載或檔案不存在，開始下載: {song.get('url')}")
            downloaded_song = await self.download_song(song['url'])
            if not downloaded_song or not downloaded_song.get('filepath'):
                logger.error("歌曲下載失敗，無法播放。")
                if interaction:
                    await interaction.followup.send("無法播放歌曲，下載失敗。", ephemeral=True)
                return
            # 更新歌曲資訊
            song.update(downloaded_song)

        # 初始化音訊來源
        source = discord.FFmpegPCMAudio(
            song['filepath'],
            executable=FFMPEG_PATH,
            options="-vn -loglevel quiet"
        )

        # 停止當前播放，開始新的播放
        if self.voice_client.is_playing():
            self.is_stopping = True
            self.voice_client.stop()

        self.voice_client.play(
            source,
            after=lambda e: asyncio.run_coroutine_threadsafe(self.auto_play_next(), self.bot.loop)
        )
        self.start_time = time.time()

        # 確保進度更新任務啟動
        if not self.progress_updater.is_running():
            self.progress_updater.start()

        await self.embed_manager.update_embed(interaction, force_update=True)

    @tasks.loop(seconds=15)
    async def progress_updater(self):
        """
        使用 tasks.loop 控制進度條更新。
        """
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            logger.debug("進度條更新中...")
            await self.embed_manager.update_embed(force_update=True)
        else:
            logger.debug("播放器不在活動中，停止進度更新。")
            self.progress_updater.stop()  # 停止任務以節省資源

    @progress_updater.before_loop
    async def before_progress_updater(self):
        """
        在進度更新開始前執行的操作。
        """
        logger.debug("準備啟動進度更新任務...")

    @progress_updater.error
    async def progress_updater_error(self, error):
        """
        進度更新任務中的錯誤處理。
        """
        logger.error(f"進度更新任務發生錯誤：{error}")

    async def auto_play_next(self):
        """
        自動播放下一首歌曲。
        """
        if self.is_stopping:
            logger.debug("播放器已停止，不進行自動播放。")
            return  # 如果是手動停止，不自動播放下一首

        playlist_length = len(self.playlist_manager.playlist)
        if playlist_length == 0:
            logger.debug("播放清單為空，無法自動播放下一首。")
            return

        if self.playlist_manager.play_mode == "順序播放":
            if self.playlist_manager.current_index < playlist_length - 1:
                self.playlist_manager.current_index += 1
                logger.debug(f"順序播放下一首，索引更新為：{self.playlist_manager.current_index}")
            elif self.playlist_manager.is_repeat:
                self.playlist_manager.current_index = 0
                logger.debug("到達清單末尾，循環到第一首。")
            else:
                logger.debug("順序播放完成，無後續歌曲，停止播放。")
                if self.update_task:
                    self.update_task.cancel()
                await self.embed_manager.update_embed(force_update=True)
                return
        elif self.playlist_manager.play_mode == "隨機播放":
            self.playlist_manager.current_index = random.randint(0, playlist_length - 1)
            logger.debug(f"隨機播放下一首，索引更新為：{self.playlist_manager.current_index}")

        # 播放下一首
        await self.play_handler()

    # 音樂-啟動播放器
    @app_commands.command(name="音樂-啟動播放器", description="啟動播放器，播放清單中的音樂或直接新增並播放一首音樂")
    @app_commands.rename(url="youtube網址")
    async def start_player(self, interaction: discord.Interaction, url: str = None):
        """
        啟動播放器：
        - 若播放清單為空，允許用戶提供一首音樂 URL。
        - 若播放清單不為空，直接啟動播放。
        """
        # 檢查播放器是否已啟動：以語音客戶端狀態為準
        if self.voice_client and self.voice_client.is_connected():
            await interaction.response.send_message(
                embed=discord.Embed(description="播放器已啟動，請勿重複執行指令。", color=discord.Color.orange()),
                ephemeral=True
            )
            return

        # 發送「請稍候」訊息
        await interaction.response.send_message(
            embed=discord.Embed(description="請稍候...", color=discord.Color.yellow())
        )
        self.embed_manager.current_message = await interaction.original_response()  # 綁定初始訊息

        # 檢查播放清單和 URL
        if not self.playlist_manager.playlist and not url:
            await interaction.followup.send(
                embed=discord.Embed(description="播放清單為空，請提供音樂網址來啟動播放器。", color=discord.Color.red()),
                ephemeral=True
            )
            return

        # 嘗試進入語音頻道
        if not await self.join_voice_channel(interaction):
            return

        # 如果播放清單為空，新增並播放提供的 URL
        if not self.playlist_manager.playlist:
            song = await self.extract_song_info(url)
            if song:
                self.playlist_manager.add_song(song)
                self.playlist_manager.current_index = 0
                await self.play_handler(interaction)
            else:
                await interaction.followup.send(
                    embed=discord.Embed(description="獲取歌曲資訊時發生錯誤。", color=discord.Color.red()), ephemeral=True
                )
        else:
            # 若播放清單已有歌曲，直接啟動播放
            await self.play_handler(interaction)

    # 音樂-新增至播放清單
    @app_commands.command(name="音樂-新增至播放清單", description="新增音樂至播放清單")
    @app_commands.rename(url="youtube網址")
    async def add_to_playlist(self, interaction: discord.Interaction, url: str):
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=discord.Embed(description="請稍候...", color=discord.Color.yellow()))
        self.embed_manager.current_message = await interaction.original_response()

        song = await self.extract_song_info(url)
        if song:
            self.playlist_manager.add_song(song)

            # 確保 current_index 在有效範圍內
            if self.playlist_manager.current_index >= len(self.playlist_manager.playlist):
                self.playlist_manager.current_index = len(self.playlist_manager.playlist) - 1

            # 更新嵌入訊息
            await self.embed_manager.current_message.edit(
                embed=discord.Embed(description=f"已新增至播放清單：[{song['title']}]({song['url']})", color=discord.Color.green())
            )

            # 若播放器啟動，更新嵌入訊息
            if self.voice_client:
                await self.embed_manager.update_embed(force_update=True)
        else:
            await self.embed_manager.current_message.edit(
                embed=discord.Embed(description="新增至播放清單時發生錯誤。", color=discord.Color.red())
            )


    async def extract_song_info(self, url):
        """
        提取歌曲的資訊，不下載音樂。
        """
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'quiet': True,
                'skip_download': True,  # 僅提取資訊，不下載
            }
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, self._extract_info_sync, url, ydl_opts)
            if info:
                song = {
                    'title': info['title'],
                    'duration': info['duration'],
                    'thumbnail': info.get('thumbnail', ''),
                    'filepath': None,  # 尚未下載
                    'url': url,
                    'uploader': info.get('uploader', '未知上傳者'),
                    'id': info.get('id'),
                    'ext': info.get('ext'),
                }
                return song
            else:
                return None
        except Exception as e:
            logger.error(f"提取歌曲資訊錯誤: {e}")
            return None

    def _extract_info_sync(self, url, ydl_opts):
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    async def download_song(self, url):
        """
        非同步下載歌曲，避免阻塞。
        """
        try:
            temp_filename = os.path.join(self.download_folder, '%(id)s.%(ext)s')
            ydl_opts = {
                'format': 'bestaudio/best',
                'ffmpeg_location': FFMPEG_PATH,
                'quiet': True,
                'outtmpl': temp_filename,
                'fragment_retries': 10,
                'http_chunk_size': 10 * 1024 * 1024,  # 每片段大小 10MB
            }

            loop = asyncio.get_event_loop()
            info, filepath = await loop.run_in_executor(None, self._download_song_sync, url, ydl_opts)

            if info and filepath and os.path.exists(filepath):
                song = {
                    'title': info['title'],
                    'duration': info['duration'],
                    'thumbnail': info.get('thumbnail', ''),
                    'filepath': filepath,
                    'url': url,
                    'uploader': info.get('uploader', '未知上傳者'),
                }
                logger.info(f"歌曲已下載：{song['title']} (路徑: {song['filepath']})")
                return song
            else:
                logger.error("下載歌曲失敗。")
                return None
        except Exception as e:
            logger.error(f"下載歌曲時發生錯誤：{e}")
            return None

    def _download_song_sync(self, url, ydl_opts):
        """
        同步下載方法，供 run_in_executor 使用。
        """
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
            return info, filepath

    # 播放上一首
    async def play_previous(self, interaction):
        self.playlist_manager.get_previous_index()
        await self.play_handler(interaction)

    # 播放下一首
    async def play_next(self, interaction):
        self.playlist_manager.get_next_index()
        if self.playlist_manager.current_index < len(self.playlist_manager.playlist):
            await self.play_handler(interaction)
        else:
            await interaction.followup.send("已經是最後一首歌曲。", ephemeral=True)
            # 重置 current_index 到最後一首有效歌曲
            self.playlist_manager.current_index = len(self.playlist_manager.playlist) - 1

    # 切換播放/暫停
    async def toggle_play_pause(self, interaction):
        if self.voice_client.is_playing():
            self.voice_client.pause()
        elif self.voice_client.is_paused():
            self.voice_client.resume()
        else:
            await self.play_handler(interaction)
        await self.embed_manager.update_embed(interaction, force_update=True)

    # 切換播放模式
    async def toggle_play_mode(self, interaction):
        self.playlist_manager.play_mode = "隨機播放" if self.playlist_manager.play_mode == "順序播放" else "順序播放"
        await self.embed_manager.update_embed(interaction, force_update=True)

    # 切換循環播放
    async def toggle_repeat(self, interaction):
        self.playlist_manager.is_repeat = not self.playlist_manager.is_repeat
        await self.embed_manager.update_embed(interaction, force_update=True)

    async def leave_voice_channel(self, interaction):
        if self.voice_client:
            self.is_stopping = True
            self.voice_client.stop()
            await self.voice_client.disconnect()
            self.voice_client = None

            # 清空播放清單
            self.playlist_manager.clear()

            # 停止進度更新任務
            if self.update_task.is_running():  # 確保是 tasks.loop
                self.update_task.cancel()

            # 清理暫存音樂檔案
            self.clear_downloads()

            # 更新嵌入訊息，移除所有按鈕，並顯示離開狀態
            embed = discord.Embed(
                title="已離開語音頻道",
                description=f"**{interaction.user.display_name}** 讓機器人離開了語音頻道。",
                color=discord.Color.red()
            )
            view = discord.ui.View()  # 空白 View，移除按鈕

            if self.embed_manager.current_message:
                await self.embed_manager.current_message.edit(embed=embed, view=view)
                self.embed_manager.current_message = None
            else:
                await interaction.response.send_message(embed=embed, view=view)

    # 查看播放清單
    @app_commands.command(name="音樂-查看播放清單", description="查看目前的播放清單")
    async def view_playlist(self, interaction: discord.Interaction):
        if not self.playlist_manager.playlist:
            await interaction.response.send_message(embed=discord.Embed(description="播放清單是空的。", color=discord.Color.red()), ephemeral=True)
            return
        description = "\n".join([f"{i + 1}. [{song['title']}]({song['url']})" for i, song in enumerate(self.playlist_manager.playlist)])
        await interaction.response.send_message(embed=discord.Embed(title="🎶 播放清單", description=description, color=discord.Color.blurple()), ephemeral=False)

    # 歌曲自動補全函數
    async def song_autocomplete(self, interaction: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=song['title'], value=str(i))
            for i, song in enumerate(self.playlist_manager.playlist)
            if current.lower() in song['title'].lower()
        ]

    # 移除特定歌曲
    @app_commands.command(name="音樂-移除播放清單特定音樂", description="從播放清單中刪除特定音樂")
    @app_commands.rename(index="要刪除的音樂")
    @app_commands.autocomplete(index=song_autocomplete)
    async def remove_song(self, interaction: discord.Interaction, index: str):
        try:
            idx = int(index)
            if idx < 0 or idx >= len(self.playlist_manager.playlist):
                await interaction.response.send_message("無效的選項。", ephemeral=True)
                return
            removed = self.playlist_manager.playlist.pop(idx)
            if idx == self.playlist_manager.current_index:
                if self.voice_client.is_playing():
                    self.is_stopping = True
                    self.voice_client.stop()
                if idx >= len(self.playlist_manager.playlist):
                    self.playlist_manager.current_index = 0
                await self.play_handler(interaction)
            elif idx < self.playlist_manager.current_index:
                self.playlist_manager.current_index -= 1
            await interaction.response.send_message(embed=discord.Embed(title="已刪除", description=f"[{removed['title']}]({removed['url']})", color=discord.Color.red()), ephemeral=False)
            await self.embed_manager.update_embed(interaction, force_update=True)
        except Exception as e:
            logger.error(f"移除歌曲錯誤: {e}")
            await interaction.response.send_message("移除歌曲時發生錯誤。", ephemeral=True)

    # 清空播放清單
    @app_commands.command(name="音樂-清空播放清單", description="清空播放清單")
    async def clear_playlist(self, interaction: discord.Interaction):
        # 清除播放清單
        self.playlist_manager.clear()

        # 停止播放
        if self.voice_client and self.voice_client.is_playing():
            self.is_stopping = True
            self.voice_client.stop()

        # 取消定期更新任務
        if self.update_task:
            self.update_task.cancel()
            self.update_task = None

        # 清除暫存音樂
        self.clear_downloads()

        # 重設播放器狀態
        self.voice_client = None
        self.start_time = None
        self.is_stopping = False

        # 更新嵌入訊息，顯示播放清單已清空
        await interaction.response.send_message(embed=discord.Embed(description="播放清單已清空。", color=discord.Color.green()), ephemeral=False)
        await self.embed_manager.update_embed(interaction, force_update=True)

    # 卸載時的清理
    async def cog_unload(self):
        # 確保已斷開語音連線
        if self.voice_client and self.voice_client.is_connected():
            self.voice_client.stop()
            await self.voice_client.disconnect()
        self.voice_client = None

        # 清除播放清單
        self.playlist_manager.clear()

        # 取消定期更新任務
        if self.update_task:
            self.update_task.cancel()
            self.update_task = None

        # 刪除暫存音樂檔案
        self.clear_downloads()

        # 重設所有變數
        self.start_time = None
        self.is_stopping = False
        self.embed_manager.current_message = None
        self.embed_manager.last_update_time = 0  # 清除嵌入訊息更新時間

        # 確保播放清單和狀態完全重置
        self.playlist_manager = PlaylistManager()
        self.embed_manager = EmbedManager(self)

        logger.info("[MusicPlayer] Cog 已卸載並重設所有屬性。")

async def setup(bot):
    music_player = MusicPlayer(bot)
    try:
        await music_player.check_ffmpeg()  # 檢查 FFmpeg
        await bot.add_cog(music_player)
        logger.info("[MusicPlayer] Cog 已成功載入")
    except RuntimeError as e:
        logger.error(f"[MusicPlayer] Cog 加載失敗：{e}")
        await bot.close()
