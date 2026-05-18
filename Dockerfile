# Build v5 — force Zeabur rebuild
FROM python:3.11-slim

WORKDIR /app

# 先裝依賴（利用 Docker cache）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製所有檔案
COPY . .

# 建立快取目錄
RUN mkdir -p stations_data

EXPOSE 8080

CMD ["python", "main.py"]
