import os
import json
import time
import random
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from groq import Groq

import gspread
from oauth2client.service_account import ServiceAccountCredentials


# ================= CONFIG =================
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SHEET_NAME = "Sheet1"

LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_URN = os.getenv("LINKEDIN_PERSON_URN")
 
RENDER_SELF_URL = os.getenv("RENDER_SELF_URL")  # optional

GROQ_API_KEY= os.getenv("GROQ_API_KEY")

groq_client = Groq(api_key=GROQ_API_KEY)
# =========================================

# ---------- GLOBAL VERIFIED STATE ----------
sheet = None
# ------------------------------------------


# ========== GOOGLE SHEETS AUTH ==========
def verify_google_sheet():
    global sheet

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    if os.path.exists("google_credentials.json"):
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            "google_credentials.json", scope
        )
    else:
        creds_dict = json.loads(os.environ["GOOGLE_CREDS_JSON"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            creds_dict, scope
        )

    client = gspread.authorize(creds)
    sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(SHEET_NAME)

    # sanity check
    sheet.get_all_records()



# ========== BUSINESS LOGIC ==========
def get_pending_row():
    rows = sheet.get_all_records()
    for i, row in enumerate(rows, start=2):
        if row.get("Status") == "Pending":
            return i, row
    return None, None


def generate_post(prompt: str) -> str:
    """
    Takes a raw prompt from Google Sheet
    Returns a clean, LinkedIn-ready post
    """

    system_prompt = (
        """You are a senior full-stack developer, Shopify expert,UI, UX and SaaS builder writing from real production experience.

Audience
Mid-to-senior developers, Shopify/eCommerce builders, and SaaS founders who already know the basics and care about performance, SEO, maintainability, and business impact.

Goal
Write LinkedIn posts that teach one sharp insight, challenge assumptions, and connect tech decisions to real outcomes.

Style Rules

Confident, senior voice

No emojis, no hashtags

No hype or beginner explanations

Clear, skimmable paragraphs

Practical insight over theory

Post Structure

Strong hook (1–2 lines)

Explain the real problem or misconception

2–4 concrete insights or tradeoffs

End with one thoughtful question

Constraints

Don’t repeat the topic title

Don’t oversell tools or frameworks

No step-by-step tutorials

Input: One topic
Output: One complete LinkedIn post"""
    )

    user_prompt = f"""
prompt: {prompt}

Write a LinkedIn post following all rules.
"""

    response = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=400,
    )

    text = response.choices[0].message.content.strip()

    return text

def post_to_linkedin(text):
    headers = {
    "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
    "Content-Type": "application/json",
    "LinkedIn-Version": "202401",
    "X-Restli-Protocol-Version": "2.0.0"
    }

    payload = {
        "author": LINKEDIN_PERSON_URN,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }

    r = requests.post("https://api.linkedin.com/v2/ugcPosts", headers=headers, json=payload)
    r.raise_for_status()


def job():
    row_number, row = get_pending_row()
    if not row:
        return

    post_text = generate_post(row["AI Prompt"])
    post_to_linkedin(post_text)

    # ✅ Wrap value in list of lists
    sheet.update(f"C{row_number}", [["Posted"]])
    
    
# ========== KEEP ALIVE ==========
def keep_alive():
    if not RENDER_SELF_URL:
        return
    try:
        requests.get(RENDER_SELF_URL, timeout=5)
    except:
        pass


# ========== STARTUP ==========
def startup():
    verify_google_sheet()

    scheduler = BackgroundScheduler()
    scheduler.add_job(keep_alive, "interval", minutes=random.randint(5, 7))
    scheduler.start()
    scheduler.add_job(job, "interval", hours=4)




if __name__ == "__main__":
    startup()
    time.sleep(60)  # keep the script alive for APScheduler