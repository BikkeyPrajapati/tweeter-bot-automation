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
import certifi  # ADDED
import json     # ADDED

# -------- Settings --------
COOKIES_FILE = "twitter_cookies.pkl"
MAX_TWEET_LENGTH = 275
MIN_TWEET_LENGTH = 150
LOG_FILE = "tweet_bot_errors.log"
TWEET_LOG_FILE = "tweet_log.txt"
HASHTAGS = {
    "BBC": [
        "#BBCNews", "#BreakingNews", "#WorldNews", "#Breaking", "#UKNews", "#BBCUpdates", "#GlobalNews", "#Headlines", "#BBCEarth", "#BBCTravel", "#TrendingNow", "#NewsAlert", "#BBCBritain", "#LiveNews", "#NewsOfTheDay"
    ],
    "CNN": [
        "#CNN", "#BreakingNews", "#CNNUpdates", "#USNews", "#WorldNews", "#TopStories", "#LiveNews", "#CNNNews", "#Politics", "#TrendingNews", "#NewsUpdate", "#Election2024", "#Democracy", "#Headlines", "#ViralNews"
    ],
    "TOI": [
        "#TimesOfIndia", "#IndiaNews", "#TOIUpdates", "#BreakingIndia", "#IndianNews", "#TOIHeadlines", "#BharatNews", "#TOI", "#Mumbai", "#Bollywood", "#IndiaToday", "#TrendingIndia", "#DesiNews", "#IndianPolitics", "#NewsIndia"
    ],
    "NDTV": [
        "#NDTV", "#NDTVNews", "#IndiaNews", "#Breaking", "#NewsUpdate", "#IndianNews", "#LatestNews", "#RavishKumar", "#Delhi", "#Modi", "#BJP", "#Politics", "#IndianPolitics", "#TrendingIndia", "#NewsAlert"
    ],
    "TheHindu": [
        "#TheHindu", "#IndiaNews", "#QualityJournalism", "#Breaking", "#Analysis", "#HinduNews", "#Credible", "#Chennai", "#SouthIndia", "#IndianExpress", "#Politics", "#NewsAnalysis", "#Editorial", "#OpEd", "#InDepthNews"
    ],
    "IndianExpress": [
        "#IndianExpress", "#IndiaNews", "#Breaking", "#ExpressNews", "#Journalism", "#Politics", "#Analysis", "#Delhi", "#Mumbai", "#IndianPolitics", "#NewsUpdate", "#Editorial", "#Investigation", "#CurrentAffairs", "#TrendingNews"
    ],
    "HindustanTimes": [
        "#HindustanTimes", "#HTNews", "#IndiaNews", "#Breaking", "#News", "#Politics", "#Updates", "#Delhi", "#Mumbai", "#IndianNews", "#HTUpdates", "#Bollywood", "#Sports", "#Business", "#TrendingIndia"
    ],
    "IndiaToday": [
        "#IndiaToday", "#Breaking", "#IndiaNews", "#Analysis", "#Politics", "#CurrentAffairs", "#News", "#AajTak", "#IndianNews", "#NewsUpdate", "#TrendingIndia", "#Investigation", "#Exclusive", "#LiveNews", "#Headlines"
    ]
}


TWEET_HISTORY_FILE = "tweeted_news.txt"
MAX_HISTORY = 100
TOI_RSS_FEED = "http://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms"
NDTV_RSS_FEED = "https://feeds.feedburner.com/ndtvnews-latest"
THEHINDU_RSS_FEED = "https://www.thehindu.com/feeder/default.rss"
INDIANEXPRESS_RSS_FEED = "https://indianexpress.com/section/india/feed/"
HINDUSTANTIMES_RSS_FEED = "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml"
INDIATODAY_RSS_FEED = "https://www.indiatoday.in/rss/1206578"
# --------------------------

logging.basicConfig(filename=LOG_FILE, level=logging.ERROR,
                    format='%(asctime)s %(levelname)s:%(message)s')

# ADDED - Missing function for GitHub Actions
def setup_cookies():
    """Load cookies from GitHub Secret or local file"""
    if os.getenv('GITHUB_ACTIONS'):
        print("[*] Running in GitHub Actions - loading cookies from secrets")
        cookie_data = os.getenv('TWITTER_COOKIES')
        if cookie_data:
            try:
                print(f"[*] Cookie data length: {len(cookie_data)}")
                cookies = json.loads(cookie_data)
                print(f"[*] Successfully parsed {len(cookies)} cookies")
                with open('temp_cookies.pkl', 'wb') as f:
                    pickle.dump(cookies, f)
                print("[*] Temporary cookie file created successfully")
                return 'temp_cookies.pkl'
            except json.JSONDecodeError as e:
                print(f"[!] JSON parsing error: {e}")
                return None
            except Exception as e:
                print(f"[!] Cookie processing error: {e}")
                return None
        else:
            print("[!] No TWITTER_COOKIES environment variable found")
            return None
    else:
        print("[*] Running locally - using local cookie file")
        return 'twitter_cookies.pkl'

