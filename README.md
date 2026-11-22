# 🤖 영대소식 알림 봇 (YU Notice Bot)

영남대학교의 다양한 학과 공지사항을 실시간 크롤링하여, 사용자가 선택한 전공에 맞게 개인화된 텔레그램 알림을 발송하고 중요 공지를 스크랩 보관할 수 있는 서비스입니다.

---

## ✨ 주요 기능
* **학과 맞춤형 공지 발송**: 영대소식을 비롯하여 컴퓨터학부, SW중심대학, 전자공학, 기계공학 등 사용자가 구독한 카테고리만 필터링해 발송합니다.
* **중복 알림 방지**: 게시글 고유 번호(`articleNo`) 집합을 대조하여 상단 고정 공지로 인한 중복 알림을 차단합니다.
* **텔레그램 미니앱 연동**: 톡방 내 웹앱 화면을 통해 알림 구독 설정(ON/OFF) 및 스크랩 보관함을 손쉽게 관리할 수 있습니다.
* **Supabase DB 연동**: 구독 정보 및 스크랩 데이터를 안전한 클라우드 데이터베이스에 실시간 동기화합니다.
* **관리자 장애 경보**: 크롤링 실패 등 비정상 동작 감지 시, 관리자 계정으로 실시간 장애 로그 경보를 즉시 자동 발송합니다.

---

## 📂 파일 구조
* `telegram_bot.py`: 크롤링, DB 연동 및 알림 발송 메인 백엔드
* `index.html`: 설정 및 스크랩 보관함 관리용 텔레그램 미니앱 프론트엔드
* `last_notices.json`: 중복 수집 필터링용 직전 공지 ID 캐시
* `.gitignore`: 보안 기밀 파일의 깃허브 업로드 차단 설정
* `.env`: 토큰 및 DB 정보 등 보안 환경변수 격리 보관 파일

---

## 🚀 가동 및 설정 방법

### 1. 환경변수(.env) 설정
프로젝트 폴더 내에 `.env` 파일을 생성하고 기밀 정보를 입력합니다:
```env
TELEGRAM_TOKEN=your_telegram_token
ADMIN_CHAT_ID=your_chat_id
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
WEBAPP_URL=https://<your_github_username>.github.io/<your_repository_name>/
```

### 2. 패키지 설치
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3. 상시 실행 서비스 등록 (systemd)
봇은 항상 실행되며 `/start`, `/menu`에 즉시 응답하고, 공지 수집은 평일 9:00 ~ 17:50에 10분 간격으로 수행합니다.
```bash
sudo cp deploy/yu-notice-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now yu-notice-bot
```

### 4. 테스트
```bash
python3 -m unittest discover -s tests -v
```
