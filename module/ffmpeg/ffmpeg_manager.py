import os
import shutil
import platform
import zipfile
import tarfile
import time
import aiohttp
import asyncio
from loguru import logger

def format_size(size):
    """
    格式化顯示檔案大小。

    :param size: int, 檔案大小（以位元組為單位）。
    :return: str, 格式化後的檔案大小（如 KB、MB）。
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} GB"

def format_time(seconds):
    """
    格式化顯示時間。

    :param seconds: int, 時間秒數。
    :return: str, 格式化後的時間（如 "5分30秒"）。
    """
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}分{seconds}秒"

def detect_platform():
    """
    檢測作業系統。

    :return: str or None, 若系統為 Windows 或 Linux，回傳系統名稱；否則回傳 None。
    """
    system = platform.system()
    if system not in ["Windows", "Linux"]:
        logger.error("此作業系統不支援自動下載 ffmpeg。")
        return None
    return system

def _get_ffmpeg_paths(system):
    """
    根據系統回傳 FFmpeg 的路徑與下載資訊。

    :param system: str, 系統名稱（"Windows" 或 "Linux"）。
    :return: tuple, 包含 FFmpeg 可執行檔路徑、下載 URL、壓縮檔案路徑、基礎目錄。
    """
    base_dir = os.path.join("module", "ffmpeg", system)
    os.makedirs(base_dir, exist_ok=True)

    ffmpeg_path = os.path.join(base_dir, "ffmpeg")
    if system == "Windows":
        ffmpeg_path += ".exe"

    if system == "Windows":
        download_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        file_name = os.path.join(base_dir, "ffmpeg.zip")
    elif system == "Linux":
        download_url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-i686-static.tar.xz"
        file_name = os.path.join(base_dir, "ffmpeg.tar.xz")

    return ffmpeg_path, download_url, file_name, base_dir

async def _download_ffmpeg_with_status(url, file_name):
    """
    非同步下載 FFmpeg 並顯示下載進度。

    :param url: str, 下載 URL。
    :param file_name: str, 本地存檔名稱。
    :return: int, 成功回傳 0，失敗回傳 1。
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"下載失敗，HTTP 狀態碼: {response.status}")
                    return 1

                total_size = int(response.headers.get('Content-Length', 0))
                block_size = 64 * 1024  # 每次讀取 64 KB
                downloaded = 0
                start_time = time.time()

                with open(file_name, 'wb') as f:
                    while True:
                        chunk = await response.content.read(block_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        elapsed_time = time.time() - start_time
                        percent = downloaded / total_size * 100 if total_size else 0
                        speed = downloaded / elapsed_time if elapsed_time > 0 else 0
                        print(f"\r下載中: [{percent:.2f}%] 速度: {format_size(speed)}/s，已下載: {format_size(downloaded)}，已用時間: {format_time(elapsed_time)}", end="    ")

                elapsed_time = time.time() - start_time
                print(f"\n下載完成: {format_size(total_size)}，耗時: {format_time(elapsed_time)}")
                return 0
    except Exception as e:
        logger.error(f"下載失敗: {e}")
        return 1

def _extract_ffmpeg(file_name, base_dir, system):
    """
    解壓縮 FFmpeg 壓縮檔並設置可執行檔。

    :param file_name: str, 壓縮檔路徑。
    :param base_dir: str, 解壓目錄。
    :param system: str, 系統名稱（"Windows" 或 "Linux"）。
    :return: int, 成功回傳 0，失敗回傳 1。
    """
    try:
        extracted_dir = None
        if file_name.endswith(".zip"):
            with zipfile.ZipFile(file_name, "r") as zip_ref:
                zip_ref.extractall(base_dir)
                extracted_dir = os.path.join(base_dir, zip_ref.namelist()[0])
        elif file_name.endswith(".tar.xz"):
            with tarfile.open(file_name, "r:xz") as tar_ref:
                tar_ref.extractall(base_dir)
                extracted_dir = os.path.join(base_dir, tar_ref.getnames()[0])

        ffmpeg_path = os.path.join(base_dir, "ffmpeg")
        if system == "Windows":
            os.rename(os.path.join(extracted_dir, "bin", "ffmpeg.exe"), ffmpeg_path + ".exe")
        else:
            os.rename(os.path.join(extracted_dir, "ffmpeg"), ffmpeg_path)

        logger.info("ffmpeg 已成功解壓並移至指定路徑。")
        os.remove(file_name)

        if extracted_dir and os.path.exists(extracted_dir):
            shutil.rmtree(extracted_dir)

        logger.info("清理臨時檔案完成。")
        return 0
    except Exception as e:
        logger.error(f"解壓縮失敗: {e}")
        return 1

async def check_and_download_ffmpeg():
    """
    主邏輯：檢查 FFmpeg 是否存在，若不存在則下載並設置。

    :return: dict, 包含以下鍵值：
        - "status_code" (int): 狀態碼，0 表示成功，1 表示失敗。
        - "relative_path" (str): 相對路徑，例如 "module/ffmpeg/Windows/ffmpeg.exe"。
        - "absolute_path" (str): 絕對路徑，例如 "/absolute/path/to/module/ffmpeg/Windows/ffmpeg.exe"。
    """
    system = detect_platform()
    if not system:
        return {
            "status_code": 1,
            "relative_path": None,
            "absolute_path": None
        }

    ffmpeg_path, download_url, file_name, base_dir = _get_ffmpeg_paths(system)

    if os.path.exists(ffmpeg_path):
        logger.info("ffmpeg 已存在於指定路徑。")
        return {
            "status_code": 0,
            "relative_path": os.path.relpath(ffmpeg_path),
            "absolute_path": os.path.abspath(ffmpeg_path)
        }

    logger.info("正在下載 ffmpeg...")
    if await _download_ffmpeg_with_status(download_url, file_name) == 1:
        return {
            "status_code": 1,
            "relative_path": None,
            "absolute_path": None
        }

    logger.info("正在解壓縮 ffmpeg...")
    if _extract_ffmpeg(file_name, base_dir, system) == 1:
        return {
            "status_code": 1,
            "relative_path": None,
            "absolute_path": None
        }

    return {
        "status_code": 0,
        "relative_path": os.path.relpath(ffmpeg_path),
        "absolute_path": os.path.abspath(ffmpeg_path)
    }

if __name__ == "__main__":
    async def main():
        """
        測試主邏輯，檢查檔案路徑與下載流程是否正常。
        """
        result = await check_and_download_ffmpeg()
        if result["status_code"] == 0:
            print(f"FFmpeg 已成功設置：\n相對路徑: {result['relative_path']}\n絕對路徑: {result['absolute_path']}")
        else:
            print("FFmpeg 下載或設置失敗。")

    asyncio.run(main())
