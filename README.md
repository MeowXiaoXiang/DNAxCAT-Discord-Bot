# DNAxCAT_DiscordBot

![Python 3.10](https://img.shields.io/badge/Python-3.10-blue?logo=python) ![Version v1.0](https://img.shields.io/badge/Version-v1.0-orange)

## 介紹

DNAxCAT Discord Bot 是一個多功能的 Discord 機器人，提供井字遊戲和音樂播放功能。

## 安裝

在開始使用這個 Bot 之前，你需要安裝一些必要的 Python 套件。你可以使用以下的指令來安裝這些套件：

```bash
pip install -r requirements.txt
```

## 功能介紹

- `tic_tac_toe`: 這個功能是在 Discord 中進行井字遊戲。玩家使用表情符號進行操作，機器人會管理遊戲狀態和回合，並處理勝負判定。
- `music`: 這個功能是在 Discord 中作為 YouTube 音樂播放器的功能。

## 專案目錄組成

- `cogs/`: 存放機器人功能模組的目錄。
  - `music_player.py`: 音樂播放器功能模組。
  - `tic_tac_toe.py`: 井字遊戲功能模組。
- `config/setting.json`: 設定檔案，包含機器人的 Discord Bot TOKEN。
- `module/ffmpeg`: 存放 ffmpeg 相關檔案的目錄。
- `logs/`: 存放日誌檔案的目錄。
- `music_downloads/`: 存放下載的音樂檔案的目錄。
- `tests/`: 存放測試檔案的目錄。

## 設定

- `config/setting.json` 檔案，除了 `TOKEN` 使用字串外，其他請都使用整數：
  - `TOKEN`：設定機器人的 Discord Bot TOKEN。