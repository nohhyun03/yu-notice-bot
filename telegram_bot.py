import json
import requests
import os
import time
import sys
import logging
import urllib.parse
from logging.handlers import RotatingFileHandler
from bs4 import BeautifulSoup
from supabase import create_client, Client
from dotenv import load_dotenv

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

# 미니 앱 URL (사용자의 GitHub Pages 주소)
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://nohhyun03.github.io/yu-notice-bot/")

# Supabase 클라우드 DB 연동 설정
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
        response = supabase.table("subscribers").select("*").execute()
        return response.data if response.data else []
    except Exception as e:
        logger.error(f"⚠️ Supabase 데이터 로드 실패: {e}")
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
def process_pending_commands(token):
    # ⚠️ 혹시 숨어있을 웹훅 세션을 강제 지우기하여 getUpdates 수신 방해 차단
    try:
        requests.get(f"https://api.telegram.org/bot{token}/deleteWebhook", timeout=5)
    except Exception:
        pass

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            logger.info(f"⚠️ 대화 내역 수집 실패 (HTTP 상태코드: {response.status_code})")
            return
            
        updates = response.json().get("result", [])
        logger.info(f"🔍 텔레그램 대기 중인 명령어 개수: {len(updates)}개")
        if not updates:
            return
            
        last_update_id = 0
        for update in updates:
            update_id = update["update_id"]
            last_update_id = max(last_update_id, update_id)
            
            if "message" in update:
                msg = update["message"]
                chat_id = msg["chat"]["id"]
                text = msg.get("text", "").strip()
                logger.info(f"   ㄴ 감지된 메시지 (Chat ID: {chat_id}): '{text}'")
                
                if text == "/start" or text == "/menu":
                    logger.info(f"      👉 '{text}' 명령어 매칭 성공! 메뉴 버튼 카드 발송 요청")
                    send_menu(token, chat_id)
                    
        if last_update_id > 0:
            requests.get(f"{url}?offset={last_update_id + 1}", timeout=10)
            
    except Exception as e:
        logger.error(f"⚠️ 대화 처리기 예외 발생: {e}")

# ==========================================
# 5. 크롤링 및 발송 코어 함수
# ==========================================
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
        return notices
    except Exception as e:
        err_msg = f"⚠️ [{info['name']}] 크롤링 실패: {e}"
        logger.error(err_msg)
        
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
def main():
    logger.info("🤖 영남대 다중 공지사항 배치 프로그램 작동 시작 (Supabase 연동)...")
    
    # 1. 사용자가 보낸 명령어 처리
    process_pending_commands(TELEGRAM_TOKEN)
    
    # 2. Supabase DB에서 최신 가입자/구독 정보 일괄 획득
    subscribers = load_subscribers_from_db()
    if not subscribers:
        logger.info("⚠️ 등록된 구독자가 데이터베이스에 없습니다. 크롤링 단계를 건너뛰고 종료합니다.")
        return
        
    active_categories = set()
    for sub in subscribers:
        active_categories.update(sub.get("subscriptions", []))
        
    if not active_categories:
        logger.info("💤 활성화된 구독 카테고리가 없습니다.")
        logger.info("✅ 배치 처리가 완료되어 프로그램을 안전하게 종료합니다.")
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
                        
                        encoded_title = urllib.parse.quote(post['title'])
                        encoded_link = urllib.parse.quote(post['link'])
                        bookmark_url = f"{WEBAPP_URL}?action=add&title={encoded_title}&link={encoded_link}"
                        
                        keyboard = {
                            "inline_keyboard": [
                                [{"text": "📌 이 공지 스크랩하기", "web_app": {"url": bookmark_url}}]
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
    logger.info("✅ 모든 배치 작업이 완료되어 프로그램을 안전하게 종료합니다.")

if __name__ == "__main__":
    main()
