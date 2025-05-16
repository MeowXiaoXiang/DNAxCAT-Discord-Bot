import discord
from loguru import logger

class MusicEmbedManager:
    """
    管理各種情境下的 Discord Embed 生成，並記錄操作日誌
    """
    # ---------------------
    # 播放相關嵌入
    # ---------------------
    def playing_embed(self, song_info: dict, is_looping: bool, is_playing: bool, current_time: int = 0) -> discord.Embed:
        """
        生成播放中的嵌入訊息
        :param song_info: dict, 包含歌曲相關資訊
        :param is_looping: bool, 是否循環播放
        :param is_playing: bool, 播放狀態（True 為正在播放，False 為暫停）
        :param current_time: int, 已播放的秒數
        :return: discord.Embed
        """
        try:
            logger.debug(f"生成播放嵌入: {song_info.get('title', '未知')} 狀態: {'播放' if is_playing else '暫停'} 時間: {current_time}")
            status = "正在播放 ▶️" if is_playing else "已暫停 ⏸️"
            progress_bar = self.create_progress_bar(current_time, song_info['duration'])

            embed = discord.Embed(
                color=discord.Color.blurple()
            )
            embed.set_author(name=song_info['uploader'], url=song_info.get('uploader_url', ''))
            embed.description = f"{song_info['index']}. [{song_info['title']}]({song_info['url']})"
            embed.add_field(
                name="狀態",
                value=f"{status}\n{current_time // 60}:{current_time % 60:02d} / {song_info['duration'] // 60}:{song_info['duration'] % 60:02d}\n{progress_bar}",
                inline=False
            )
            embed.set_thumbnail(url=song_info['thumbnail'])
            embed.set_footer(text=f"循環播放: {'開啟' if is_looping else '關閉'}")
            return embed
        except Exception as e:
            logger.error(f"生成播放嵌入時發生錯誤: {e}")
            return self.error_embed("無法生成播放嵌入")

    @staticmethod
    def create_progress_bar(current, total, length=20):
        """
        建立進度條
        :param current: int, 已播放秒數
        :param total: int, 總秒數
        :param length: int, 進度條長度
        :return: str, 進度條
        """
        progress = int((current / total) * length) if total > 0 else 0
        bar = '▇' * progress + '—' * (length - progress)
        return f"`{bar}`"

    # ---------------------
    # 清單相關嵌入
    # ---------------------
    def playlist_embed(self, playlist_page: dict) -> 'discord.Embed':
        """
        生成播放清單嵌入訊息
        :param playlist_page: dict, 來自 get_playlist_paginated
        :return: discord.Embed
        """
        try:
            logger.debug(f"生成播放清單嵌入，第 {playlist_page.get('current_page', '?')}/{playlist_page.get('total_pages', '?')} 頁")
            # 初始化 Embed
            embed = discord.Embed(
                title="🎶 播放清單",
                description="",
                color=discord.Color.green()
            )

            # 處理清單內容
            if not playlist_page["songs"]:
                embed.description = "目前播放清單中沒有音樂！"
            else:
                song_descriptions = [
                    f"{song['index']}. [{song['title']}]({song['url']})" for song in playlist_page["songs"]
                ]
                embed.description = "\n".join(song_descriptions)

            # 添加 Footer 提供頁數與總歌曲資訊
            embed.set_footer(
                text=f"目前頁數: {playlist_page['current_page']}/{playlist_page['total_pages']} | 總歌曲數: {playlist_page['total_songs']}"
            )
            return embed

        except Exception as e:
            logger.error(f"生成播放清單嵌入時發生錯誤: {e}")
            return self.error_embed("無法生成播放清單嵌入")

    # ---------------------
    # 操作結果嵌入
    # ---------------------
    def added_song_embed(self, song_info):
        """
        生成新增歌曲後的提示嵌入訊息
        :param song_info: dict, 包含新增歌曲的相關資訊
        :return: discord.Embed
        """
        try:
            logger.info(f"生成新增歌曲嵌入: {song_info.get('title', '未知')}")
            embed = discord.Embed(
                title="✅ 已新增歌曲",
                description=f"[{song_info['title']}]({song_info['url']}) 已新增至播放清單",
                color=discord.Color.green()
            )
            embed.set_author(name=song_info['uploader'], url=song_info.get('uploader_url', ''))
            embed.set_thumbnail(url=song_info['thumbnail'])
            embed.set_footer(text=f"歌曲 ID: {song_info['id']}")
            return embed
        except Exception as e:
            logger.error(f"生成新增歌曲嵌入時發生錯誤: {e}")
            return self.error_embed("無法生成新增歌曲嵌入")

    def removed_song_embed(self, song_info):
        """
        生成移除歌曲後的提示嵌入訊息
        :param song_info: dict, 包含移除歌曲的相關資訊
        :return: discord.Embed
        """
        try:
            logger.info(f"生成移除歌曲嵌入: {song_info.get('title', '未知')}")
            embed = discord.Embed(
                title="🗑️ 已移除歌曲",
                description=f"[{song_info['title']}]({song_info['url']}) 已從播放清單移除",
                color=discord.Color.orange()
            )
            embed.set_thumbnail(url=song_info['thumbnail'])
            return embed
        except Exception as e:
            logger.error(f"生成移除歌曲嵌入時發生錯誤: {e}")
            return self.error_embed("無法生成移除歌曲嵌入")

    def clear_playlist_embed(self):
        """
        生成清空播放清單後的提示嵌入訊息
        :return: discord.Embed
        """
        try:
            logger.info("生成清空播放清單嵌入")
            embed = discord.Embed(
                title="🗑️ 播放清單已清空",
                description="所有歌曲已從播放清單中移除",
                color=discord.Color.red()
            )
            return embed
        except Exception as e:
            logger.error(f"生成清空播放清單嵌入時發生錯誤: {e}")
            return self.error_embed("無法生成清空播放清單嵌入")

    # ---------------------
    # 錯誤相關嵌入
    # ---------------------
    def error_embed(self, error_message):
        """
        生成錯誤提示嵌入訊息
        :param error_message: str, 錯誤訊息
        :return: discord.Embed
        """
        logger.warning(f"生成錯誤嵌入: {error_message}")
        embed = discord.Embed(
            title="❌ 錯誤",
            description=error_message,
            color=discord.Color.red()
        )
        return embed

