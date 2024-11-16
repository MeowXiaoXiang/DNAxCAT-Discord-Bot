import os
import platform
import zipfile
import tarfile
import time
import aiohttp
import asyncio
from loguru import logger

def format_size(size):
    """格式化顯示大小：KB、MB、GB"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

def format_time(seconds):
    """格式化顯示時間"""
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}分{seconds}秒"

async def async_download_ffmpeg_with_status(url, file_name):
    """非同步下載文件並顯示進度"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                total_size = int(response.headers['Content-Length'])
                block_size = 1024
                downloaded = 0
                start_time = time.time()

                with open(file_name, 'wb') as f:
                    while True:
                        chunk = await response.content.read(block_size)
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        f.write(chunk)

                        percent = int(downloaded * 100 / total_size)
                        elapsed_time = time.time() - start_time
                        speed = downloaded / elapsed_time if elapsed_time > 0 else 0
                        speed_str = f"{speed / 1024:.2f} KB/s"
                        downloaded_str = f"{downloaded / 1024 / 1024:.2f} MB"
                        total_str = f"{total_size / 1024 / 1024:.2f} MB"
                        time_str = format_time(elapsed_time)
                        print(f"\r下載中: [{percent}%] 速度: {speed_str}，已下載: {downloaded_str} / {total_str}，耗時: {time_str}", end="")

                print(f"\n下載完成: {total_str}")
                return 0  # 成功狀態碼
    except Exception as e:
        logger.error(f"下載失敗: {e}")
        return 1  # 失敗狀態碼

async def async_check_and_download_ffmpeg():
    """檢查並非同步下載 ffmpeg"""
    # 設定平台特定的下載路徑
    system = platform.system()
    base_dir = os.path.join("module", "ffmpeg", system)
    os.makedirs(base_dir, exist_ok=True)

    # 設定 ffmpeg 路徑
    ffmpeg_path = os.path.join(base_dir, "ffmpeg")
    if system == "Windows":
        ffmpeg_path += ".exe"

    # 如果 ffmpeg 已存在
    if os.path.exists(ffmpeg_path):
        logger.info("ffmpeg 已存在於指定路徑。")
        return 0  # 已存在表示成功

    # 設定下載 URL 和本地檔案路徑
    if system == "Windows":
        url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        file_name = os.path.join(base_dir, "ffmpeg.zip")
    elif system == "Linux":
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-i686-static.tar.xz"
        file_name = os.path.join(base_dir, "ffmpeg.tar.xz")
    else:
        logger.error("此作業系統不支援自動下載 ffmpeg。")
        return 1  # 無法下載表示失敗

    # 開始下載
    logger.info("正在下載 ffmpeg...")
    status = await async_download_ffmpeg_with_status(url, file_name)
    if status == 1:
        return 1  # 下載失敗

    # 解壓縮
    logger.info("正在解壓縮 ffmpeg...")
    try:
        if file_name.endswith(".zip"):
            with zipfile.ZipFile(file_name, "r") as zip_ref:
                zip_ref.extractall(base_dir)
                extracted_dir = os.path.join(base_dir, zip_ref.namelist()[0])
        elif file_name.endswith(".tar.xz"):
            with tarfile.open(file_name, "r:xz") as tar_ref:
                tar_ref.extractall(base_dir)
                extracted_dir = os.path.join(base_dir, tar_ref.getnames()[0])

        # 移動 ffmpeg 可執行檔
        if system == "Windows":
            os.rename(os.path.join(extracted_dir, "bin", "ffmpeg.exe"), ffmpeg_path)
        else:
            os.rename(os.path.join(extracted_dir, "ffmpeg"), ffmpeg_path)
        logger.info("ffmpeg 已成功解壓並移至指定路徑。")

        # 清理下載的壓縮檔和臨時解壓資料夾
        os.remove(file_name)
        if os.path.exists(extracted_dir):
            for root, dirs, files in os.walk(extracted_dir, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            os.rmdir(extracted_dir)
        logger.info("清理臨時檔案完成。")

        return 0  # 成功狀態碼

    except Exception as e:
        logger.error(f"解壓縮失敗: {e}")
        return 1  # 解壓縮失敗狀態碼

# 僅在此檔案直接執行時才運行
if __name__ == "__main__":
    status = asyncio.run(async_check_and_download_ffmpeg())
    if status == 0:
        logger.info("ffmpeg 下載與設置完成。")
    else:
        logger.error("ffmpeg 下載或設置失敗。")
