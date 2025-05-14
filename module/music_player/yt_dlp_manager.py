import os
import subprocess
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from loguru import logger

class YTDLPDownloader:
    def __init__(self, download_folder: str, ffmpeg_path: str = None):
        """
        初始化 YTDLPDownloader，負責處理下載和提取
        :param download_folder: str, 下載資料夾路徑
        :param ffmpeg_path: str, FFmpeg 執行檔路徑
        """
        self.download_folder = download_folder
        os.makedirs(self.download_folder, exist_ok=True)
        
        # 檢查 FFmpeg 路徑
        self.ffmpeg_path = ffmpeg_path
        if self.ffmpeg_path is None:
            logger.error("缺少 FFmpeg 路徑配置")
            raise ValueError("必須提供 FFmpeg 路徑才能轉換為 Opus 格式")
        if not os.path.exists(self.ffmpeg_path):
            logger.error(f"FFmpeg 不存在於指定路徑: {self.ffmpeg_path}")
            raise FileNotFoundError(f"FFmpeg 不存在於指定路徑: {self.ffmpeg_path}")
            
        logger.info(f"YTDLPDownloader 初始化，下載資料夾: {self.download_folder}")

    def _run_yt_dlp_with_progress(self, args):
        """
        使用 subprocess 執行 yt-dlp，並即時顯示進度
        :param args: list, yt-dlp 執行參數
        :return: bool, 是否成功
        """
        try:
            logger.debug(f"執行 yt-dlp 命令: {' '.join(args)}")
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
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
            
    def _convert_to_opus(self, input_file: str):
        """
        將下載的檔案轉換為高品質 Opus 格式
        :param input_file: 輸入檔案路徑
        :return: 輸出檔案路徑或 None (失敗時)
        """
        try:
            # 生成輸出檔案路徑 (替換副檔名為 .opus)
            file_id = os.path.splitext(os.path.basename(input_file))[0]
            output_file = os.path.join(self.download_folder, f"{file_id}.opus")
            
            logger.info(f"轉換音訊檔案為 Opus 格式: {input_file} -> {output_file}")
            
            # 啟動一個新的 subprocess 進行轉換 (避免 GIL 限制)
            args = [
                self.ffmpeg_path,
                "-i", input_file,
                "-c:a", "libopus",
                "-b:a", "192k",
                "-vbr", "on",
                "-application", "audio",
                "-ar", "48000",
                "-ac", "2",
                "-loglevel", "warning",
                output_file
            ]
            
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # 等待轉換完成
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                logger.error(f"FFmpeg 轉換失敗: {stderr}")
                return None
                
            # 刪除原始檔案
            try:
                os.remove(input_file)
                logger.debug(f"已刪除原始音訊檔案: {input_file}")
            except Exception as e:
                logger.warning(f"刪除原始檔案失敗: {e}")
                
            return output_file
        except Exception as e:
            logger.error(f"轉換 Opus 格式時發生錯誤: {e}")
            return None

    def extract_info(self, url: str):
        """
        使用 subprocess 提取簡化的影片資訊
        :param url: str, 影片網址
        :return: dict or None
        """
        try:
            logger.info(f"提取影片資訊: {url}")
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
                output_lines = process.stdout.strip().splitlines()
                if not output_lines:
                    logger.error("yt-dlp 沒有輸出任何資訊")
                    return None
                first_json = json.loads(output_lines[0])
                simplified_info = {
                    "id": first_json.get("id"),
                    "title": first_json.get("title"),
                    "uploader": first_json.get("uploader"),
                    "uploader_url": first_json.get("channel_url"),
                    "duration": first_json.get("duration"),
                    "url": first_json.get("webpage_url"),
                    "thumbnail": first_json.get("thumbnail"),
                }
                logger.info(f"只取第一首: {simplified_info}")
                return simplified_info
            logger.error(f"提取資訊失敗：{process.stderr.strip()}")
            return None
        except Exception as e:
            logger.error(f"提取資訊時發生錯誤：{e}")
            return None

    def download(self, url: str):
        """
        使用 subprocess 下載影片並轉換為 Opus 格式
        :param url: str, 影片網址
        :return: (dict, str) or (None, None) - 影片資訊和 Opus 檔案路徑
        """
        try:
            logger.info(f"開始下載影片: {url}")
            # 先取得第一首的 id
            info = self.extract_info(url)
            if not info or not info.get("id"):
                logger.error("無法取得影片資訊或 id")
                return None, None
                
            # 設定下載輸出範本
            output_template = os.path.join(self.download_folder, "%s.%%(ext)s" % info["id"])
            
            # 下載最佳音訊格式
            args = [
                "yt-dlp",
                "--format", "bestaudio/best",
                "--output", output_template,
                "--no-warnings",
                info["url"],
            ]
            
            success = self._run_yt_dlp_with_progress(args)
            if not success:
                logger.error("yt-dlp 執行失敗")
                return None, None
                
            # 查找下載的檔案
            downloaded_file = None
            for file in os.listdir(self.download_folder):
                if file.startswith(info["id"]) and not file.endswith(".opus"):
                    downloaded_file = os.path.join(self.download_folder, file)
                    logger.info(f"找到下載的原始檔案: {downloaded_file}")
                    break
                    
            if not downloaded_file:
                logger.error("找不到下載的檔案")
                return None, None
                
            # 轉換為 Opus 格式
            opus_file = self._convert_to_opus(downloaded_file)
            if not opus_file:
                logger.error("轉換為 Opus 格式失敗")
                return None, None
                
            logger.info(f"成功下載並轉換為 Opus 格式: {opus_file}")
            return info, opus_file
        except Exception as e:
            logger.error(f"下載歌曲時發生錯誤：{e}")
            return None, None

    async def async_extract_info(self, url: str):
        """
        提供異步方式調用同步的 extract_info 方法
        :param url: str, 影片網址
        :return: dict or None
        """
        logger.debug(f"異步提取影片資訊: {url}")
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(executor, self.extract_info, url)

    async def async_download(self, url: str):
        """
        提供異步方式調用同步的 download 方法
        :param url: str, 影片網址
        :return: (dict, str) or (None, None)
        """
        logger.debug(f"異步下載影片: {url}")
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(executor, self.download, url)

    def clear_temp_files(self):
        """
        清空下載資料夾內的所有檔案
        """
        try:
            logger.info(f"清空暫存檔案，目錄: {self.download_folder}")
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
        # 需要提供 ffmpeg 路徑
        ffmpeg_path = input("請輸入 FFmpeg 執行檔路徑: ")
        yt_manager = YTDLPDownloader("./temp/music", ffmpeg_path)
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