if __name__ == "__main__":
    # 測試資料
    test_song_info = {
        "id": "example123",
        "index": 1,
        "title": "Example Song",
        "uploader": "Example Uploader",
        "uploader_url": "https://example.com/channel/example",
        "duration": 120,
        "url": "https://example.com/song/example123",
        "thumbnail": "https://example.com/images/example_thumbnail.jpg"
    }

    test_playlist = [
        {
            "id": "example123",
            "index": 1,
            "title": "Example Song 1",
            "url": "https://example.com/song/example123",
        },
        {
            "id": "example124",
            "index": 2,
            "title": "Example Song 2",
            "url": "https://example.com/song/example124",
        }
    ]

    embed_manager = MusicEmbedManager()

    def print_embed_simulation(title, embed):
        print(f"\n{'-' * 50}")
        print(f" 模擬嵌入 - {title}")
        print(f"{'-' * 50}")
        print(f"Title: {embed.get('title', '無')}")
        print(f"Description: {embed.get('description', '無')}")
        if "author" in embed:
            print(f"Author: {embed['author']['name']} ({embed['author'].get('url', '無')})")
        if "fields" in embed:
            for field in embed["fields"]:
                print(f"{field['name']}: {field['value']}")
        if "footer" in embed:
            print(f"Footer: {embed['footer']['text']}")
        print(f"{'-' * 50}\n")

    print("--- 測試播放嵌入 ---")
    current_time_simulation = 75
    playing_embed = embed_manager.playing_embed(
        test_song_info,
        is_looping=True,
        is_playing=True,
        current_time=current_time_simulation
    )
    print_embed_simulation("播放嵌入", playing_embed.to_dict())

    print("--- 測試新增歌曲嵌入 ---")
    added_embed = embed_manager.added_song_embed(test_song_info)
    print_embed_simulation("新增歌曲嵌入", added_embed.to_dict())

    print("--- 測試播放清單嵌入 ---")
    playlist_embed = embed_manager.playlist_embed(test_playlist)
    print_embed_simulation("播放清單嵌入", playlist_embed.to_dict())

    print("--- 測試移除歌曲嵌入 ---")
    removed_embed = embed_manager.removed_song_embed(test_song_info)
    print_embed_simulation("移除歌曲嵌入", removed_embed.to_dict())

    print("--- 測試清空播放清單嵌入 ---")
    clear_embed = embed_manager.clear_playlist_embed()
    print_embed_simulation("清空播放清單嵌入", clear_embed.to_dict())

    print("--- 測試錯誤嵌入 ---")
    error_embed = embed_manager.error_embed("這是一個測試錯誤訊息")
    print_embed_simulation("錯誤嵌入", error_embed.to_dict())
