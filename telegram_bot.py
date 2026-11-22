import asyncio
import json
import requests
import os
import signal
import time
import sys
import logging
import urllib.parse
from datetime import datetime
from logging.handlers import RotatingFileHandler
from aiohttp import web
from bs4 import BeautifulSoup
from dotenv import load_dotenv

import api
import db
from bot_schedule import KST, next_run_time

# ==========================================
# 0. 로깅 시스템 구축
# ==========================================
LOG_FILE = "bot_run.log"

logger = logging.getLogger("telegram_bot")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# ==========================================
# 1. 설정 정보 및 파일 경로 정의
# ==========================================
# 로컬/서버 내 .env 파일 로드
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
LAST_NOTICES_FILE = "last_notices.json"

# 관리자 Chat ID
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# 미니 앱 URL
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://bot.nohhyun.me/")

# 구독/스크랩 데이터 SQLite 파일
DB_PATH = os.getenv("DB_PATH", "data.db")

# 미니 앱 API (nginx가 /api/ 를 여기로 전달)
API_HOST = "127.0.0.1"
API_PORT = 8080

BOOKMARK_ANSWERS = {
    "added": "📌 스크랩 완료",
    "exists": "이미 보관함에 있는 공지입니다",
    "missing": "스크랩할 수 없는 공지입니다",
}

CATEGORIES = {
    "general": {
        "name": "영대소식(학교공지)",
        "url": "https://gendereq.yu.ac.kr/main/intro/yu-news.do?mode=list&&articleLimit=10&article.offset=0",
        "host": "https://gendereq.yu.ac.kr"
    },
    "computer_dept": {
        "name": "컴퓨터학부 공지사항",
        "url": "https://www.yu.ac.kr/computer/notice/notice.do?mode=list&&articleLimit=10&article.offset=0",
        "host": "https://www.yu.ac.kr"
    },
    "computer_major": {
        "name": "컴퓨터공학전공 공지사항",
        "url": "https://www.yu.ac.kr/cse/community/notice.do?mode=list&&articleLimit=10&article.offset=0",
        "host": "https://www.yu.ac.kr"
    },
    "sw_edu": {
        "name": "SW중심대학사업단 공지사항",
        "url": "https://www.yu.ac.kr/swedu/notice/notice.do?mode=list&&articleLimit=10&article.offset=0",
        "host": "https://www.yu.ac.kr"
    },
    "electronics": {
        "name": "전자공학과 공지사항",
        "url": "https://www.yu.ac.kr/electronics/community/notice.do?mode=list&&articleLimit=10&article.offset=0",
        "host": "https://www.yu.ac.kr"
    },
    "mechanical": {
        "name": "기계공학과 공지사항",
        "url": "https://www.yu.ac.kr/me/notice/notice.do?mode=list&&articleLimit=10&article.offset=0",
        "host": "https://www.yu.ac.kr"
    },
    "economics": {
        "name": "경제금융학과 공지사항",
        "url": "https://www.yu.ac.kr/econ/dept/undergrad-notice.do?mode=list&&articleLimit=10&article.offset=0",
        "host": "https://www.yu.ac.kr"
    }
}

# ==========================================
# 2. 데이터 입출력 함수
# ==========================================
def load_subscribers_from_db():
    try:
        return db.list_subscribers()
    except Exception as e:
        logger.error(f"⚠️ 구독자 데이터 로드 실패: {e}")
        return []

def load_last_notices():
    if not os.path.exists(LAST_NOTICES_FILE):
        return {}
    try:
        with open(LAST_NOTICES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"⚠️ 이전 공지 파일 로드 오류: {e}")
        return {}

def save_last_notices(data):
    try:
        with open(LAST_NOTICES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"⚠️ 이전 공지 파일 저장 오류: {e}")

