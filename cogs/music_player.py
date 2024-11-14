import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import random
import platform
import os
import asyncio
from loguru import logger
import time

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
                    self.current_index = len(self.playlist)  # 超出範圍，表示播放完畢
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
        if not force_update and current_time - self.last_update_time < 15:
            return
        self.last_update_time = current_time

        # 建立嵌入訊息內容
        song = self.player.playlist_manager.get_current_song()
        if not song:
            embed = discord.Embed(description="目前沒有播放中的音樂。", color=discord.Color.red())
        else:
            song_index = self.player.playlist_manager.current_index + 1
            embed = discord.Embed(color=discord.Color.blurple())
            embed.set_author(name=song['uploader'])
            embed.description = f"{song_index}. [{song['title']}]({song['url']})"
            elapsed = int(current_time - self.player.start_time)
            elapsed = min(elapsed, song['duration'])
            progress = self.create_progress_bar(elapsed, song['duration'])
            status = "正在播放 ▶️" if self.player.voice_client.is_playing() else "已暫停 ⏸️"
            embed.add_field(
                name=status,
                value=f"{elapsed // 60}:{elapsed % 60:02d} {progress} {song['duration'] // 60}:{song['duration'] % 60:02d}",
                inline=False
            )
            embed.set_thumbnail(url=song['thumbnail'])
            embed.set_footer(
                text=f"播放模式: {self.player.playlist_manager.play_mode} | 循環播放: {'開啟' if self.player.playlist_manager.is_repeat else '關閉'}"
            )

        view = MusicControls(self.player)
        view.update_buttons()

        # 根據是否已存在 `current_message` 來更新或發送新訊息
        if self.current_message:
            try:
                await self.current_message.edit(embed=embed, view=view)
            except discord.HTTPException as e:
                logger.error(f"更新嵌入訊息時發生錯誤: {e}")
                # 若編輯失敗，嘗試重新獲取訊息
                if interaction and not interaction.response.is_done():
                    await interaction.response.send_message(embed=embed, view=view)
                    self.current_message = await interaction.original_response()
        elif interaction and not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, view=view)
            self.current_message = await interaction.original_response()

    def create_progress_bar(self, elapsed, total, length=20):
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

