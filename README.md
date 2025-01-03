# DNAxCAT_DiscordBot

![Python 3.10](https://img.shields.io/badge/Python-3.10-blue?logo=python) ![Version v1.0](https://img.shields.io/badge/Version-v1.0-orange)

## 介紹

DNAxCAT Discord Bot 是一款多功能 Discord 機器人，專為提升伺服器互動性與管理效率設計，提供從遊戲互動到論壇通知的多樣化功能。

---

## **功能介紹**

- **頭貼顯示 (avatar.py)**:  
  顯示伺服器成員的頭像，並根據頭像的平均顏色自動調整嵌入消息的顏色，展現細緻的技術應用。

- **常用連結 (common.py)**:  
  集合九藏喵窩的官方網站、論壇、動畫 YouTube 頻道與 Wiki 等連結，便於伺服器成員快速查閱相關資訊。

- **論壇通知 (forum_notifier.py)**:  
  利用爬蟲技術檢查指定論壇的新貼文，並將新文章的標題與連結公告至指定頻道，確保伺服器成員不錯過重要資訊。

- **踩地雷 (minesweeper.py)**:  
  在 Discord 中進行踩地雷遊戲，利用消息中的隱藏標籤模擬遊戲，但因 Discord 的限制，目前為靜態操作。

- **音樂播放 (music_cog.py)**:  
  作為 YouTube 音樂播放器，支援播放、暫停、停止與播放清單管理。  
  - **技術亮點**:  
    - 使用 `yt-dlp` 下載音樂並存入暫存目錄，離開頻道時自動清理。  
    - 利用 `ffmpeg` 處理音樂文件並實現播放。  

- **井字遊戲 (tic_tac_toe.py)**:  
  一款小型井字遊戲，玩家通過點擊表情符號選擇位置，機器人會管理回合並自動判定勝負。

---

## **專案目錄結構**

- **`cogs/`**: 存放主要功能模組。  
  - `avatar.py`: 頭貼顯示與顏色調整功能。  
  - `common.py`: 常用連結指令功能模組。  
  - `forum_notifier.py`: 論壇通知模組，包含爬蟲邏輯。  
  - `minesweeper.py`: 踩地雷遊戲模組。  
  - `music_cog.py`: 音樂播放功能模組。  
  - `tic_tac_toe.py`: 井字遊戲功能模組。  

- **`module/`**: 功能支援模組。  
  - `forum_notifier/`: 包含爬蟲與資料管理邏輯。  
  - `music_player/`: 音樂播放的核心邏輯與管理模組。  

- **`config/`**: 配置檔案。  
  - `settings.json`: 包含論壇通知與機器人參數設定。  
- **`logs/`**: 日誌檔案目錄，用於記錄執行過程（自動生成）。  
- **`data/`**: 持久化數據存儲目錄（自動生成）。  
- **`temp/music/`**: 暫存音樂文件目錄（自動生成）。  

---

## **安裝與使用**

### **安裝必要套件**
請確保已安裝 Python 3.10 或以上版本，並執行以下指令安裝必要的依賴套件：

```bash
pip install -r requirements.txt
```

### 所需配置設定

- `config/settings.json` 檔案，包含以下設定：
  - `forum_notifier`: 論壇通知功能的設定。
    - `channel_id`: 發送通知的頻道 ID。
    - `interval_minutes`: 檢查新文章的間隔時間（分鐘）。
    - `base_url`: 論壇的基礎 URL。
    - `forums`: 包含各個論壇的 URL 和顏色設定。
- `.env` 檔案，包含以下設定：
  - `DISCORD_BOT_TOKEN`: 設定機器人的 Discord Bot TOKEN。
  - `DEBUG`: 設定是否啟用 DEBUG 模式。

### 使用

- 啟動機器人：

  ```bash
  python main.py
  ```

## Docker

你可以使用 Docker 來運行這個專案。以下是 Docker 的使用方法：

1. 建立 Docker 映像（建立前請先設定好 `config/settings.json`）：

```bash
docker build -t dnaxcat_discord_bot .
```

2. 運行 Docker 容器：

```bash
docker run -d --name dnaxcat_discord_bot -e DISCORD_BOT_TOKEN=你的token -e DEBUG=false dnaxcat_discord_bot
```

這樣就可以在 Docker 容器中運行 DNAxCAT Discord Bot 了。