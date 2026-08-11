FROM python:3.10-slim

WORKDIR /app

# 기본 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 스크립트를 주기적으로 실행하기 위한 커맨드
# Railway cron 기능 또는 apscheduler를 사용할 경우 수정될 수 있습니다.
# 현재는 1회 실행 후 종료(크론 잡용)하도록 설정
CMD ["python", "main.py"]
