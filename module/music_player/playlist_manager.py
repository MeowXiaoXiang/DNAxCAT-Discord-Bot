from typing import Optional
from loguru import logger

class MusicPlaylistManager:
    """
    播放清單管理器：負責管理歌曲的新增、刪除、取得下一首、上一首、清單重排等功能
    提供清晰的歌曲管理邏輯，包括支援循環播放模式與分頁查看
    """

    def __init__(self):
        self.playlist = []  # 儲存歌曲資訊的列表
        self.current_index = -1  # 目前的播放的歌曲index
        self.loop = False  # 初始為非循環播放模式

    def add(self, song: dict) -> dict:
        """
        新增一首歌曲到播放清單
        :param song: dict, 必須包含 id, title, url, duration, uploader, thumbnail, uploader_url
        :return: dict, 加入後的歌曲資訊（含 index）
        """
        required_keys = {"id", "title", "url", "duration", "uploader", "thumbnail", "uploader_url"}
        if not isinstance(song, dict) or not required_keys.issubset(song):
            logger.error(f"新增歌曲失敗，資訊格式錯誤: {song}")
            raise ValueError(f"歌曲資訊格式錯誤，必須包含以下欄位: {required_keys}")

        song_with_index = {"index": len(self.playlist) + 1, **song}
        self.playlist.append(song_with_index)
        logger.info(f"已新增歌曲: {song_with_index['title']} (ID: {song_with_index['id']})，目前清單共 {len(self.playlist)} 首")
        # 如果是第一首，初始化 current_index
        if len(self.playlist) == 1:
            self.current_index = 0
            logger.debug("播放清單原本為空，current_index 初始化為 0")
        return song_with_index

    def remove(self, index: int) -> list:
        """
        移除指定 index 的歌曲。
        :param index: int, 歌曲編號（1-based）
        :return: list, 移除後的播放清單
        """
        if not isinstance(index, int) or index < 1:
            logger.error(f"移除歌曲失敗，index 非正整數: {index}")
            raise ValueError("歌曲編號必須是正整數")
        # 找出要移除的歌曲在 list 的位置
        remove_pos = next((i for i, song in enumerate(self.playlist) if song["index"] == index), None)
        if remove_pos is None:
            logger.warning(f"移除歌曲失敗，找不到 index={index} 的歌曲")
            return self.playlist
        removed_song = self.playlist.pop(remove_pos)
        logger.info(f"已移除歌曲: {removed_song['title']} (ID: {removed_song['id']})，剩餘 {len(self.playlist)} 首")
        # 修正 current_index
        if remove_pos < self.current_index:
            self.current_index -= 1
        elif remove_pos == self.current_index:
            # 如果移除的是目前播放的，指向下一首，若無則上一首，若全清空則 -1
            if self.current_index >= len(self.playlist):
                self.current_index = len(self.playlist) - 1
                logger.debug(f"移除當前播放歌曲，current_index 修正為 {self.current_index}")
        if not self.playlist:
            self.current_index = -1
            logger.debug("播放清單已清空，current_index 設為 -1")
        self._reindex_playlist()
        return self.playlist

    def clear(self) -> None:
        """
        清空播放清單。
        """
        logger.info(f"清空播放清單，原有 {len(self.playlist)} 首歌曲")
        self.playlist = []
        self.current_index = -1

    def get_current_song(self) -> Optional[dict]:
        """
        取得目前播放的歌曲資訊。
        :return: dict or None
        """
        if not self.playlist or not (0 <= self.current_index < len(self.playlist)):
            logger.debug("查詢目前播放歌曲，但播放清單為空或 current_index 越界")
            return None
        return self.playlist[self.current_index]

    def switch_to_next_song(self) -> Optional[dict]:
        """
        切換到下一首歌，會改變 current_index 並回傳新當前歌曲。
        若無下一首則回傳 None。
        """
        if not self.playlist or len(self.playlist) == 1:
            logger.debug("切換下一首失敗，播放清單為空或僅一首")
            return None
        if self.loop:
            self.current_index = (self.current_index + 1) % len(self.playlist)
        else:
            if self.current_index + 1 < len(self.playlist):
                self.current_index += 1
            else:
                logger.debug("切換下一首失敗，已到清單末尾且非循環模式")
                return None
        logger.info(f"切換到下一首: {self.playlist[self.current_index]['title']} (index: {self.current_index})")
        return self.playlist[self.current_index]

    def switch_to_previous_song(self) -> Optional[dict]:
        """
        切換到上一首歌，會改變 current_index 並回傳新當前歌曲。
        若無上一首則回傳 None。
        """
        if not self.playlist or len(self.playlist) == 1:
            logger.debug("切換上一首失敗，播放清單為空或僅一首")
            return None
        if self.loop:
            self.current_index = (self.current_index - 1) % len(self.playlist)
        else:
            if self.current_index > 0:
                self.current_index -= 1
            else:
                logger.debug("切換上一首失敗，已到清單開頭且非循環模式")
                return None
        logger.info(f"切換到上一首: {self.playlist[self.current_index]['title']} (index: {self.current_index})")
        return self.playlist[self.current_index]

    def get_next_song_info(self) -> Optional[dict]:
        """
        僅查詢下一首歌（不改變 current_index），若無下一首則回傳 None。
        """
        if not self.playlist or len(self.playlist) == 1:
            return None
        if self.loop:
            idx = (self.current_index + 1) % len(self.playlist)
        else:
            if self.current_index + 1 < len(self.playlist):
                idx = self.current_index + 1
            else:
                return None
        logger.debug(f"查詢下一首: {self.playlist[idx]['title']} (index: {idx})")
        return self.playlist[idx]

    def get_previous_song_info(self) -> Optional[dict]:
        """
        僅查詢上一首歌（不改變 current_index），若無上一首則回傳 None。
        """
        if not self.playlist or len(self.playlist) == 1:
            return None
        if self.loop:
            idx = (self.current_index - 1) % len(self.playlist)
        else:
            if self.current_index > 0:
                idx = self.current_index - 1
            else:
                return None
        logger.debug(f"查詢上一首: {self.playlist[idx]['title']} (index: {idx})")
        return self.playlist[idx]

    def _reindex_playlist(self) -> None:
        """
        重新編號播放清單內所有歌曲的 index 欄位。
        """
        for idx, song in enumerate(self.playlist, start=1):
            song["index"] = idx
        logger.debug("已重新編號播放清單 index")

    def get_playlist_paginated(self, page: int = 1, per_page: int = 5) -> dict:
        """
        取得分頁後的播放清單資訊。
        :param page: int, 目前頁數（從 1 開始）
        :param per_page: int, 每頁顯示幾首
        :return: dict, 包含 songs, current_page, total_pages, total_songs
        """
        total_songs = len(self.playlist)
        total_pages = (total_songs + per_page - 1) // per_page if per_page > 0 else 1
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        end = start + per_page
        songs = self.playlist[start:end]
        logger.debug(f"分頁查詢：第 {page}/{total_pages} 頁，每頁 {per_page} 首，共 {total_songs} 首")
        return {
            "songs": songs,
            "current_page": page,
            "total_pages": total_pages,
            "total_songs": total_songs
        }

