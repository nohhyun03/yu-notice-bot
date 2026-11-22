# 🤖 영대소식 알림 봇 (YU Notice Bot)

영남대학교의 다양한 학과 공지사항을 실시간 크롤링하여, 사용자가 선택한 전공에 맞게 개인화된 텔레그램 알림을 발송하고 중요 공지를 스크랩 보관할 수 있는 서비스입니다.

---

## ✨ 주요 기능
* **학과 맞춤형 공지 발송**: 영대소식을 비롯하여 컴퓨터학부, SW중심대학, 전자공학, 기계공학 등 사용자가 구독한 카테고리만 필터링해 발송합니다.
* **중복 알림 방지**: 게시글 고유 번호(`articleNo`) 집합을 대조하여 상단 고정 공지로 인한 중복 알림을 차단합니다.
* **채팅에서 바로 스크랩**: 새 공지 메시지의 "📌 스크랩" 버튼을 누르면 화면 전환 없이 보관함에 저장됩니다.
* **텔레그램 미니앱**: `https://bot.nohhyun.me` 에서 알림 구독 설정(ON/OFF)과 스크랩 보관함을 관리합니다. 모든 요청은 텔레그램 서명(`initData`)을 서버에서 검증합니다.
* **서버 내 SQLite 저장소**: 구독 정보와 스크랩은 서버의 `data.db`에 저장되며 매일 백업됩니다.
* **관리자 장애 경보**: 크롤링 실패 시 한 번, 복구 시 한 번 관리자에게 알립니다.

---

## 📂 파일 구조
* `telegram_bot.py`: 크롤링, 알림 발송, 텔레그램 폴링, 미니앱 API 기동 (상시 실행)
* `bot_schedule.py`: 수집 시각 계산 (평일 9:00 ~ 17:50, 10분 간격)
* `db.py`: SQLite 저장소 (구독자, 스크랩, 발송한 공지)
* `auth.py`: 텔레그램 `initData` 서명 검증
* `api.py`: 미니앱용 API (`/api/...`)
* `web/index.html`: 텔레그램 미니앱 프론트엔드
* `scripts/backup_db.py`: SQLite DB 백업
* `deploy/`: systemd 서비스, nginx 설정, 백업 cron, 옛 GitHub Pages 안내 페이지
* `last_notices.json`: 중복 수집 필터링용 직전 공지 ID 캐시
* `.env`: 토큰 등 환경변수 (git 제외)

---

## 🚀 가동 및 설정 방법

### 1. 환경변수(.env) 설정
```env
TELEGRAM_TOKEN=your_telegram_token
ADMIN_CHAT_ID=your_chat_id
WEBAPP_URL=https://bot.nohhyun.me/
```

### 2. 패키지 설치
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3. 상시 실행 서비스 등록 (systemd)
봇은 항상 실행되며 `/start`, `/menu`에 즉시 응답하고, 공지 수집은 평일 9:00 ~ 17:50에 10분 간격으로 수행합니다. 미니앱 API는 `127.0.0.1:8080`에서 대기하고 nginx가 `/api/`를 전달합니다.
```bash
sudo cp deploy/yu-notice-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now yu-notice-bot
```

### 4. nginx와 백업
* nginx: `deploy/nginx-bot.nohhyun.me.conf` 내용을 HTTPS 서버 블록에 반영
* 백업: `sudo cp deploy/yu-notice-bot-backup.cron /etc/cron.d/yu-notice-bot-backup` (매일 03:00, 14개 보관)

### 5. 테스트
```bash
python3 -m unittest discover -s tests -v
```
