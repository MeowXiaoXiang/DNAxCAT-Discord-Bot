# DNAxCAT_DiscordBot

![Python 3.10](https://img.shields.io/badge/Python-3.10-blue?logo=python) ![Version v1.0](https://img.shields.io/badge/Version-v1.0-orange)

## 介紹

DNAxCAT Discord Bot 是一個多功能的 Discord 機器人，提供井字遊戲、音樂播放和論壇通知功能。

## 安裝

在開始使用這個 Bot 之前，你需要安裝一些必要的 Python 套件。你可以使用以下的指令來安裝這些套件：

```bash
pip install -r requirements.txt
```

## 功能介紹

- `tic_tac_toe`: 這個功能是在 Discord 中進行井字遊戲。玩家使用表情符號進行操作，機器人會管理遊戲狀態和回合，並處理勝負判定。
- `music`: 這個功能是在 Discord 中作為 YouTube 音樂播放器的功能。
- `forum_notifier`: 這個功能會定期檢查指定論壇的文章，並在有新文章時發送通知。
- `avatar`: 這個功能可以顯示目標成員的頭貼。
- `minesweeper`: 這個功能可以在 Discord 中進行踩地雷遊戲。

## 專案目錄組成

- `cogs/`: 存放機器人功能模組的目錄。
  - `avatar.py`: 顯示成員頭貼功能模組。
  - `common.py`: 一些通用功能模組。
  - `forum_notifier.py`: 論壇通知功能模組。
  - `minesweeper.py`: 踩地雷遊戲功能模組。
  - `tic_tac_toe.py`: 井字遊戲功能模組。
  - `music_player.py`: 音樂播放器，僅支援 Youtube，目前不穩暫時擺放至 `cogs_disabled` 資料夾中存放。
- `config/setting.json`: 設定檔案，包含機器人的 Discord Bot TOKEN 及其他設定。
- `module/ffmpeg`: 存放 ffmpeg 相關檔案的目錄。
- `logs/`: 存放日誌檔案的目錄。
- `music_downloads/`: 存放下載的音樂檔案的目錄。
- `tests/`: 存放測試檔案的目錄。

## 設定

- `config/settings.json` 檔案，包含以下設定：
  - `forum_notifier`: 論壇通知功能的設定。
    - `channel_id`: 發送通知的頻道 ID。
    - `interval_minutes`: 檢查新文章的間隔時間（分鐘）。
    - `base_url`: 論壇的基礎 URL。
    - `forums`: 包含各個論壇的 URL 和顏色設定。
- `.env` 檔案，包含以下設定：
  - `DISCORD_BOT_TOKEN`: 設定機器人的 Discord Bot TOKEN。
  - `DEBUG`: 設定是否啟用 DEBUG 模式。

## Docker 用法

你可以使用 Docker 來運行這個專案。以下是 Docker 的使用方法：

1. 建立 Docker 映像：

```bash
docker build -t dnaxcat_discord_bot .
```

2. 運行 Docker 容器：

```bash
docker run -d --name dnaxcat_discord_bot -e DISCORD_BOT_TOKEN=你的token -e DEBUG=false dnaxcat_discord_bot
```

這樣就可以在 Docker 容器中運行 DNAxCAT Discord Bot 了。