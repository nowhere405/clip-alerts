# Clip alerts

When a new clip appears on your YouTube channel, TikTok or Facebook Page, a message with the link appears in your Discord channel. GitHub runs the check for free every 10 minutes, so your PC can stay off.

## Setup

Add each item under **Settings → Secrets and variables → Actions → New repository secret** in this GitHub repo:

| Secret name | What to put |
|---|---|
| `DISCORD_WEBHOOK_URL` | In Discord: right-click the channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy Webhook URL |
| `YOUTUBE_CHANNEL` | Your channel link, for example `https://www.youtube.com/@yourname` |
| `TIKTOK_USERNAME` | Your TikTok username, for example `@yourname` |
| `FACEBOOK_PAGE_ID` | Your Page's number id (from Page → About → Page transparency, or Meta Business Suite) |
| `FACEBOOK_PAGE_TOKEN` | A long-lived Page access token (Claude will walk you through this) |

Leave out any platform you don't want checked.

Then go to **Actions → Check for new clips → Run workflow** once. The first run only remembers your existing clips, so nothing old gets posted. After that, every new clip is announced.

## Valorant live alerts

When a Valorant Champions match goes live on vlr.gg, the channel gets a "LIVE NOW: Team A vs Team B" message. To send these to a different channel, make a webhook there and save it as the secret `VALORANT_WEBHOOK_URL`. To follow a different event, change `VALORANT_EVENT` in `.github/workflows/check.yml`.

## Notes

- Alerts arrive about 10 to 15 minutes after a clip goes live. GitHub can sometimes run the check a bit late.
- TikTok has no official feed. By default the check reads your public profile with yt-dlp, which sometimes breaks when TikTok changes things. If TikTok alerts stop, set `TIKTOK_RSS_URL` to another RSS feed of your profile (for example, one from rss.app).
- `state.json` is the list of clips already announced. Don't delete it unless you want everything re-remembered.
