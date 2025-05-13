import discord
import asyncio
import os
from typing import Optional, Dict, Callable
from loguru import logger


class MusicPlayerController:
    def __init__(self, ffmpeg_path, music_dir, loop: asyncio.AbstractEventLoop, on_song_end: Callable[[], asyncio.Future]):
        """
        初始化 MusicPlayerController
        :param ffmpeg_path: str, FFmpeg 執行檔路徑
        :param music_dir: str, 音樂檔案資料夾
        :param loop: asyncio.AbstractEventLoop, 事件循環
        :param on_song_end: Callable, 歌曲播放完畢時的回調
        """
        if not os.path.exists(ffmpeg_path):
            logger.error(f"FFmpeg 不存在於指定路徑: {ffmpeg_path}")
            raise FileNotFoundError(f"FFmpeg 不存在於指定路徑: {ffmpeg_path}")
        if not os.path.isdir(music_dir):
            logger.error(f"音樂資料夾不存在或不是目錄: {music_dir}")
            raise NotADirectoryError(f"音樂資料夾不存在或不是目錄: {music_dir}")
        self.ffmpeg_path = ffmpeg_path
        self.music_dir = music_dir.rstrip("/")
        self.voice_client: Optional['discord.VoiceClient'] = None
        self.current_song = None
        self.is_playing = False
        self.is_paused = False
        self.start_time = None
        self.paused_time = 0
        self.loop = loop
        self.on_song_end = on_song_end
        logger.info(f"MusicPlayerController 初始化完成，音樂資料夾: {self.music_dir}")

    async def set_voice_client(self, voice_client):
        """
        設定 Discord 語音 client
        :param voice_client: discord.VoiceClient
        """
        self.voice_client = voice_client
        logger.info("已設定 voice_client")

    async def play_song(self, song_id: str):
        """
        播放指定歌曲
        :param song_id: str, 歌曲 ID
        """
        if not self.voice_client or not self.voice_client.is_connected():
            logger.error("未連接語音頻道，無法播放音樂")
            raise RuntimeError("未連接語音頻道，無法播放音樂")
        file_path = None
        for extension in [".webm", ".mp3", ".m4a"]:
            potential_path = os.path.join(self.music_dir, f"{song_id}{extension}")
            if os.path.exists(potential_path):
                file_path = potential_path
                break
        if not file_path:
            logger.error(f"找不到對應的音樂檔案：{song_id}")
            raise FileNotFoundError(f"找不到對應的音樂檔案：{song_id}")
        self.current_song = {"id": song_id, "file_path": file_path}
        self.is_playing = True
        self.is_paused = False
        self.start_time = asyncio.get_running_loop().time()
        self.paused_time = 0
        logger.info(f"開始播放歌曲: {song_id} ({file_path})")
        import discord
        audio_source = discord.FFmpegPCMAudio(
            executable=self.ffmpeg_path,
            source=file_path,
            options="-vn"
        )
        def after_playback(error):
            if error:
                logger.error(f"播放結束時發生錯誤: {error}")
            self.loop.call_soon_threadsafe(asyncio.create_task, self.on_song_end())
        self.voice_client.play(audio_source, after=after_playback)

    async def stop(self):
        """
        停止播放並重置狀態
        """
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
            logger.info("已停止播放")
        self.is_playing = False
        self.current_song = None
        self.start_time = None
        self.paused_time = 0

    async def pause(self):
        """
        暫停播放
        """
        if self.voice_client and self.voice_client.is_playing() and not self.is_paused:
            self.voice_client.pause()
            self.is_paused = True
            self.paused_time += asyncio.get_running_loop().time() - self.start_time
            logger.info("已暫停播放")

    async def resume(self):
        """
        恢復播放
        """
        if self.voice_client and self.is_paused:
            self.voice_client.resume()
            self.is_paused = False
            self.start_time = asyncio.get_running_loop().time()
            logger.info("已恢復播放")

    def get_current_status(self) -> Dict[str, Optional[object]]:
        """
        獲取播放器當前狀態
        :return: Dict[str, Optional[object]]
        """
        current_time = 0
        if self.is_playing and not self.is_paused and self.start_time:
            current_time = asyncio.get_running_loop().time() - self.start_time + self.paused_time
        elif self.is_paused:
            current_time = self.paused_time
        logger.debug(f"播放器狀態查詢: is_playing={self.is_playing}, is_paused={self.is_paused}, current_sec={int(current_time)}")
        return {
            "is_playing": self.is_playing,
            "is_paused": self.is_paused,
            "song_id": self.current_song["id"] if self.current_song else None,
            "current_sec": int(current_time)
        }