# ==========================================
# 3. 텔레그램 WebApp 버튼 발송
# ==========================================
def send_menu(token, chat_id):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    keyboard = {
        "inline_keyboard": [
            [{"text": "⚙️ 알림 설정 및 보관함 열기", "web_app": {"url": WEBAPP_URL}}]
        ]
    }
    
    payload = {
        "chat_id": chat_id,
        "text": (
            "<b>🔔 [알림 설정 및 스크랩 보관함 메뉴]</b>\n\n"
            "아래 버튼을 터치하시면 **구독 설정 및 스크랩 보관함** 창이 열립니다.\n"
            "이전 구독 내역 복원은 물론, 보관해 둔 중요 공지목록을 모아보실 수 있습니다."
        ),
        "parse_mode": "HTML",
        "reply_markup": json.dumps(keyboard)
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"⚠️ 메뉴 발송 오류 (Chat ID: {chat_id}): {e}")

# ==========================================
# 4. 실시간 대화식 명령어 처리
# ==========================================
def handle_bookmark_callback(token, callback_query):
    # The user id comes from Telegram's update, so a scrap can only be saved for the person who tapped.
    chat_id = str(callback_query["from"]["id"])
    notice_id = db.parse_bookmark_data(callback_query.get("data", ""))
    result = "missing" if notice_id is None else db.bookmark_notice(chat_id, notice_id)
    logger.info(f"   ㄴ 스크랩 버튼 (Chat ID: {chat_id}, notice: {notice_id}): {result}")
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json={"callback_query_id": callback_query["id"], "text": BOOKMARK_ANSWERS[result]},
            timeout=10,
        )
    except Exception as e:
        logger.error(f"⚠️ 스크랩 응답 오류 (Chat ID: {chat_id}): {e}")


