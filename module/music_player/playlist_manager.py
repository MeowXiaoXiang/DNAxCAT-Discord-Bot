from typing import Optional
from loguru import logger

class PlaylistManager:
    """
    播放清單管理器：負責管理歌曲的新增、刪除、取得下一首、清單重排等功能
    提供清晰的歌曲管理邏輯，包括支援循環播放模式與分頁查看
    """

    def __init__(self):
        """
        初始化播放清單管理器
        - self.playlist: 儲存所有歌曲的清單
        - self.current_index: 目前的播放歌曲的index，-1 表示尚未開始播放
        - self.loop: 是否啟用循環播放模式
        """
        self.playlist = []  # 儲存歌曲資訊的列表
        self.current_index = -1  # 目前的播放的歌曲index
        self.loop = False  # 初始為非循環播放模式

    def add(self, song: dict) -> dict:
        """
        新增歌曲到播放清單，並動態分配編號

        Args:
            song (dict): 包含歌曲資訊的字典，例如:
            {
                "id": "abc123",
                "title": "Song Name",
                "uploader": "Uploader",
                "uploader_url": "https://uploader.channel.url",  # 新增欄位
                "duration": "3:40",
                "url": "https://...",
                "thumbnail": "thumbnail_url"
            }

        Returns:
            dict: 新增到清單中的歌曲資訊（包含 index）
        """
        required_keys = {"id", "title", "url", "duration", "uploader", "thumbnail", "uploader_url"}
        if not isinstance(song, dict) or not required_keys.issubset(song):
            raise ValueError(f"歌曲資訊格式錯誤，必須包含以下欄位: {required_keys}")

        new_index = len(self.playlist) + 1  # 計算歌曲的編號
        song_with_index = {"index": new_index, **song}  # 加入 index 欄位
        self.playlist.append(song_with_index)

        # 如果是第一首，初始化 current_index
        if len(self.playlist) == 1:
            self.current_index = 0

        return song_with_index

    def remove(self, index: int) -> list:
        """
        根據編號移除歌曲，並重新整理清單index

        Args:
            index (int): 要移除的歌曲編號

        Returns:
            list: 更新後的播放清單
        """
        if not isinstance(index, int) or index < 1:
            raise ValueError("歌曲編號必須是正整數")

        # 保留未被移除的歌曲
        self.playlist = [song for song in self.playlist if song["index"] != index]
        self._reindex_playlist()  # 重新整理歌曲index
        return self.playlist

    def get_current_song(self) -> Optional[dict]:
        """
        取得目前的正在播放的歌曲

        Returns:
            dict or None: 目前的歌曲資訊，若無有效歌曲則返回 None
        """
        if not self.playlist:  # 播放清單為空
            logger.warning("播放清單為空，無法取得目前的歌曲")
            return None

        if not (0 <= self.current_index < len(self.playlist)):  # 檢查index有效性
            logger.warning(f"目前的index無效: {self.current_index} (清單長度: {len(self.playlist)})")
            return None

        return self.playlist[self.current_index]

    def get_next_song(self) -> Optional[dict]:
        """
        取得下一首歌曲，並更新index

        Returns:
            dict or None: 下一首歌曲資訊，若無歌曲可播放則返回 None
        """
        logger.debug("準備取得下一首歌曲")
        if not self.playlist:  # 播放清單為空
            logger.warning("播放清單為空，無法取得下一首歌曲")
            return None

        # 單首或多首的邏輯統一處理
        if self.loop:
            if len(self.playlist) > 1:  # 多首循環時，index前進
                self.current_index = (self.current_index + 1) % len(self.playlist)
            # 單首循環，保持目前的index不變
        else:
            if self.current_index + 1 < len(self.playlist):  # 非循環模式下，還有下一首
                self.current_index += 1
            else:
                logger.info("非循環模式，播放到最後一首")
                return None  # 到達最後一首時返回 None

        return self.playlist[self.current_index]

    def clear(self) -> None:
        """
        清空播放清單並重置播放index
        """
        self.playlist = []
        self.current_index = -1

    def get_playlist_paginated(self, page: int = 1, per_page: int = 10, char_limit: int = 6000) -> dict:
        """
        分頁查看播放清單，動態控制總字符數不超過限制。

        Args:
            page (int): 要查看的頁碼（從 1 開始）
            per_page (int): 每頁歌曲數量（初始值）
            char_limit (int): 每個嵌入的總字數上限，默認 6000

        Returns:
            dict: 分頁結果，包括 songs 列表、總頁數和字符限制。
        """
        if not isinstance(page, int) or not isinstance(per_page, int) or page < 1 or per_page < 1:
            raise ValueError("頁碼和每頁數量必須是正整數且大於 0")

        total_songs = len(self.playlist)
        total_pages = (total_songs + per_page - 1) // per_page  # 預計總頁數

        if page > total_pages:
            return {"current_page": page, "total_pages": total_pages, "total_songs": total_songs, "songs": []}

        # 計算分頁起始索引與字符總數
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        songs = self.playlist[start_index:end_index]
        description_chars = sum(len(f"{song['index']}. {song['title']}") for song in songs)

        # 如果字符超過限制，減少 per_page 並重新計算
        while description_chars > char_limit and per_page > 1:
            per_page -= 1
            end_index = start_index + per_page
            songs = self.playlist[start_index:end_index]
            description_chars = sum(len(f"{song['index']}. {song['title']}") for song in songs)

        total_pages = (total_songs + per_page - 1) // per_page  # 更新總頁數
        return {
            "current_page": page,
            "total_pages": total_pages,
            "total_songs": total_songs,
            "songs": songs
        }

    def _reindex_playlist(self) -> None:
        """
        重新整理播放清單中的歌曲編號，從 1 開始排序
        """
        for idx, song in enumerate(self.playlist, start=1):
            song["index"] = idx
        self.current_index = -1  # 重新設定播放index

# 測試
if __name__ == "__main__":
    manager = PlaylistManager()

    # 新增 25 個歌曲
    for i in range(25):
        manager.add({
            "id": f"id_{i+1}",
            "title": f"Song {i+1}",
            "uploader": f"Uploader {i+1}",
            "uploader_url": f"http://example.com/channel{i+1}",
            "duration": "3:30",
            "url": f"http://example.com/song{i+1}",
            "thumbnail": f"http://example.com/thumbnail{i+1}.jpg"
        })

    # 測試分頁查看
    print("=== 第 1 頁 ===")
    print(manager.get_playlist_paginated(page=1, per_page=10), end="\n\n")

    print("=== 第 2 頁 ===")
    print(manager.get_playlist_paginated(page=2, per_page=10), end="\n\n")

    print("=== 第 3 頁 ===")
    print(manager.get_playlist_paginated(page=3, per_page=10), end="\n\n") 

    print("=== 超出頁數範圍 ===")
    print(manager.get_playlist_paginated(page=4, per_page=10), end="\n\n")
