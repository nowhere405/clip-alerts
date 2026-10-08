"""Check YouTube, TikTok and a Facebook Page for new clips and post them to Discord.

Settings come from environment variables (GitHub repository secrets):
  DISCORD_WEBHOOK_URL   required. Discord channel webhook link.
  YOUTUBE_CHANNEL       optional. Channel link, @handle, or UC... channel id.
  TIKTOK_USERNAME       optional. TikTok username, with or without @.
  TIKTOK_RSS_URL        optional. Any RSS feed of the TikTok profile (overrides the default).
  FACEBOOK_PAGE_ID      optional. Numeric Page id.
  FACEBOOK_PAGE_TOKEN   optional. Long-lived Page access token.

Seen clip ids are kept in state.json. The first time a platform is checked,
its existing clips are only remembered, so old clips are never announced.
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
USER_AGENT = "Mozilla/5.0 (compatible; clip-alerts/1.0)"
MAX_REMEMBERED = 200


def fetch(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def env(name):
    return os.environ.get(name, "").strip()


# --- YouTube -----------------------------------------------------------------

def youtube_channel_id(value):
    if re.fullmatch(r"UC[\w-]{22}", value):
        return value
    m = re.search(r"/channel/(UC[\w-]{22})", value)
    if m:
        return m.group(1)
    if not value.startswith("http"):
        value = "https://www.youtube.com/" + (value if value.startswith("@") else "@" + value)
    page = fetch(value)
    m = re.search(r'"(?:channelId|externalId)":"(UC[\w-]{22})"', page)
    if not m:
        raise RuntimeError(f"could not find a YouTube channel id at {value}")
    return m.group(1)


def youtube_clips(channel):
    channel_id = youtube_channel_id(channel)
    xml = fetch(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    clips = []
    for entry in ET.fromstring(xml).findall("a:entry", ns):
        video_id = entry.findtext("yt:videoId", namespaces=ns)
        title = entry.findtext("a:title", default="", namespaces=ns)
        link = entry.find("a:link", ns)
        url = link.get("href") if link is not None else f"https://www.youtube.com/watch?v={video_id}"
        clips.append({"id": video_id, "title": title, "url": url})
    return clips


# --- TikTok ------------------------------------------------------------------

def rss_clips(feed_url):
    root = ET.fromstring(fetch(feed_url))
    clips = []
    for item in root.iter("item"):
        url = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or url).strip()
        clips.append({"id": guid, "title": (item.findtext("title") or "").strip(), "url": url})
    return clips


def tiktok_clips(username, feed_url):
    if feed_url:
        return rss_clips(feed_url)
    # TikTok has no official feed, so yt-dlp reads the public profile page.
    username = username.lstrip("@")
    out = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--playlist-end", "10", "-J",
         f"https://www.tiktok.com/@{username}"],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip().splitlines()[-1] if out.stderr.strip() else "yt-dlp failed")
    clips = []
    for entry in json.loads(out.stdout).get("entries") or []:
        video_id = str(entry.get("id") or "")
        url = entry.get("url") or f"https://www.tiktok.com/@{username}/video/{video_id}"
        if not url.startswith("http"):
            url = f"https://www.tiktok.com/@{username}/video/{video_id}"
        title = (entry.get("title") or entry.get("description") or "").split("\n")[0][:150]
        clips.append({"id": video_id, "title": title, "url": url})
    return clips


# --- Facebook Page -----------------------------------------------------------

def facebook_clips(page_id, token):
    # Reels and videos posted on the Page also show up as Page posts.
    params = urllib.parse.urlencode({
        "fields": "id,message,permalink_url",
        "limit": 10,
        "access_token": token,
    })
    data = json.loads(fetch(f"https://graph.facebook.com/v21.0/{page_id}/posts?{params}"))
    clips = []
    for post in data.get("data", []):
        url = post.get("permalink_url") or f"https://www.facebook.com/{post['id']}"
        text = post.get("message") or ""
        clips.append({"id": post["id"], "title": text.split("\n")[0][:150], "url": url})
    return clips


# --- Discord -----------------------------------------------------------------

def announce(webhook, platform, clip):
    title = clip["title"] or "New clip"
    body = json.dumps({"content": f"🎬 **New {platform} clip is up!**\n{title}\n{clip['url']}"}).encode()
    fetch(webhook, data=body, headers={"Content-Type": "application/json"})


# --- Main --------------------------------------------------------------------

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")


def main():
    webhook = env("DISCORD_WEBHOOK_URL")
    if not webhook:
        sys.exit("DISCORD_WEBHOOK_URL is not set")

    if env("SEND_TEST") == "true":
        announce(webhook, "test", {"title": "This is a test. Real clip alerts will look like this.", "url": "https://github.com/nowhere405/clip-alerts"})
        print("test message sent")
        return

    sources = []
    if env("YOUTUBE_CHANNEL"):
        sources.append(("YouTube", lambda: youtube_clips(env("YOUTUBE_CHANNEL"))))
    if env("TIKTOK_USERNAME") or env("TIKTOK_RSS_URL"):
        sources.append(("TikTok", lambda: tiktok_clips(env("TIKTOK_USERNAME"), env("TIKTOK_RSS_URL"))))
    if env("FACEBOOK_PAGE_ID") and env("FACEBOOK_PAGE_TOKEN"):
        sources.append(("Facebook", lambda: facebook_clips(env("FACEBOOK_PAGE_ID"), env("FACEBOOK_PAGE_TOKEN"))))
    if not sources:
        sys.exit("No platforms are set up yet")

    state = load_state()
    failed = []
    for platform, get_clips in sources:
        try:
            clips = get_clips()
        except Exception as e:
            print(f"{platform}: check failed: {e}", file=sys.stderr)
            failed.append(platform)
            continue

        first_run = platform not in state
        seen = state.setdefault(platform, [])
        new = []
        for c in clips:
            if c["id"] and c["id"] not in seen and c["id"] not in (n["id"] for n in new):
                new.append(c)
        # Feeds list newest first; announce oldest first so Discord reads in order.
        for clip in reversed(new):
            if not first_run:
                announce(webhook, platform, clip)
                print(f"{platform}: announced {clip['url']}")
            seen.append(clip["id"])
        state[platform] = seen[-MAX_REMEMBERED:]
        print(f"{platform}: {len(clips)} clips checked, {0 if first_run else len(new)} new")

    # A daily change keeps the repo active so GitHub never pauses the schedule.
    state["last_run_day"] = time.strftime("%Y-%m-%d", time.gmtime())
    save_state(state)
    if failed and len(failed) == len(sources):
        sys.exit("Every platform check failed")


if __name__ == "__main__":
    main()
