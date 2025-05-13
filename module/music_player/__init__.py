"""
Music Player 子模組
-------------------
這個模組提供 Discord Bot 的音樂播放功能，支援播放、暫停、切歌、播放清單管理、嵌入訊息顯示、互動按鈕等

注意：這個 music_player 僅支援 YouTube 音樂來源（透過 yt-dlp 下載/解析），尚未支援其他平台

主要元件：
- MusicPlayerController：負責音樂播放、暫停、恢復、狀態查詢
- MusicPlaylistManager：播放清單管理（增刪查改、切歌、分頁）
- YTDLPDownloader：YouTube 音樂下載與資訊提取
- MusicEmbedManager：Discord 嵌入訊息生成
- MusicPlayerButtons/PaginationButtons：互動式控制按鈕
"""

from .player_controller import MusicPlayerController
from .playlist_manager import MusicPlaylistManager
from .yt_dlp_manager import YTDLPDownloader
from .embed_manager import MusicEmbedManager
from .button_manager import MusicPlayerButtons, PaginationButtons

__all__ = [
    "MusicPlayerController",
    "MusicPlaylistManager",
    "YTDLPDownloader",
    "MusicEmbedManager",
    "MusicPlayerButtons",
    "PaginationButtons"
]