# ADDED - Missing function for SSL certificates
def fetch_with_certifi(url, timeout=10):
    """Fetch URL using certifi certificate bundle"""
    try:
        response = requests.get(url, verify=certifi.where(), timeout=timeout)
        return response
    except requests.exceptions.RequestException as e:
        raise e

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
        },
        {  # ADDED - NDTV source
            "name": "NDTV",
            "url": NDTV_RSS_FEED,
            "headline_selector": None,
            "desc_selector": None
        },
        {
            "name": "TheHindu",
            "url": THEHINDU_RSS_FEED,
            "headline_selector": None,
            "desc_selector": None
        },
         {
            "name": "IndianExpress",
            "url": INDIANEXPRESS_RSS_FEED,
            "headline_selector": None,
            "desc_selector": None
        },
         {
            "name": "HindustanTimes",
            "url": HINDUSTANTIMES_RSS_FEED,
            "headline_selector": None,
            "desc_selector": None
        },
        {
            "name": "IndiaToday",
            "url": INDIATODAY_RSS_FEED,
            "headline_selector": None,
            "desc_selector": None
        }
    ]
    
    for source in random.sample(sources, len(sources)):
        try:
            headlines = []
            if source["name"] == "BBC":
                res = fetch_with_certifi(source["url"], timeout=10)  # FIXED - use certifi
                soup = BeautifulSoup(res.text, "html.parser")
                for h in soup.select(source["headline_selector"]):
                    headline = remove_non_bmp(h.text.strip())
                    if not headline: 
                        continue
                    next_p = h.find_next("p")
                    summary = remove_non_bmp(next_p.text.strip()) if next_p else ""
                    headlines.append((headline, summary))
                    
            elif source["name"] == "CNN":
                res = fetch_with_certifi(source["url"], timeout=10)  # FIXED - use certifi
                soup = BeautifulSoup(res.text, "html.parser")
                for h in soup.select(source["headline_selector"]):
                    headline = remove_non_bmp(h.text.strip())
                    if not headline: 
                        continue
                    headlines.append((headline, ""))
                    
            elif source["name"] == "TOI" or source["name"] == "NDTV" or source["name"] == "TheHindu" or source["name"] == "IndianExpress" or source["name"] == "HindustanTimes" or source["name"] == "IndiaToday":
                res = fetch_with_certifi(source["url"], timeout=10)
                root = ET.fromstring(res.content)
                for item in root.findall(".//item"):
                    headline = remove_non_bmp(item.findtext("title", default="").strip())
                    raw_summary = item.findtext("description", default="").strip()
                    clean_summary = BeautifulSoup(raw_summary, "html.parser").get_text()
                    summary = remove_non_bmp(clean_summary)
                    
                    # Skip summary if it's the same as headline
                    if summary.lower().strip() == headline.lower().strip():
                        summary = ""
                        
                    headlines.append((headline, summary))

            
            else:
                continue
            
            # Filter out already tweeted news and compose tweet
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
                    
        except Exception as e:  # FIXED - complete try-except block
            logging.error(f"Failed to fetch news from {source['name']}: {e}")
            print(f"⚠️ Failed to fetch news from {source['name']}: {e}")
    
    print("[!] No new news found to tweet.")
    return None, None, None

def tweet(text, driver, wait):
    try:
        driver.get("https://x.com/compose/post")

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
        return False

def main():
    print("[*] Starting Twitter Bot...")
    
    # FIXED - Add cookie setup for GitHub Actions
    cookie_file = setup_cookies()
    if not cookie_file:
        print("[!] No cookie file available")
        return
    
    tweet_text, headline, src = fetch_random_news()
    if not tweet_text:
        print("[X] No tweet to post.")
        return

    print(f"[*] Composed tweet: {tweet_text} ({len(tweet_text)} chars)")

    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")  # ADDED
    chrome_options.add_argument("--disable-dev-shm-usage")  # ADDED

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.get("https://x.com")

    if os.path.exists(cookie_file):  # FIXED - use dynamic cookie file
        print("[*] Loading cookies...")
        with open(cookie_file, "rb") as f:
            cookies = pickle.load(f)
            for cookie in cookies:
                if "expiry" in cookie:
                    del cookie["expiry"]
                driver.add_cookie(cookie)
        driver.refresh()
        print("[+] Cookies loaded and refreshed!")
        time.sleep(5)
    else:
        print(f"[!] Cookie file {cookie_file} not found. Login manually, save cookies, and rerun.")
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
