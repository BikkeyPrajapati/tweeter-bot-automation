import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException
from webdriver_manager.chrome import ChromeDriverManager
import time
import pickle
import os
import re
import logging
import random
import xml.etree.ElementTree as ET

# -------- Settings --------
COOKIES_FILE = "twitter_cookies.pkl"
MAX_TWEET_LENGTH = 275
MIN_TWEET_LENGTH = 150
LOG_FILE = "tweet_bot_errors.log"
TWEET_LOG_FILE = "tweet_log.txt"
HASHTAGS = {
    "BBC": [
        "#BBCNews", "#WorldNews", "#Breaking", "#UKNews", "#BBCUpdates", "#GlobalNews", "#Headlines"
    ],
    "CNN": [
        "#CNN", "#BreakingNews", "#CNNUpdates", "#USNews", "#WorldNews", "#TopStories", "#LiveNews"
    ],
    "TOI": [
        "#TimesOfIndia", "#IndiaNews", "#TOIUpdates", "#BreakingIndia", "#IndianNews", "#TOIHeadlines", "#BharatNews"
    ]
}

TWEET_HISTORY_FILE = "tweeted_news.txt"
MAX_HISTORY = 100
TOI_RSS_FEED = "http://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms"
# --------------------------

logging.basicConfig(filename=LOG_FILE, level=logging.ERROR,
                    format='%(asctime)s %(levelname)s:%(message)s')

def remove_non_bmp(text):
    return re.sub(r'[\U00010000-\U0010FFFF]', '', text)

