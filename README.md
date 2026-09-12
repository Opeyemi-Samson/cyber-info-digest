# 🔐 Cyber Info Digest

An AI-powered pipeline that fetches cybersecurity news, simplifies it
into plain English, and emails a clean weekly digest.

## Why I built it
I wanted to keep up with security news but headlines were either too
technical or too alarmist. So I built a tool that reads the sources,
and uses Gemini to categorize, rate severity, and explain each story
like a friendly analyst would.

## How it works
RSS Feeds → Deduplicate → Full-text fetch → AI (categorize/severity/summarize)
→ HTML email via Gmail

## Setup
1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in your keys
3. `python main.py`

## What I learned
- Google's free-tier AI quotas (batching 15 AI calls into 1!)
- Handling retired model versions gracefully
- SMTP + Gmail App Passwords
