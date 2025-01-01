import discord
import asyncio
import os
from typing import Optional, Dict, Callable


class PlayerController:
    def __init__(self, ffmpeg_path, music_dir, loop: asyncio.AbstractEventLoop, on_song_end: Callable[[], asyncio.Future]):
        """
        初始化 PlayerController
        :param ffmpeg_path: str，FFmpeg 的可執行檔路徑
        :param music_dir: str，音樂檔案的資料夾
        :param loop: asyncio.AbstractEventLoop，事件循環
        :param on_song_end: Callable，當歌曲播放完畢時執行的回調函數
        """
        if not os.path.exists(ffmpeg_path):
            raise FileNotFoundError(f"FFmpeg 不存在於指定路徑: {ffmpeg_path}")
        if not os.path.isdir(music_dir):
            raise NotADirectoryError(f"音樂資料夾不存在或不是目錄: {music_dir}")

        self.ffmpeg_path = ffmpeg_path
        self.music_dir = music_dir.rstrip("/")
        self.voice_client: Optional[discord.VoiceClient] = None
        self.current_song = None
        self.is_playing = False
        self.is_paused = False
        self.start_time = None  # 播放開始時間
        self.paused_time = 0  # 累計暫停時間
        self.loop = loop  # 傳入的事件循環
        self.on_song_end = on_song_end  # 播放結束的回調函數

    async def set_voice_client(self, voice_client: discord.VoiceClient):
        self.voice_client = voice_client

    async def play_song(self, song_id: str):
        """
        播放指定歌曲
        :param song_id: str，歌曲 ID
        """
        if not self.voice_client or not self.voice_client.is_connected():
            raise RuntimeError("未連接語音頻道，無法播放音樂")

        # 確定檔案路徑
        file_path = None
        for extension in [".webm", ".mp3", ".m4a"]:
            potential_path = os.path.join(self.music_dir, f"{song_id}{extension}")
            if os.path.exists(potential_path):
                file_path = potential_path
                break

        if not file_path:
            raise FileNotFoundError(f"找不到對應的音樂檔案：{song_id}")

        self.current_song = {"id": song_id, "file_path": file_path}
        self.is_playing = True
        self.is_paused = False
        self.start_time = asyncio.get_running_loop().time()  # 記錄開始播放的時間
        self.paused_time = 0  # 重置暫停時間

        audio_source = discord.FFmpegPCMAudio(
            executable=self.ffmpeg_path,
            source=file_path,
            options="-vn"
        )

        def after_playback(error):
            # 確保協程調度在正確的事件循環中
            self.loop.call_soon_threadsafe(asyncio.create_task, self.on_song_end())

        self.voice_client.play(audio_source, after=after_playback)

    async def stop(self):
        """
        停止播放並重置狀態
        """
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
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
            self.paused_time += asyncio.get_running_loop().time() - self.start_time  # 累加暫停時的進度

    async def resume(self):
        """
        恢復播放
        """
        if self.voice_client and self.is_paused:
            self.voice_client.resume()
            self.is_paused = False
            self.start_time = asyncio.get_running_loop().time()  # 記錄恢復播放的時間

    def get_current_status(self) -> Dict[str, Optional[object]]:
        """
        獲取播放器當前狀態
        :return: Dict[str, Optional[object]]，包含播放狀態資訊
        """
        current_time = 0
        if self.is_playing and not self.is_paused and self.start_time:
            current_time = asyncio.get_running_loop().time() - self.start_time + self.paused_time
        elif self.is_paused:
            current_time = self.paused_time  # 如果暫停，返回累計播放時間

        return {
            "is_playing": self.is_playing,
            "is_paused": self.is_paused,
            "song_id": self.current_song["id"] if self.current_song else None,
            "current_sec": int(current_time)
        }