# 播放器主模組
class MusicPlayer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.playlist_manager = PlaylistManager()
        self.embed_manager = EmbedManager(self)
        self.voice_client = None
        self.start_time = time.time()
        self.download_folder = "music_downloads"
        os.makedirs(self.download_folder, exist_ok=True)
        self.update_task = None  # 用於定期更新嵌入訊息的任務
        self.is_stopping = False

    def clear_downloads(self):
        for file in os.listdir(self.download_folder):
            file_path = os.path.join(self.download_folder, file)
            if os.path.isfile(file_path):
                os.remove(file_path)

    async def join_voice_channel(self, interaction):
        try:
            if not interaction.user.voice or not interaction.user.voice.channel:
                await interaction.followup.send(embed=discord.Embed(description="請先加入語音頻道。", color=discord.Color.red()), ephemeral=True)
                return False
            channel = interaction.user.voice.channel
            if not self.voice_client or not self.voice_client.is_connected():
                self.voice_client = await channel.connect()
            elif self.voice_client.channel != channel:
                await self.voice_client.move_to(channel)
            return True
        except Exception as e:
            logger.error(f"加入語音頻道錯誤: {e}")
            await interaction.followup.send(embed=discord.Embed(description="無法加入語音頻道。", color=discord.Color.red()), ephemeral=True)
            return False

    async def play_song(self, interaction=None):
        song = self.playlist_manager.get_current_song()
        if not song:
            if interaction:
                await interaction.followup.send("播放清單為空。", ephemeral=True)
            return

        source = discord.FFmpegPCMAudio(
            song['filepath'],
            executable=FFMPEG_PATH,
            options="-vn -loglevel quiet"
        )

        def after(e):
            if e:
                logger.error(f"FFmpeg error: {e}")
            elif not self.is_stopping:
                asyncio.run_coroutine_threadsafe(self.auto_play_next(), self.bot.loop)
            self.is_stopping = False

        if self.voice_client.is_playing():
            self.is_stopping = True
            self.voice_client.stop()

        self.voice_client.play(source, after=after)
        self.start_time = time.time()

        # 啟動定期更新嵌入訊息的任務
        if self.update_task:
            self.update_task.cancel()
        self.update_task = self.bot.loop.create_task(self.update_progress())

        await self.embed_manager.update_embed(interaction, force_update=True)

    async def update_progress(self):
        try:
            while self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
                await self.embed_manager.update_embed(force_update=True)
                await asyncio.sleep(15)
        except asyncio.CancelledError:
            logger.info("進度更新任務已取消")
        except Exception as e:
            logger.error(f"更新進度時發生錯誤: {e}")

    async def auto_play_next(self):
        if self.playlist_manager.is_repeat:
            # 如果啟用循環播放，則繼續下一首
            self.playlist_manager.get_next_index()
            await self.play_song()
        else:
            # 非循環播放時，判斷是否播放到清單結尾
            if self.playlist_manager.current_index >= len(self.playlist_manager.playlist) - 1:
                # 停在清單的開頭，不自動播放
                self.playlist_manager.current_index = 0
                await self.embed_manager.update_embed(force_update=True)
                # 停止更新任務
                if self.update_task:
                    self.update_task.cancel()
            else:
                # 若不是最後一首，正常播放下一首
                self.playlist_manager.get_next_index()
                await self.play_song()

    # 播放或新增音樂指令
    @app_commands.command(name="音樂-播放或新增音樂", description="播放或新增音樂")
    @app_commands.rename(url="youtube網址")
    async def play_music(self, interaction: discord.Interaction, url: str):
        # 初始時發送「請稍候」訊息
        await interaction.response.send_message(
            embed=discord.Embed(description="請稍候...", color=discord.Color.yellow())
        )
        self.embed_manager.current_message = await interaction.original_response()  # 綁定初始訊息

        if not await self.join_voice_channel(interaction):
            return

        song = await self.download_song(interaction, url)
        if song:
            self.playlist_manager.add_song(song)
            if not self.voice_client.is_playing() and not self.voice_client.is_paused():
                self.playlist_manager.current_index = len(self.playlist_manager.playlist) - 1
                await self.play_song(interaction)
            else:
                await interaction.followup.send(
                    embed=discord.Embed(description=f"已新增至播放清單：[{song['title']}]({song['url']})", color=discord.Color.green())
                )
            await self.embed_manager.update_embed(interaction, force_update=True)  # 更新嵌入訊息
        else:
            await interaction.followup.send(
                embed=discord.Embed(description="下載歌曲時發生錯誤。", color=discord.Color.red()), ephemeral=True
            )

    async def download_song(self, interaction, url):
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'ffmpeg_location': FFMPEG_PATH,
                'quiet': True,
                'outtmpl': os.path.join(self.download_folder, '%(id)s.%(ext)s'),
                'fragment_retries': 10,  # 增加重試次數
                'http_chunk_size': 10 * 1024 * 1024  # 每片段大小 10MB
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                song = {
                    'title': info['title'],
                    'duration': info['duration'],
                    'thumbnail': info.get('thumbnail', ''),
                    'filepath': ydl.prepare_filename(info),  # 使用原始下載格式
                    'url': url,
                    'uploader': info.get('uploader', '未知上傳者')
                }
            return song
        except Exception as e:
            logger.error(f"下載歌曲錯誤: {e}")
            return None

    # 播放上一首
    async def play_previous(self, interaction):
        self.playlist_manager.get_previous_index()
        await self.play_song(interaction)

    # 播放下一首
    async def play_next(self, interaction):
        self.playlist_manager.get_next_index()
        if self.playlist_manager.current_index < len(self.playlist_manager.playlist):
            await self.play_song(interaction)
        else:
            await interaction.followup.send("已經是最後一首歌曲。", ephemeral=True)

    # 切換播放/暫停
    async def toggle_play_pause(self, interaction):
        if self.voice_client.is_playing():
            self.voice_client.pause()
        elif self.voice_client.is_paused():
            self.voice_client.resume()
        else:
            await self.play_song(interaction)
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
            self.playlist_manager.clear()
            
            # 停止定期更新任務
            if self.update_task:
                self.update_task.cancel()
            
            # 清除暫存音樂
            self.clear_downloads()

            # 更新嵌入訊息，移除所有按鈕，並顯示離開狀態
            embed = discord.Embed(title="已離開語音頻道", description=f"{interaction.user.display_name} 讓機器人離開了語音頻道。", color=discord.Color.red())
            view = discord.ui.View()  # 空白 View 移除所有按鈕
            
            if self.embed_manager.current_message:
                await self.embed_manager.current_message.edit(embed=embed, view=view)
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
                await self.play_song(interaction)
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
        
        logger.info("MusicPlayer Cog 已卸載並重設所有屬性。")


async def setup(bot):
    await bot.add_cog(MusicPlayer(bot))
