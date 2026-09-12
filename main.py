"""
Weekly Cyber Digest
Fetches cybersecurity news, simplifies it with AI, and emails a summary.
"""

import json
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import feedparser
from google import genai
import trafilatura
from dateutil import parser as date_parser
from dotenv import load_dotenv


# ============================================================
# 1. SETTINGS - loaded from .env file (never put real values here)
# ============================================================

load_dotenv()

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TO_EMAIL = os.getenv("TO_EMAIL")
         # ← where to send it


FEEDS = [
    "https://feeds.feedburner.com/TheHackersNews",
    "https://www.bleepingcomputer.com/feed/",
    "https://krebsonsecurity.com/feed/",
    "https://www.securityweek.com/feed/",
    "https://therecord.media/feed",
]

SEEN_FILE = Path("seen_articles.json")
MAX_ARTICLES = 15
DAYS_TO_LOOK_BACK = 7

# --- Digest preferences (edit these anytime) ---
MIN_SEVERITY = 2          # only email articles with severity >= this (1-5)
MIN_SEVERITY_BADGE = 4    # articles >= this get a 🔴 CRITICAL-style badge

SEVERITY_EMOJI = {
    5: "🚨 CRITICAL",
    4: "🔴 HIGH",
    3: "🟠 MEDIUM",
    2: "🟡 LOW",
    1: "⚪ TRIVIAL",
}


# ============================================================
# 2. AI SETUP
# ============================================================

client = genai.Client(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-3.6-flash"


def ask_ai(prompt):
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    )
    return response.text

# ============================================================
# 3. REMEMBERING OLD STORIES
# ============================================================

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(list(seen)))


# ============================================================
# 4. FETCH ARTICLES
# ============================================================

def fetch_recent_articles():
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_TO_LOOK_BACK)
    seen = load_seen()
    articles, used_links = [], set()

    for feed_url in FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                link = entry.get("link", "")
                if not link or link in seen or link in used_links:
                    continue
                if entry.get("published"):
                    try:
                        if date_parser.parse(entry.published) < cutoff:
                            continue
                    except Exception:
                        pass
                used_links.add(link)
                articles.append({
                    "title": entry.get("title", "Untitled"),
                    "link": link,
                    "summary": entry.get("summary", ""),
                })
        except Exception as e:
            print(f"  Could not read feed {feed_url}: {e}")

        if len(articles) >= MAX_ARTICLES * 2:
            break

    return articles[:MAX_ARTICLES]


def get_full_text(url, fallback=""):
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded)
            if text and len(text) > len(fallback):
                return text[:5000]
    except Exception:
        pass
    return fallback[:3000]


# ============================================================
# 5. AI: CATEGORIZE, RATE SEVERITY, SIMPLIFY
# ============================================================

def analyze_all_articles(articles):
    numbered = ""
    for i, a in enumerate(articles, 1):
        numbered += f"ARTICLE {i}\nTITLE: {a['title']}\nLINK: {a['link']}\n"
        numbered += f"CONTENT: {get_full_text(a['link'], a['summary'])[:2000]}\n\n"

    prompt = f"""You are a friendly cybersecurity explainer. Analyze each article below.
For EACH article, reply in EXACTLY this block format, and separate blocks
with the line --- :

NUMBER: [article number]
CATEGORY: [one word: Ransomware, Breach, Zero-Day, Malware, Privacy, Government, Advisories, Other]
SEVERITY: [1-5, where 5 is critical]
TITLE: [simplified title]
SUMMARY: [3-4 plain-English sentences: what happened, who is affected, one practical takeaway]

Articles:
{numbered}"""

    reply = ask_ai(prompt)

    results = []
    for block in reply.split("---"):
        entry = None
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("NUMBER:"):
                entry = {"category": "Other", "severity": 3, "title": "",
                         "summary": "", "link": ""}
                try:
                    n = int(line.split(":", 1)[1].strip())
                    entry["link"] = articles[n - 1]["link"]
                except Exception:
                    entry = None
            elif entry is not None:
                if line.startswith("CATEGORY:"):
                    entry["category"] = line.split(":", 1)[1].strip()[:20]
                elif line.startswith("SEVERITY:"):
                    try:
                        entry["severity"] = int(line.split(":", 1)[1].strip()[0])
                    except Exception:
                        pass
                elif line.startswith("TITLE:"):
                    entry["title"] = line.split(":", 1)[1].strip()
                elif line.startswith("SUMMARY:"):
                    entry["summary"] = line.split(":", 1)[1].strip()
        if entry and entry["summary"]:
            results.append(entry)
    return results


# ============================================================
# 6. BUILD + SEND EMAIL
# ============================================================


def build_email(weekly_overview, analyzed):
    # 1. Filter by minimum severity BEFORE doing anything else
    filtered = [a for a in analyzed if a["severity"] >= MIN_SEVERITY]

    if not filtered:
        print(f"No articles met severity >= {MIN_SEVERITY}. Skipping email.")
        return None

    groups = {}
    for a in filtered:
        groups.setdefault(a["category"], []).append(a)

    html = f"""
    <html><body style="font-family: Arial, sans-serif; max-width: 700px;">
    <h2>Weekly Cyber Digest - {datetime.now():%B %d, %Y}</h2>
    <p style="background:#f0f4f8; padding:12px; border-radius:8px;">
    {weekly_overview}</p><hr>
    """

    for category, stories in sorted(groups.items()):
        html += f"<h3>{category}</h3>"
        for s in sorted(stories, key=lambda x: -x["severity"]):
            badge = SEVERITY_EMOJI.get(s["severity"], "🟠 MEDIUM")
            html += f"""
            <p><b>{s['title']}</b><br>
            <small>Severity: {badge}</small><br>
            {s['summary']}<br>
            <a href="{s['link']}">Read the original</a></p>
            """

    html += "<hr><p style='color:gray;font-size:12px;'>Built with Python</p>"
    html += "</body></html>"
    return html



def send_email(html):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Weekly Cyber Digest - {datetime.now():%b %d}"
    msg["From"] = TO_EMAIL
    msg["To"] = TO_EMAIL
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)


# ============================================================
# 7. MAIN
# ============================================================

def main():
    print("Fetching articles...")
    articles = fetch_recent_articles()
    if not articles:
        print("No new articles found. Done.")
        return
    print(f"Found {len(articles)} new articles.")

    print("Analyzing with AI (one big batch call)...")
    analyzed = analyze_all_articles(articles)
    print(f"  Successfully analyzed {len(analyzed)} articles.")

    if not analyzed:
        print("AI returned nothing useful. Try again later.")
        return

    print("Writing weekly overview...")
    titles = "\n".join(f"- {a['title']} ({a['category']})" for a in analyzed)
    overview = ask_ai(
        "Write a short 4-5 sentence plain-English overview of this week's "
        "cybersecurity themes. Friendly tone, no jargon:\n" + titles
    )

    print("Building email...")
    html = build_email(overview, analyzed)
    if html is None:
        print("Nothing severe enough to email. Marking articles as seen anyway.")
    else:
        print("Sending email...")
        send_email(html)


    seen = load_seen()
    for a in analyzed:
        seen.add(a["link"])
    save_seen(seen)
    print("Done! Check your inbox.")
if __name__ == "__main__":
    main()

