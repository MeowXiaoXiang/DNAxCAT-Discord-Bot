import discord
import asyncio
import os
import time
from typing import Optional, Dict, Callable, Any
from loguru import logger


class MusicPlayerController:
    """
    音樂播放控制器，負責與 Discord 音頻系統交互
    核心職責：
    - 播放、暫停、恢復、停止音樂
    - 提供播放狀態查詢
    - 管理語音客戶端連接
    """
    def __init__(self, ffmpeg_path, music_dir, loop: asyncio.AbstractEventLoop, on_song_end: Callable[[], asyncio.Future]):
        """
        初始化 MusicPlayerController
        :param ffmpeg_path: str, FFmpeg 執行檔路徑
        :param music_dir: str, 音樂檔案資料夾
        :param loop: asyncio.AbstractEventLoop, 事件循環
        :param on_song_end: Callable, 歌曲播放完畢時的回調
        """
        # 檢查 FFmpeg 路徑
        if not os.path.exists(ffmpeg_path):
            logger.error(f"FFmpeg 不存在於指定路徑: {ffmpeg_path}")
            raise FileNotFoundError(f"FFmpeg 不存在於指定路徑: {ffmpeg_path}")
        
        # 檢查音樂目錄
        if not os.path.isdir(music_dir):
            logger.error(f"音樂資料夾不存在或不是目錄: {music_dir}")
            raise NotADirectoryError(f"音樂資料夾不存在或不是目錄: {music_dir}")
        
        # 初始化屬性
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
        
        # 音頻緩存，提高效能
        self._audio_cache = {}
        
        # 新增：最後操作時間戳，用於判斷是否是手動操作導致的切換
        self.last_manual_operation_time = 0
        
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
        # 檢查語音客戶端
        if not self.voice_client or not self.voice_client.is_connected():
            logger.error("未連接語音頻道，無法播放音樂")
            raise RuntimeError("未連接語音頻道，無法播放音樂")
        
        # 查找音樂文件
        file_path = self._find_audio_file(song_id)
        if not file_path:
            logger.error(f"找不到對應的音樂檔案：{song_id}")
            raise FileNotFoundError(f"找不到對應的音樂檔案：{song_id}")
        
        # 如果當前正在播放，先停止
        if self.voice_client.is_playing():
            logger.debug("播放新歌前先停止當前播放")
            self.voice_client.stop()
        
        # 更新當前歌曲信息
        self.current_song = {"id": song_id, "file_path": file_path}
        self.is_playing = True
        self.is_paused = False
        self.start_time = time.time()  # 使用 time.time() 代替 asyncio.get_running_loop().time() 提高兼容性
        self.paused_time = 0
        
        # 更新手動操作時間戳
        self.last_manual_operation_time = time.time()
        
        # 創建音頻源
        audio_source = self._create_audio_source(file_path)
        
        # 開始播放
        logger.info(f"開始播放歌曲: {song_id} ({file_path})")
        self.voice_client.play(audio_source, after=self._play_finished_callback)

    async def stop(self):
        """
        停止播放並重置狀態
        """
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
            logger.info("已停止播放")
        
        # 更新手動操作時間戳
        self.last_manual_operation_time = time.time()
        
        self.is_playing = False
        self.is_paused = False
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
            if self.start_time is not None:
                self.paused_time += time.time() - self.start_time
            
            # 更新手動操作時間戳
            self.last_manual_operation_time = time.time()
            
            logger.info("已暫停播放")

    async def resume(self):
        """
        恢復播放
        """
        if self.voice_client and self.is_paused:
            self.voice_client.resume()
            self.is_paused = False
            self.start_time = time.time()
            
            # 更新手動操作時間戳
            self.last_manual_operation_time = time.time()
            
            logger.info("已恢復播放")

    def get_current_status(self) -> Dict[str, Optional[Any]]:
        """
        獲取播放器當前狀態
        :return: Dict[str, Optional[object]]
        """
        current_time = 0
        if self.is_playing and not self.is_paused and self.start_time:
            current_time = time.time() - self.start_time + self.paused_time
        elif self.is_paused:
            current_time = self.paused_time
        
        logger.debug(f"播放器狀態查詢: is_playing={self.is_playing}, is_paused={self.is_paused}, current_sec={int(current_time)}")
        
        return {
            "is_playing": self.is_playing,
            "is_paused": self.is_paused,
            "song_id": self.current_song["id"] if self.current_song else None,
            "current_sec": int(current_time),
            "last_manual_operation_time": self.last_manual_operation_time  # 新增：返回最後操作時間
        }
    
    def _find_audio_file(self, song_id: str) -> Optional[str]:
        """
        根據歌曲ID查找對應的音頻文件
        :param song_id: 歌曲ID
        :return: 文件路徑或None
        """
        # 優先查找 Opus 格式檔案
        opus_path = os.path.join(self.music_dir, f"{song_id}.opus")
        if os.path.exists(opus_path):
            return opus_path
            
        # 檢查其他常見音頻格式
        for extension in [".webm", ".mp3", ".m4a"]:
            potential_path = os.path.join(self.music_dir, f"{song_id}{extension}")
            if os.path.exists(potential_path):
                return potential_path
        return None
    
    def _create_audio_source(self, file_path: str) -> discord.AudioSource:
        """
        創建音頻源，優先使用 Opus 格式以提高效能
        :param file_path: 音頻文件路徑
        :return: Discord音頻源
        """
        # 檢查檔案類型，如果是 Opus 使用專用的播放器
        if file_path.endswith(".opus"):
            logger.info("檢測到 Opus 音訊格式，使用 Opus 播放器")
            try:
                return discord.FFmpegOpusAudio(
                    source=file_path,
                    executable=self.ffmpeg_path,
                    bitrate=192,  # 和下載時相同的比特率
                )
            except Exception as e:
                logger.error(f"使用 Opus 播放器失敗，退回至 PCM: {e}")
                # 若 Opus 播放失敗，使用 PCM 作為備選方案
        
        # 使用標準 PCM 播放器
        logger.info("使用標準 PCM 播放器")
        return discord.FFmpegPCMAudio(
            source=file_path,
            executable=self.ffmpeg_path,
            # PCM 音質參數優化：
            # - 保持 48kHz 與立體聲以維持高音質
            # - 增加處理線程數提高效能
            # - 降低日誌級別減少輸出
            options="-vn -loglevel error -ar 48000 -ac 2 -threads 4"
        )

    def _play_finished_callback(self, error):
        """
        播放完成回調，由Discord音頻系統調用
        :param error: 錯誤信息
        """
        if error:
            logger.error(f"播放結束時發生錯誤: {error}")
        
        # 使用線程安全的方式調用回調
        self.loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self._safe_call_on_song_end())
        )
    
    async def _safe_call_on_song_end(self):
        """
        安全調用歌曲結束回調
        避免回調中的錯誤影響播放器
        """
        logger.debug("歌曲自然播放結束，觸發下一首回調")
        try:
            await self.on_song_end()
        except Exception as e:
            logger.error(f"歌曲結束回調發生錯誤: {e}")
            logger.exception(e)
    
    def clear_cache(self):
        """
        清除音頻緩存
        """
        self._audio_cache.clear()
        logger.debug("已清除音頻緩存")
