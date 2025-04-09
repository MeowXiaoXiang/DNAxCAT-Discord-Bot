from typing import Optional
from loguru import logger

class PlaylistManager:
    """
    播放清單管理器：負責管理歌曲的新增、刪除、取得下一首、上一首、清單重排等功能
    提供清晰的歌曲管理邏輯，包括支援循環播放模式與分頁查看
    """

    def __init__(self):
        self.playlist = []  # 儲存歌曲資訊的列表
        self.current_index = -1  # 目前的播放的歌曲index
        self.loop = False  # 初始為非循環播放模式

    def add(self, song: dict) -> dict:
        required_keys = {"id", "title", "url", "duration", "uploader", "thumbnail", "uploader_url"}
        if not isinstance(song, dict) or not required_keys.issubset(song):
            raise ValueError(f"歌曲資訊格式錯誤，必須包含以下欄位: {required_keys}")

        new_index = len(self.playlist) + 1
        song_with_index = {"index": new_index, **song}
        self.playlist.append(song_with_index)

        # 如果是第一首，初始化 current_index
        if len(self.playlist) == 1:
            self.current_index = 0

        return song_with_index

    def remove(self, index: int) -> list:
        if not isinstance(index, int) or index < 1:
            raise ValueError("歌曲編號必須是正整數")

        self.playlist = [song for song in self.playlist if song["index"] != index]
        self._reindex_playlist()

        # 修正 current_index，防止超出範圍
        if self.current_index >= len(self.playlist):
            self.current_index = len(self.playlist) - 1 if self.playlist else -1

        return self.playlist

    def get_current_song(self) -> Optional[dict]:
        if not self.playlist:
            logger.warning("播放清單為空，無法取得目前的歌曲")
            return None

        if not (0 <= self.current_index < len(self.playlist)):
            logger.warning(f"目前的index無效: {self.current_index} (清單長度: {len(self.playlist)})")
            return None

        return self.playlist[self.current_index]

    def get_next_song(self) -> Optional[dict]:
        """
        取得下一首歌曲，並更新index。
        - 循環模式下到尾端會跳回第一首
        - 非循環模式下到尾端返回 None
        - 僅一首時禁止切換
        """
        logger.debug("準備取得下一首歌曲")
        if not self.playlist:
            logger.warning("播放清單為空，無法取得下一首歌曲")
            return None

        if len(self.playlist) == 1:
            logger.info("僅有一首歌曲，禁止切換下一首")
            return None

        if self.loop:
            self.current_index = (self.current_index + 1) % len(self.playlist)
        else:
            if self.current_index + 1 < len(self.playlist):
                self.current_index += 1
            else:
                logger.info("非循環模式，播放到最後一首")
                return None

        return self.playlist[self.current_index]

    def get_previous_song(self) -> Optional[dict]:
        """
        取得上一首歌曲，並更新index。
        - 循環模式下到第一首會跳回最後一首
        - 非循環模式下到第一首返回 None
        - 僅一首時禁止切換
        """
        logger.debug("準備取得上一首歌曲")
        if not self.playlist:
            logger.warning("播放清單為空，無法取得上一首歌曲")
            return None

        if len(self.playlist) == 1:
            logger.info("僅有一首歌曲，禁止切換上一首")
            return None

        if self.loop:
            self.current_index = (self.current_index - 1) % len(self.playlist)
        else:
            if self.current_index > 0:
                self.current_index -= 1
            else:
                logger.info("非循環模式，已經是第一首")
                return None

        return self.playlist[self.current_index]

    def clear(self) -> None:
        self.playlist = []
        self.current_index = -1

    def get_playlist_paginated(self, page: int = 1, per_page: int = 10, char_limit: int = 6000) -> dict:
        if not isinstance(page, int) or not isinstance(per_page, int) or page < 1 or per_page < 1:
            raise ValueError("頁碼和每頁數量必須是正整數且大於 0")

        total_songs = len(self.playlist)
        total_pages = (total_songs + per_page - 1) // per_page

        if page > total_pages:
            return {"current_page": page, "total_pages": total_pages, "total_songs": total_songs, "songs": []}

        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        songs = self.playlist[start_index:end_index]
        description_chars = sum(len(f"{song['index']}. {song['title']}") for song in songs)

        while description_chars > char_limit and per_page > 1:
            per_page -= 1
            end_index = start_index + per_page
            songs = self.playlist[start_index:end_index]
            description_chars = sum(len(f"{song['index']}. {song['title']}") for song in songs)

        total_pages = (total_songs + per_page - 1) // per_page
        return {
            "current_page": page,
            "total_pages": total_pages,
            "total_songs": total_songs,
            "songs": songs
        }

    def _reindex_playlist(self) -> None:
        for idx, song in enumerate(self.playlist, start=1):
            song["index"] = idx
        self.current_index = 0 if self.playlist else -1


if __name__ == "__main__":
    manager = PlaylistManager()

    # 新增 5 首歌曲
    for i in range(5):
        manager.add({
            "id": f"id_{i+1}",
            "title": f"Song {i+1}",
            "uploader": f"Uploader {i+1}",
            "uploader_url": f"http://example.com/channel{i+1}",
            "duration": "3:30",
            "url": f"http://example.com/song{i+1}",
            "thumbnail": f"http://example.com/thumbnail{i+1}.jpg"
        })

    # 測試分頁
    print("=== 分頁測試 ===")
    print(manager.get_playlist_paginated(page=1, per_page=3))
    print(manager.get_playlist_paginated(page=2, per_page=3))
    print(manager.get_playlist_paginated(page=3, per_page=3))

    # 測試播放切換
    print("\n=== 播放切換測試 ===")
    manager.loop = True
    for _ in range(7):
        next_song = manager.get_next_song()
        print(f"▶ 下一首：{next_song['title'] if next_song else '無'} (index: {manager.current_index})")

    for _ in range(7):
        prev_song = manager.get_previous_song()
        print(f"◀ 上一首：{prev_song['title'] if prev_song else '無'} (index: {manager.current_index})")

    # 測試清除與移除
    print("\n=== 移除歌曲 ===")
    manager.remove(3)
    for song in manager.playlist:
        print(f"剩餘：{song['index']}. {song['title']}")

    print(f"目前播放：{manager.get_current_song()['title'] if manager.get_current_song() else '無'}")