# 使用 Python 3.10 的官方 Docker 映像作為基礎映像
FROM python:3.10

# 設定工作目錄
WORKDIR /app

# 把 requirements.txt 複製到 Docker 容器中
COPY requirements.txt .

# 透過 pip 安裝 requirements.txt 中列出的所有依賴項
RUN pip install -r requirements.txt

# 將你的專案代碼複製到 Docker 容器中
COPY . .

# Docker 容器啟動時，運行 main.py
CMD ["python", "main.py"]