def handle_update(token, update):
    if "callback_query" in update:
        handle_bookmark_callback(token, update["callback_query"])
        return
    if "message" not in update:
        return
    msg = update["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()
    logger.info(f"   ㄴ 감지된 메시지 (Chat ID: {chat_id}): '{text}'")

    if text == "/start" or text == "/menu":
        logger.info(f"      👉 '{text}' 명령어 매칭 성공! 메뉴 버튼 카드 발송 요청")
        send_menu(token, chat_id)


async def poll_loop(token):
    # ⚠️ 혹시 숨어있을 웹훅 세션을 강제 지우기하여 getUpdates 수신 방해 차단
    try:
        await asyncio.to_thread(requests.get, f"https://api.telegram.org/bot{token}/deleteWebhook", timeout=5)
    except Exception:
        pass

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    offset = None
    while True:
        try:
            # Long polling: Telegram holds the request up to 50s and returns as soon as a message arrives.
            response = await asyncio.to_thread(
                requests.get, url,
                params={"offset": offset, "timeout": 50, "allowed_updates": json.dumps(["message", "callback_query"])},
                timeout=60,
            )
            if response.status_code != 200:
                logger.error(f"⚠️ getUpdates HTTP {response.status_code}: {response.text[:200]}")
                await asyncio.sleep(5)
                continue

            for update in response.json().get("result", []):
                offset = update["update_id"] + 1
                await asyncio.to_thread(handle_update, token, update)
        except Exception as e:
            logger.error(f"⚠️ 대화 처리기 예외 발생: {e}")
            await asyncio.sleep(5)

# ==========================================
# 5. 크롤링 및 발송 코어 함수
# ==========================================
# 장애 경보를 이미 보낸 카테고리 (복구 시 제거)
failing_categories = set()

def fetch_notices(category_key):
    info = CATEGORIES.get(category_key)
    if not info:
        return []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    }
    notices = []
    try:
        response = requests.get(info["url"], headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select("tbody tr")
        for row in rows:
            num_tag = row.select_one(".b-num-box")
            title_tag = row.select_one(".b-title-box a")
            if num_tag and title_tag:
                title = title_tag.get_text(strip=True)
                href = title_tag["href"]
                
                if href.startswith("?"):
                    base_path = info["url"].split("?")[0]
                    link = base_path + href
                else:
                    link = href if href.startswith("http") else info["host"] + href
                
                parsed_query = urllib.parse.urlparse(link).query
                query_params = urllib.parse.parse_qs(parsed_query)
                article_no = query_params.get("articleNo", [None])[0]
                notice_id = article_no if article_no else link
                
                notices.append({"id": notice_id, "title": title, "link": link})
        if category_key in failing_categories:
            failing_categories.discard(category_key)
            send_telegram_message(
                TELEGRAM_TOKEN, ADMIN_CHAT_ID,
                f"<b>✅ [영남대 공지봇 복구]</b>\n\n📌 <b>복구 대상:</b> {info['name']}"
            )
        return notices
    except Exception as e:
        err_msg = f"⚠️ [{info['name']}] 크롤링 실패: {e}"
        logger.error(err_msg)

        # Alert once per outage; the bot now runs continuously, so repeats would arrive every 10 minutes.
        if category_key not in failing_categories:
            failing_categories.add(category_key)
            telegram_alert = (
                f"<b>🚨 [영남대 공지봇 장애 경보]</b>\n\n"
                f"공지사항을 긁어오는 중 에러가 발생했습니다.\n\n"
                f"📌 <b>장애 대상:</b> {info['name']}\n"
                f"❌ <b>에러 로그:</b> {e}"
            )
            send_telegram_message(TELEGRAM_TOKEN, ADMIN_CHAT_ID, telegram_alert)
        return []

def send_telegram_message(token, chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
        
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code == 200:
                return True
        except Exception as e:
            pass
        if attempt < max_retries:
            time.sleep(2)
    return False

# ==========================================
# 6. 메인 통합 실행
# ==========================================
def crawl_and_send():
    # 2. DB에서 최신 가입자/구독 정보 일괄 획득
    subscribers = load_subscribers_from_db()
    if not subscribers:
        logger.info("⚠️ 등록된 구독자가 데이터베이스에 없습니다. 이번 수집을 건너뜁니다.")
        return
        
    active_categories = set()
    for sub in subscribers:
        active_categories.update(sub.get("subscriptions", []))
        
    if not active_categories:
        logger.info("💤 활성화된 구독 카테고리가 없습니다.")
        logger.info("✅ 이번 수집을 건너뜁니다.")
        return
        
    last_notices = load_last_notices()
    new_notices_by_category = {}
    
    # 🔔 캐시 딕셔너리: 중복 크롤링을 완벽하게 방지하여 트래픽 절약
    crawled_cache = {}
    
    # 4. 구독 중인 카테고리만 크롤링 및 새 글 수집
    for category in active_categories:
        if category not in CATEGORIES:
            continue
        logger.info(f"🔍 공지사항 수집 중: {CATEGORIES[category]['name']}")
        notices = fetch_notices(category)
        if not notices:
            continue
            
        # 첫 번째 긁어온 공지 원본 리스트를 메모리 캐시에 백업 저장
        crawled_cache[category] = notices
            
        last_ids = last_notices.get(category, [])
        if isinstance(last_ids, str):
            last_ids = []
            
        new_posts = []
        
        if not last_ids:
            new_posts.append(notices[0])
        else:
            for notice in notices:
                if notice["id"] not in last_ids:
                    new_posts.append(notice)
                    
        if new_posts:
            new_posts.reverse()
            new_notices_by_category[category] = new_posts
            
    # 5. 1:1 개인화 공지 전송
    if not new_notices_by_category:
        logger.info("💤 신규 공지사항이 발견되지 않았습니다.")
    else:
        logger.info("🎯 새로운 공지가 수집되어 대상자별 개별 메시지 전송을 시작합니다...")

        # Store each new notice once so its scrap button carries only a short id.
        for category, posts in new_notices_by_category.items():
            for post in posts:
                post["notice_id"] = db.remember_notice(category, post["id"], post["title"], post["link"])

        for sub in subscribers:
            chat_id = sub["chat_id"]
            name = sub["name"]
            user_subs = sub.get("subscriptions", [])
            
            for category in user_subs:
                if category in new_notices_by_category:
                    for post in new_notices_by_category[category]:
                        category_name = CATEGORIES[category]["name"]
                        msg_text = (
                            f"<b>🚨 [{category_name} 새 공지!]</b>\n\n"
                            f"{post['title']}\n\n"
                            f"👉 <a href='{post['link']}'>공지 본문 바로가기</a>"
                        )
                        
                        keyboard = {
                            "inline_keyboard": [
                                [{"text": "📌 이 공지 스크랩하기", "callback_data": f"bm:{post['notice_id']}"}]
                            ]
                        }
                        
                        logger.info(f"📬 발송 시작 -> {name}({chat_id}) | 카테고리: {category_name}")
                        success = send_telegram_message(TELEGRAM_TOKEN, chat_id, msg_text, keyboard)
                        if success:
                            logger.info(f"   ㄴ 발송 성공: {post['title']}")
                        else:
                            logger.info(f"   ㄴ 발송 실패: {post['title']}")
                        time.sleep(0.5)
                        
    # 6. 알림 완료 기록 갱신 (메모리 캐시 정보를 그대로 백업하여 이중 크롤링 제거!)
    updated_last_notices = last_notices.copy()
    for category in active_categories:
        if category in crawled_cache and crawled_cache[category]:
            updated_last_notices[category] = [n["id"] for n in crawled_cache[category]]
            
    save_last_notices(updated_last_notices)
    logger.info("📝 알림 완료 기록 갱신 완료.")
    logger.info("✅ 이번 수집/발송 작업을 완료했습니다.")


async def schedule_loop():
    while True:
        now = datetime.now(KST)
        target = next_run_time(now)
        logger.info(f"⏰ 다음 수집 예정: {target:%Y-%m-%d %H:%M}")
        await asyncio.sleep((target - now).total_seconds())
        try:
            await asyncio.to_thread(crawl_and_send)
        except Exception as e:
            # One failed run must not stop future runs.
            logger.error(f"🚨 수집 실행 중 예외: {e}")


async def run():
    # systemd stops the service with SIGTERM. Cancel the loops instead of dying at once, so a crawl running in
    # a worker thread finishes and saves last_notices.json (asyncio.run waits for worker threads on exit).
    if sys.platform != "win32":
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, asyncio.current_task().cancel)
    runner = web.AppRunner(api.make_app(TELEGRAM_TOKEN, CATEGORIES))
    await runner.setup()
    await web.TCPSite(runner, API_HOST, API_PORT).start()
    logger.info(f"🌐 미니 앱 API 대기 중: http://{API_HOST}:{API_PORT}/api/")
    try:
        await asyncio.gather(poll_loop(TELEGRAM_TOKEN), schedule_loop())
    except asyncio.CancelledError:
        logger.info("🛑 종료 신호 수신. 진행 중인 작업을 마치고 종료합니다.")
    finally:
        await runner.cleanup()


def main():
    logger.info("🤖 영남대 공지봇 상시 실행 시작 (SQLite)...")

    # ⚠️ [보안/안전 가드] 필수 환경변수 누락 시 무한 예외 통신 방지 및 즉각 자가 안전 종료
    if not TELEGRAM_TOKEN:
        logger.error("🚨 [환경변수 에러] 필수 설정값 TELEGRAM_TOKEN 이 없습니다.")
        logger.error("   ㄴ 서버/로컬 폴더 내의 .env 파일 설정 상태를 다시 한번 확인해 주세요.")
        sys.exit(1)

    db.init_db(DB_PATH)
    asyncio.run(run())

if __name__ == "__main__":
    main()
