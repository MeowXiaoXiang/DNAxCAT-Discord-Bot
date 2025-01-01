import os
import subprocess
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from loguru import logger

class YTDLPManager:
    def __init__(self, download_folder: str):
        """
        初始化 YTDLPManager，負責處理下載和提取
        """
        self.download_folder = download_folder
        os.makedirs(self.download_folder, exist_ok=True)

    def _run_yt_dlp_with_progress(self, args):
        """
        使用 subprocess 執行 yt-dlp，並即時顯示進度
        """
        try:
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            logger.debug(f"執行命令: {' '.join(args)}")
            for line in iter(process.stdout.readline, ""):
                line = line.strip()
                if "[download]" in line:
                    print(f"\r{line}", end="")
            process.stdout.close()
            return_code = process.wait()
            print()  # 確保下載完成後換行
            if return_code != 0:
                logger.error("yt-dlp 執行失敗")
                return False
            return True
        except Exception as e:
            logger.error(f"執行 yt-dlp 時發生錯誤：{e}")
            return False

    def extract_info(self, url: str):
        """
        使用 subprocess 提取簡化的影片資訊
        """
        try:
            args = [
                "yt-dlp",
                "--dump-json",
                "--quiet",
                "--no-warnings",
                url,
            ]
            process = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if process.returncode == 0:
                raw_info = json.loads(process.stdout)
                simplified_info = {
                    "id": raw_info.get("id"),
                    "title": raw_info.get("title"),
                    "uploader": raw_info.get("uploader"),
                    "uploader_url": raw_info.get("channel_url"),
                    "duration": raw_info.get("duration"),
                    "url": raw_info.get("webpage_url"),
                    "thumbnail": raw_info.get("thumbnail"),
                }
                logger.debug(f"提取到的簡化資訊: {simplified_info}")
                return simplified_info
            logger.error(f"提取資訊失敗：{process.stderr.strip()}")
            return None
        except Exception as e:
            logger.error(f"提取資訊時發生錯誤：{e}")
            return None

    def download(self, url: str):
        """
        使用 subprocess 下載影片，支援下載進度顯示
        """
        try:
            output_template = os.path.join(self.download_folder, "%(id)s.%(ext)s")
            args = [
                "yt-dlp",
                "--format", "bestaudio/best",
                "--output", output_template,
                "--no-warnings",
                url,
            ]
            success = self._run_yt_dlp_with_progress(args)
            if success:
                logger.debug("下載成功，嘗試提取下載的影片資訊...")
                info = self.extract_info(url)
                if info:
                    downloaded_files = os.listdir(self.download_folder)
                    for file in downloaded_files:
                        logger.debug(f"下載資料夾內的檔案: {file}")
                        if file.startswith(info["id"]):
                            filepath = os.path.join(self.download_folder, file)
                            logger.info(f"實際下載的檔案路徑：{filepath}")
                            return info, filepath
                    logger.error("未找到匹配的下載檔案！檢查下載資料夾")                        
                return None, None
            else:
                logger.error("yt-dlp 執行失敗")
                return None, None
        except Exception as e:
            logger.error(f"下載歌曲時發生錯誤：{e}")
            return None, None

    async def async_extract_info(self, url: str):
        """
        提供異步方式調用同步的 extract_info 方法
        """
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(executor, self.extract_info, url)

    async def async_download(self, url: str):
        """
        提供異步方式調用同步的 download 方法
        """
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(executor, self.download, url)

    def clear_temp_files(self):
        """
        清空下載資料夾內的所有檔案
        """
        try:
            for file_name in os.listdir(self.download_folder):
                file_path = os.path.join(self.download_folder, file_name)
                if os.path.isfile(file_path):  # 確保只刪除檔案
                    os.remove(file_path)
            logger.info(f"已清空暫存檔案，目錄: {self.download_folder}")
        except Exception as e:
            logger.error(f"清除暫存檔案時發生錯誤: {e}")

# 測試模組
if __name__ == "__main__":
    async def test():
        yt_manager = YTDLPManager("./temp/music")
        url = input("請輸入 YouTube 的連結: ")

        print("\n提取資訊:")
        try:
            info = await yt_manager.async_extract_info(url)
            if info:
                print(json.dumps(info, indent=4, ensure_ascii=False))
        except Exception as e:
            print(f"提取資訊失敗: {e}")

        print("\n下載並提取資訊:")
        try:
            info, filepath = await yt_manager.async_download(url)
            if info and filepath:
                print(f"下載完成: {filepath}")
                print(json.dumps(info, indent=4, ensure_ascii=False))
        except Exception as e:
            print(f"下載失敗: {e}")

    asyncio.run(test())