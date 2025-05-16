import os
import subprocess
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from loguru import logger
import time

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
            
        # 初始化重試設定
        self.max_retries = 3
        
        # 初始化錯誤模式列表
        self.invalid_title_patterns = [
            "deleted video",
            "private video",
            "video unavailable"
        ]
        
        # 按類型分組
        self.error_patterns = [
            # 年齡限制
            "sign in to confirm your age",
            "age-restricted",
            "inappropriate for some users",
            
            # 私人/不公開影片
            "private video",
            "sign in if you've been granted access",
            
            # 版權/地區限制
            "copyright grounds",
            "blocked it",
            "content owner",
            "has blocked",
            "not available in your country",
            
            # 帳號問題
            "account associated with this video has been terminated",
            "account has been terminated",
            
            # 一般可用性問題
            "video unavailable",
            "this video is unavailable",
            "no longer available",
            "has been removed",
            
            # 其他錯誤
            "playable in embed"
        ]
            
        logger.info(f"YTDLPDownloader 初始化，下載資料夾: {self.download_folder}")

    def _is_valid_video(self, entry):
        """
        檢查影片是否有效（非刪除、非私人、非年齡限制、非版權限制）
        
        :param entry: dict, 影片資訊
        :return: bool, 影片是否有效
        """
        title = entry.get("title", "").lower()
        uploader = entry.get("uploader", "").lower()
        
        # 檢查已知的刪除或私人影片標記
        for pattern in self.invalid_title_patterns:
            if pattern.lower() in title:
                logger.warning(f"過濾無效影片 (標題含有 '{pattern}'): {title}")
                return False
                
        # 檢查空標題或空上傳者（通常表示影片不可用）
        if not title or title == "unknown title" or title == "未知標題":
            logger.warning(f"過濾無效影片 (標題為空或未知): {title}")
            return False
            
        if not uploader or uploader == "unknown uploader" or uploader == "未知上傳者":
            logger.warning(f"過濾無效影片 (上傳者為空或未知): {title}")
            return False
            
        # 檢查影片時長（通常被刪除的影片時長為0）
        if entry.get("duration", 0) == 0:
            logger.warning(f"過濾無效影片 (時長為0): {title}")
            return False
            
        return True

    def _pick_best_thumbnail(self, entry):
        """
        取得最佳縮圖：先抓 thumbnail，沒有就從 thumbnails 陣列選最大尺寸
        """
        thumb = entry.get("thumbnail")
        if not thumb and entry.get("thumbnails"):
            thumb = max(entry["thumbnails"], key=lambda t: t.get("width", 0) * t.get("height", 0)).get("url", "")
        return thumb or ""

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
            
            error_output = ""
            for line in iter(process.stdout.readline, ""):
                line = line.strip()
                if "[download]" in line:
                    print(f"\r{line}", end="")
                # 記錄錯誤輸出
                else:
                    error_output += line + "\n"
                    # 檢查是否有錯誤模式
                    lower_line = line.lower()
                    has_error = False
                    for pattern in self.error_patterns:
                        if pattern in lower_line:
                            error_type = self._detect_error_type(lower_line)
                            logger.error(f"影片無法下載 (含有錯誤模式 '{pattern}'): {line}")
                            process.terminate()
                            return False
                        
            process.stdout.close()
            return_code = process.wait()
            print()  # 確保下載完成後換行
            
            if return_code != 0:
                logger.error(f"yt-dlp 執行失敗: {error_output.strip()}")
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

    def _create_error_response(self, error_type, error_message, url=None, details=None):
        """
        建立標準化的錯誤回應
        
        :param error_type: str, 錯誤類型，如 'age_restricted', 'copyright', 'private', 'unavailable' 等
        :param error_message: str, 原始錯誤訊息
        :param url: str, 相關的 URL
        :param details: dict, 任何額外的錯誤詳情
        :return: dict, 標準化的錯誤回應
        """
        response = {
            "success": False,
            "error_type": error_type,
            "error_message": error_message,
            "display_message": self._get_user_friendly_message(error_type),
            "url": url,
            "timestamp": time.time()
        }
        
        if details:
            response["details"] = details
            
        return response
    
    def _get_user_friendly_message(self, error_type):
        """
        根據錯誤類型提供用戶友好的錯誤訊息
        
        :param error_type: str, 錯誤類型
        :return: str, 用戶友好的錯誤訊息
        """
        messages = {
            "age_restricted": "年齡限制",
            "copyright": "版權問題被阻擋",
            "private": "私人或不公開",
            "unavailable": "已不可用（可能已被刪除）",
            "account_terminated": "來源帳號已被終止",
            "region_blocked": "在您的地區無法觀看",
            "unknown": "未知原因"
        }
        return messages.get(error_type, "未知問題")
    
    def _detect_error_type(self, error_message):
        """
        根據錯誤訊息檢測具體錯誤類型
        
        :param error_message: str, 錯誤訊息
        :return: str, 錯誤類型
        """
        error_message = error_message.lower()
        
        # 年齡限制
        if any(phrase in error_message for phrase in ["sign in to confirm your age", "age-restricted", "inappropriate for some users"]):
            return "age_restricted"
            
        # 版權問題
        if any(phrase in error_message for phrase in ["copyright grounds", "blocked it", "content owner", "has blocked"]):
            return "copyright"
            
        # 地區限制
        if "not available in your country" in error_message:
            return "region_blocked"
            
        # 私人影片
        if any(phrase in error_message for phrase in ["private video", "sign in if you've been granted access"]):
            return "private"
            
        # 帳號終止
        if any(phrase in error_message for phrase in ["account associated with this video has been terminated", "account has been terminated"]):
            return "account_terminated"
            
        # 一般不可用
        if any(phrase in error_message for phrase in ["video unavailable", "this video is unavailable", "no longer available", "has been removed"]):
            return "unavailable"
            
        # 未知錯誤
        return "unknown"

    def _check_error_messages(self, error_msg: str, source_url: str):
        """
        檢查錯誤訊息中是否有特定錯誤模式
        
        :param error_msg: str, 錯誤訊息
        :param source_url: str, 來源 URL
        :return: tuple(bool, dict), (是否包含錯誤模式, 錯誤信息字典)
        """
        error_msg = error_msg.lower()
        
        for pattern in self.error_patterns:
            if pattern in error_msg:
                error_type = self._detect_error_type(error_msg)
                logger.warning(f"媒體無法使用 (含有錯誤模式 '{pattern}'): {source_url}")
                return True, self._create_error_response(error_type, error_msg, source_url)
        return False, None

    def _parse_video_data(self, data: dict):
        """
        解析影片資料並轉換為標準格式
        
        :param data: dict, 原始影片資料
        :return: dict or None, 標準格式的影片資料
        """
        # 檢查影片是否有效
        if not self._is_valid_video(data):
            logger.warning(f"跳過無效影片: {data.get('title', 'Unknown Title')}")
            return None
            
        thumb = self._pick_best_thumbnail(data)
        return {
            "id": data.get("id"),
            "title": data.get("title", "未知標題"),
            "uploader": data.get("uploader", "未知上傳者"),
            "uploader_url": data.get("channel_url", ""),
            "duration": data.get("duration", 0),
            "url": data.get("webpage_url", f"https://www.youtube.com/watch?v={data.get('id')}"),
            "thumbnail": thumb,
            "downloaded": False  # 標記是否已下載
        }
        
    def _run_yt_dlp_command(self, args: list, url: str):
        """
        執行 yt-dlp 命令並處理結果
        
        :param args: list, yt-dlp 命令參數
        :param url: str, 來源 URL
        :return: tuple(bool, str/list/dict), (成功與否, 輸出結果或錯誤資訊)
        """
        try:
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
                    return False, self._create_error_response("unknown", "yt-dlp 沒有輸出任何資訊", url)
                return True, output_lines
            else:
                error_msg = process.stderr.strip()
                logger.error(f"yt-dlp 執行失敗: {error_msg}")
                has_error, error_data = self._check_error_messages(error_msg, url)
                if has_error:
                    return False, error_data
                return False, self._create_error_response("unknown", error_msg, url)
        except Exception as e:
            logger.error(f"執行 yt-dlp 時發生錯誤: {e}")
            return False, self._create_error_response("unknown", str(e), url)

    def extract_info(self, url: str):
        """
        使用 subprocess 提取簡化的影片資訊
        :param url: str, 影片網址
        :return: dict or None - 成功時返回影片資訊，失敗時返回錯誤資訊
        """
        logger.info(f"提取影片資訊: {url}")
        args = [
            "yt-dlp",
            "--dump-json",
            "--quiet",
            "--no-warnings",
            url,
        ]
        
        success, result = self._run_yt_dlp_command(args, url)
        if not success:
            return result  # 此時 result 是錯誤資訊
            
        try:
            data = json.loads(result[0])
            info = self._parse_video_data(data)
            if info:
                logger.info(f"只取第一首: {info}")
                return info
            # 如果 parse 失敗，返回特定錯誤
            return self._create_error_response("parse_error", "解析影片資訊失敗", url)
        except Exception as e:
            logger.error(f"解析影片資訊時出錯: {e}")
            return self._create_error_response("parse_error", str(e), url)

    def extract_playlist_info(self, url: str):
        """
        提取播放清單的全部影片資訊
        :param url: str, 播放清單網址
        :return: list[dict] or dict - 成功時返回播放清單資訊，失敗時返回錯誤資訊
        """
        logger.info(f"提取播放清單資訊: {url}")
        args = [
            "yt-dlp",
            "--flat-playlist",  # 只提取清單資訊，不下載
            "--dump-json",
            "--quiet",
            "--no-warnings",
            url
        ]
        
        success, result = self._run_yt_dlp_command(args, url)
        if not success:
            return result  # 此時 result 是錯誤資訊
            
        try:
            playlist_entries = []
            filtered_count = 0
            error_entries = []
            
            for line in result:
                try:
                    entry = json.loads(line)
                    info = self._parse_video_data(entry)
                    if info:
                        playlist_entries.append(info)
                    else:
                        filtered_count += 1
                        # 記錄被過濾的項目
                        error_entries.append({
                            "title": entry.get("title", "未知標題"),
                            "reason": "無效影片"
                        })
                except Exception as e:
                    logger.error(f"處理播放清單項目時出錯: {e}")
                    filtered_count += 1
            
            if filtered_count > 0:
                logger.info(f"已從播放清單中過濾 {filtered_count} 首無效歌曲")
                
            if not playlist_entries:
                # 如果所有項目都被過濾，返回錯誤
                return self._create_error_response(
                    "empty_playlist", 
                    "播放清單中沒有可播放的歌曲", 
                    url, 
                    {"filtered_count": filtered_count, "error_entries": error_entries}
                )
                
            logger.info(f"已提取播放清單，共 {len(playlist_entries)} 首有效歌曲")
            return playlist_entries
        except Exception as e:
            logger.error(f"提取播放清單時發生錯誤: {e}")
            return self._create_error_response("playlist_error", str(e), url)

    def is_playlist(self, url: str):
        """
        判斷 URL 是否為播放清單
        :param url: str, 要檢查的 URL
        :return: bool - 是否為播放清單
        """
        return "playlist" in url or "list=" in url

    def download(self, url: str, retries=0):
        """
        使用 subprocess 下載影片並轉換為 Opus 格式
        :param url: str, 影片網址
        :param retries: int, 目前重試次數
        :return: (dict, str) or (dict, None) - 成功時返回 (影片資訊, 檔案路徑)，失敗時返回 (錯誤資訊, None)
        """
        try:
            # 檢查是否達到最大重試次數
            if retries >= self.max_retries:
                logger.error(f"下載嘗試次數已達上限 ({self.max_retries} 次)，放棄下載: {url}")
                return self._create_error_response("max_retries", f"下載嘗試次數已達上限 ({self.max_retries} 次)", url), None
                
            logger.info(f"開始下載影片: {url} (第 {retries+1} 次嘗試)")
            # 先取得第一首的 id
            info = self.extract_info(url)
            if isinstance(info, dict) and not info.get("success", True):
                # 如果 extract_info 返回錯誤資訊
                logger.error("無法取得影片資訊或 id")
                return info, None
                
            if not info or not info.get("id"):
                logger.error("無法取得影片資訊或 id")
                return self._create_error_response("invalid_info", "無法取得有效的影片資訊", url), None
                
            # 如果已經下載了這首歌，檢查文件是否存在
            opus_path = os.path.join(self.download_folder, f"{info['id']}.opus")
            if os.path.exists(opus_path):
                logger.info(f"歌曲已存在，無需重新下載: {info['title']}")
                info["downloaded"] = True
                return info, opus_path
                
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
                # 嘗試重試
                return self.download(url, retries + 1)
                
            # 查找下載的檔案
            downloaded_file = self._find_downloaded_file(info["id"])
            if not downloaded_file:
                logger.error("找不到下載的檔案")
                # 嘗試重試
                return self.download(url, retries + 1)
                
            # 轉換為 Opus 格式
            opus_file = self._convert_to_opus(downloaded_file)
            if not opus_file:
                logger.error("轉換為 Opus 格式失敗")
                # 嘗試重試
                return self.download(url, retries + 1)
                
            logger.info(f"成功下載並轉換為 Opus 格式: {opus_file}")
            info["downloaded"] = True
            return info, opus_file
        except Exception as e:
            logger.error(f"下載歌曲時發生錯誤：{e}")
            # 嘗試重試
            if retries < self.max_retries:
                logger.info(f"嘗試第 {retries+2} 次下載...")
                return self.download(url, retries + 1)
            return self._create_error_response("download_error", str(e), url), None

    def _find_downloaded_file(self, file_id):
        """
        根據檔案ID在下載資料夾中尋找下載的原始檔案
        
        :param file_id: str, 檔案ID
        :return: str or None, 找到的檔案完整路徑或None
        """
        for file in os.listdir(self.download_folder):
            if file.startswith(file_id) and not file.endswith(".opus"):
                file_path = os.path.join(self.download_folder, file)
                logger.info(f"找到下載的原始檔案: {file_path}")
                return file_path
        return None

    async def async_extract_info(self, url: str, timeout: int = 30):
        """
        提供異步方式調用同步的 extract_info 方法，並加上 timeout
        :param url: str, 影片網址
        :param timeout: int, 超時秒數
        :return: dict or None
        """
        logger.debug(f"異步提取影片資訊: {url}")
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            try:
                return await asyncio.wait_for(loop.run_in_executor(executor, self.extract_info, url), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error(f"提取影片資訊超時: {url}")
                return None
    
    async def async_extract_playlist_info(self, url: str, timeout: int = 60):
        """
        提供異步方式調用同步的 extract_playlist_info 方法，並加上 timeout
        :param url: str, 播放清單網址
        :param timeout: int, 超時秒數
        :return: list[dict] or None
        """
        logger.debug(f"異步提取播放清單資訊: {url}")
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            try:
                return await asyncio.wait_for(loop.run_in_executor(executor, self.extract_playlist_info, url), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error(f"提取播放清單資訊超時: {url}")
                return None

    async def async_download(self, url: str, timeout: int = 120):
        """
        提供異步方式調用同步的 download 方法，並加上 timeout
        :param url: str, 影片網址
        :param timeout: int, 超時秒數
        :return: (dict, str) or (None, None)
        """
        logger.debug(f"異步下載影片: {url}")
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            try:
                return await asyncio.wait_for(loop.run_in_executor(executor, self.download, url), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error(f"下載影片超時: {url}")
                return None, None

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

        # 檢查是否為播放清單
        if yt_manager.is_playlist(url):
            print("\n提取播放清單資訊:")
            try:
                playlist_info = await yt_manager.async_extract_playlist_info(url)
                if playlist_info:
                    print(f"找到 {len(playlist_info)} 首有效歌曲")
                    for i, entry in enumerate(playlist_info[:5], 1):
                        print(f"{i}. {entry['title']}")
                    if len(playlist_info) > 5:
                        print(f"... 還有 {len(playlist_info)-5} 首歌曲")
                else:
                    print("播放清單中沒有有效的歌曲")
            except Exception as e:
                print(f"提取播放清單失敗: {e}")
        else:
            print("\n提取單曲資訊:")
        try:
            info = await yt_manager.async_extract_info(url)
            if info:
                print(json.dumps(info, indent=4, ensure_ascii=False))
            else:
                print("無法提取有效的影片資訊，可能是私人或已刪除的影片")
        except Exception as e:
            print(f"提取資訊失敗: {e}")

        print("\n下載並提取資訊:")
        try:
            info, filepath = await yt_manager.async_download(url)
            if info and filepath:
                print(f"下載完成: {filepath}")
                print(json.dumps(info, indent=4, ensure_ascii=False))
            else:
                print("無法下載影片，可能是私人、已刪除或有年齡限制的影片")
        except Exception as e:
            print(f"下載失敗: {e}")

    asyncio.run(test())