def summarize(text, max_length):
    text = text.strip()
    if len(text) <= max_length:
        return text
    period_pos = text.find('.', max_length // 2)
    if 0 < period_pos < max_length:
        return text[:period_pos + 1]
    return text[:max_length].rsplit(' ', 1)[0] + "..."

def get_tweeted_news():
    if os.path.exists(TWEET_HISTORY_FILE):
        with open(TWEET_HISTORY_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f.readlines())
    return set()

def add_to_tweeted_news(headline):
    tweeted = list(get_tweeted_news())
    tweeted.insert(0, headline.strip())
    tweeted = tweeted[:MAX_HISTORY]
    with open(TWEET_HISTORY_FILE, "w", encoding="utf-8") as f:
        for t in tweeted:
            f.write(t + "\n")

def log_tweet(tweet_text, source):
    with open(TWEET_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{source}\t{tweet_text}\n")

def fetch_random_news():
    sources = [
        {
            "name": "BBC",
            "url": "https://www.bbc.com/news",
            "headline_selector": 'h2[data-testid="card-headline"]',
            "desc_selector": 'p'
        },
        {
            "name": "CNN",
            "url": "https://edition.cnn.com/world",
            "headline_selector": 'span.container__headline-text',
            "desc_selector": None
        },
        {
            "name": "TOI",
            "url": TOI_RSS_FEED,
            "headline_selector": None,
            "desc_selector": None
        }
    ]
    for source in random.sample(sources, len(sources)):
        try:
            headlines = []
            if source["name"] == "BBC":
                res = requests.get(source["url"], timeout=10)
                soup = BeautifulSoup(res.text, "html.parser")
                for h in soup.select(source["headline_selector"]):
                    headline = remove_non_bmp(h.text.strip())
                    if not headline: continue
                    next_p = h.find_next("p")
                    summary = remove_non_bmp(next_p.text.strip()) if next_p else ""
                    headlines.append((headline, summary))
            elif source["name"] == "CNN":
                res = requests.get(source["url"], timeout=10)
                soup = BeautifulSoup(res.text, "html.parser")
                for h in soup.select(source["headline_selector"]):
                    headline = remove_non_bmp(h.text.strip())
                    if not headline: continue
                    headlines.append((headline, ""))
            elif source["name"] == "TOI":
                res = requests.get(source["url"], timeout=10)
                root = ET.fromstring(res.content)
                for item in root.findall(".//item"):
                    headline = remove_non_bmp(item.findtext("title", default="").strip())
                    raw_summary = item.findtext("description", default="").strip()
                    clean_summary = BeautifulSoup(raw_summary, "html.parser").get_text()
                    summary = remove_non_bmp(clean_summary)
                    headlines.append((headline, summary))
            else:
                continue
            
            
            # Inside fetch_random_news()
            tweeted = get_tweeted_news()
            random.shuffle(headlines)
            for headline, summary in headlines:
                if not headline or headline in tweeted:
                    continue
                hashtag_list = HASHTAGS.get(source["name"], ["#News"])
                selected_tags = random.sample(hashtag_list, k=2) if len(hashtag_list) >= 2 else hashtag_list
                hashtag = " ".join(selected_tags)
                
                tweet = f"{headline}"
                if summary:
                    allowed_summary = MAX_TWEET_LENGTH - len(headline) - len(hashtag) - 3
                    if allowed_summary > 0:
                        summary_part = summarize(summary, max_length=allowed_summary)
                        tweet += f" - {summary_part}"
                tweet += f" {hashtag}"
                tweet = tweet.strip()
                if MIN_TWEET_LENGTH <= len(tweet) <= MAX_TWEET_LENGTH:
                    return tweet, headline, source["name"]

        except Exception as e:
            logging.error(f"Failed to fetch news from {source['name']}: {e}")
            print(f"⚠️ Failed to fetch news from {source['name']}: {e}")
    print("[!] No new news found to tweet.")
    return None, None, None

def tweet(text, driver, wait):
    try:
        driver.get("https://x.com/compose/post")

        # Wait for tweet box
        tweet_box = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "div[aria-label='Post text'][role='textbox']")))
        
        print("[*] Ensuring tweet box is visible...")
        driver.execute_script("arguments[0].scrollIntoView(true);", tweet_box)
        time.sleep(1)

        try:
            tweet_box.click()
        except ElementClickInterceptedException:
            print("[!] Click intercepted, trying JS click...")
            driver.execute_script("arguments[0].click();", tweet_box)

        time.sleep(1)
        tweet_box.send_keys(text)
        print(f"[+] Tweet text entered: {text}")

        try:
            WebDriverWait(driver, 5).until_not(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='dialog']"))
            )
        except:
            print("[!] Modal might still be open...")

        # Wait for and click post button
        post_button = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "button[data-testid='tweetButton']")))

        driver.execute_script("arguments[0].scrollIntoView(true);", post_button)
        time.sleep(1)
        driver.save_screenshot("pre_click_debug.png")

        try:
            post_button.click()
        except Exception:
            print("[!] Post button click failed, using JS click...")
            driver.execute_script("arguments[0].click();", post_button)

        print("[+] Tweet posted successfully!")
        return True

    except Exception as e:
        logging.error(f"Failed to tweet: {e}")
        driver.save_screenshot("debug_tweet_error.png")
        print(f"[X] Failed to tweet: {e}")

        try:
            intercepting_element = driver.execute_script("""
                const el = document.elementFromPoint(437, 90);
                return el ? el.outerHTML : 'None';
            """)
            print(f"[!] Intercepting element: {intercepting_element}")
        except:
            pass

        return False

def main():
    tweet_text, headline, src = fetch_random_news()
    if not tweet_text:
        print("[X] No tweet to post.")
        return

    print(f"[*] Composed tweet: {tweet_text} ({len(tweet_text)} chars)")

    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--headless=new")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.get("https://x.com")

    if os.path.exists(COOKIES_FILE):
        print("[*] Loading cookies...")
        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)
            for cookie in cookies:
                if "expiry" in cookie:
                    del cookie["expiry"]
                driver.add_cookie(cookie)
        driver.refresh()
        print("[+] Cookies loaded and refreshed!")
        time.sleep(5)
    else:
        print("[!] Cookie file not found. Login manually, save cookies, and rerun.")
        driver.quit()
        return

    wait = WebDriverWait(driver, 20)
    if tweet(tweet_text, driver, wait):
        add_to_tweeted_news(headline)
        log_tweet(tweet_text, src)

    driver.quit()
    print("[*] All done!")

if __name__ == "__main__":
    main()