if __name__ == "__main__":
    manager = MusicPlaylistManager()

    # 新增 11 首歌曲
    print("\n=== 添加11首歌曲 ===")
    for i in range(11):
        song = manager.add({
            "id": f"id_{i+1}",
            "title": f"Song {i+1}",
            "uploader": f"Uploader {i+1}",
            "uploader_url": f"http://example.com/channel{i+1}",
            "duration": "3:30",
            "url": f"http://example.com/song{i+1}",
            "thumbnail": f"http://example.com/thumbnail{i+1}.jpg"
        })
        print(f"已添加歌曲 {song['index']}: {song['title']}")
    
    print(f"播放清單總共有 {len(manager.playlist)} 首歌曲")

    # 測試分頁（per_page=5）
    print("\n=== 分頁測試 (per_page=5) ===")
    page1 = manager.get_playlist_paginated(page=1, per_page=5)
    print(f"第1頁: 當前頁={page1['current_page']}, 總頁數={page1['total_pages']}, 歌曲數={len(page1['songs'])}")
    print("第1頁歌曲:")
    for s in page1['songs']:
        print(f"  {s['index']}. {s['title']}")
    
    page2 = manager.get_playlist_paginated(page=2, per_page=5)
    print(f"第2頁: 當前頁={page2['current_page']}, 總頁數={page2['total_pages']}, 歌曲數={len(page2['songs'])}")
    print("第2頁歌曲:")
    for s in page2['songs']:
        print(f"  {s['index']}. {s['title']}")
    
    page3 = manager.get_playlist_paginated(page=3, per_page=5)
    print(f"第3頁: 當前頁={page3['current_page']}, 總頁數={page3['total_pages']}, 歌曲數={len(page3['songs'])}")
    print("第3頁歌曲:")
    for s in page3['songs']:
        print(f"  {s['index']}. {s['title']}")
    
    # 測試頁碼邊界
    print("\n=== 頁碼邊界測試 ===")
    page0 = manager.get_playlist_paginated(page=0, per_page=5)  # 應自動修正為頁碼1
    print(f"頁碼0: 實際返回頁碼={page0['current_page']}")
    
    page99 = manager.get_playlist_paginated(page=99, per_page=5)  # 應自動修正為最後一頁
    print(f"頁碼99: 實際返回頁碼={page99['current_page']}")
    
    # 模擬翻頁操作
    print("\n=== 模擬翻頁操作 ===")
    # 從頁碼1開始，連續點擊下一頁
    current_page = 1
    for i in range(4):  # 應該最多到頁碼3然後停止
        new_page = current_page + 1
        result = manager.get_playlist_paginated(page=new_page, per_page=5)
        print(f"從頁碼{current_page}點擊下一頁: 請求頁碼={new_page}, 實際返回頁碼={result['current_page']}")
        current_page = result['current_page']
    
    # 從最後一頁開始，連續點擊上一頁
    for i in range(4):  # 應該最多到頁碼1然後停止
        new_page = current_page - 1
        result = manager.get_playlist_paginated(page=new_page, per_page=5)
        print(f"從頁碼{current_page}點擊上一頁: 請求頁碼={new_page}, 實際返回頁碼={result['current_page']}")
        current_page = result['current_page']

    # 測試播放切換
    print("\n=== 播放切換測試 ===")
    manager.loop = True
    for _ in range(7):
        next_song = manager.switch_to_next_song()
        print(f"▶ 下一首：{next_song['title'] if next_song else '無'} (index: {manager.current_index})")

    for _ in range(7):
        prev_song = manager.switch_to_previous_song()
        print(f"◀ 上一首：{prev_song['title'] if prev_song else '無'} (index: {manager.current_index})")

    # 測試清除與移除
    print("\n=== 移除歌曲 ===")
    manager.remove(3)
    for song in manager.playlist:
        print(f"剩餘：{song['index']}. {song['title']}")

    print(f"目前播放：{manager.get_current_song()['title'] if manager.get_current_song() else '無'}")

    # === 進階測試 ===
    print("\n=== 進階測試：連續移除多首歌（包含目前播放的、第一首、最後一首） ===")
    manager = MusicPlaylistManager()
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
    print(f"初始播放：{manager.get_current_song()['title']}")
    manager.switch_to_next_song()  # 播到第2首
    print(f"切到第2首：{manager.get_current_song()['title']}")
    manager.remove(2)  # 移除目前播放的
    print(f"移除第2首，現在播放：{manager.get_current_song()['title'] if manager.get_current_song() else '無'}")
    manager.remove(1)  # 移除第一首
    print(f"移除第1首，現在播放：{manager.get_current_song()['title'] if manager.get_current_song() else '無'}")
    manager.remove(5)  # 移除最後一首
    print(f"移除第5首，現在播放：{manager.get_current_song()['title'] if manager.get_current_song() else '無'}")
    print(f"剩餘歌曲：{[song['title'] for song in manager.playlist]}")

    # 清空後再加歌
    print("\n=== 清空後再加歌 ===")
    manager.clear()
    print(f"清空後 current_index: {manager.current_index}, playlist: {manager.playlist}")
    manager.add({
        "id": "id_new",
        "title": "New Song",
        "uploader": "Uploader New",
        "uploader_url": "http://example.com/channel_new",
        "duration": "3:30",
        "url": "http://example.com/song_new",
        "thumbnail": "http://example.com/thumbnail_new.jpg"
    })
    print(f"加歌後 current_index: {manager.current_index}, 現在播放：{manager.get_current_song()['title']}")

    # 只剩一首歌時切歌
    print("\n=== 只剩一首歌時切歌 ===")
    print(f"下一首：{manager.switch_to_next_song()}")
    print(f"上一首：{manager.switch_to_previous_song()}")

    # current_index 越界情境
    print("\n=== current_index 越界測試 ===")
    manager.clear()
    manager.current_index = 10  # 強制越界
    print(f"越界後 get_current_song: {manager.get_current_song()}")

    # 新增查詢功能測試
    print("\n=== 查詢下一首/上一首（不切歌）功能測試 ===")
    manager = MusicPlaylistManager()
    for i in range(3):
        manager.add({
            "id": f"id_{i+1}",
            "title": f"Song {i+1}",
            "uploader": f"Uploader {i+1}",
            "uploader_url": f"http://example.com/channel{i+1}",
            "duration": "3:30",
            "url": f"http://example.com/song{i+1}",
            "thumbnail": f"http://example.com/thumbnail{i+1}.jpg"
        })
    print(f"目前播放：{manager.get_current_song()['title']}")
    print(f"peek 下一首：{manager.get_next_song_info()['title'] if manager.get_next_song_info() else '無'}")
    print(f"peek 上一首：{manager.get_previous_song_info()['title'] if manager.get_previous_song_info() else '無'}")
    manager.switch_to_next_song()
    print(f"切歌後目前播放：{manager.get_current_song()['title']}")
    print(f"peek 下一首：{manager.get_next_song_info()['title'] if manager.get_next_song_info() else '無'}")
    print(f"peek 上一首：{manager.get_previous_song_info()['title'] if manager.get_previous_song_info() else '無'}")