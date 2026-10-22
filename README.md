# telegram_msg_svc_auto

Every morning, one Telegram post per city with the day's weather: a short caption you can read in
the notification, and a chart of today's temperature and chance of rain.

<!-- screenshot of a post -->

## Set up

1. **Get a bot token.** In Telegram, talk to [@BotFather](https://t.me/BotFather): `/newbot`.
   If a token was ever pasted into a chat, `/revoke` it and use the new one.
2. **Pick where it posts.** Press **Start** in the bot's chat to get the posts yourself, or make a
   private channel and add the bot as an admin with **Post messages**.
3. Fill in `.env`:

   ```bash
   cp .env.example .env && chmod 600 .env   # then paste TELEGRAM_BOT_TOKEN
   uv sync
   # press Start, or post any message in the channel, then:
   uv run inv chat-id                        # copy the id into CHAT_ID
   uv run inv send-now                       # a post right now, to check how it looks
   ```

## Run it every morning (GitHub Actions)

`.github/workflows/daily.yml` posts at `POST_AT` with no machine of your own. Put the two secrets
on the repository; type each one at the hidden prompt, never in a chat:

```bash
gh secret set TELEGRAM_BOT_TOKEN
gh secret set CHAT_ID
gh variable set CITY --body "Vienna; Graz"   # optional, like POST_AT, TZ, UNITS, ANSWER_BOT
```

"Run workflow" on the Actions tab posts right away. To stop the morning posts and start them again:

```bash
gh workflow disable daily.yml
gh workflow enable daily.yml
```

GitHub starts scheduled runs late at busy times, sometimes by half an hour. The workflow has two
UTC crons, 05:00 and 06:00, because 07:00 in Vienna is one in summer and the other in winter;
only the one that is `POST_AT` posts. Another `POST_AT` or `TZ` needs other hours there. In a
public repository GitHub turns schedules off after 60 days without a commit; enable it again.

## Settings

In `.env` for `inv send-now`; on GitHub as variables (`gh variable set`), except the two secrets.

| Variable | Default | Meaning |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | From @BotFather. Required; a secret on GitHub. |
| `CHAT_ID` | — | Where it posts, from `uv run inv chat-id`. Required; a secret on GitHub. |
| `CITY` | `Vienna` | Up to 10 cities separated by `;`, one post each: `Vienna; Paris, Texas`. |
| `POST_AT` | `07:00` | When to post, in `TZ`. |
| `TZ` | `Europe/Vienna` | Time zone for `POST_AT` and for "today". |
| `UNITS` | `metric` | `metric` or `imperial`. |
| `ANSWER_BOT` | — | The answer bot's @username; the bot's description points there. |

Each run also sets the bot's description, the text people see before pressing Start: the cities,
the time, and the answer bot.

## When something goes wrong

A run that didn't post every city fails, and GitHub emails you. The log says why:

- Open-Meteo down: three tries a minute apart, then one line in the chat saying there is no
  forecast for that city today. The other cities still post.
- No air-quality data: the post goes out without that line.
- "CITY 'Wienn': no such place": fix the spelling.
- "Telegram refused the post": check `CHAT_ID`, and that the bot may post there.
- "TELEGRAM_BOT_TOKEN rejected": make a new token in @BotFather.

## Development

```bash
uv run inv test      # offline; never contacts Telegram
uv run inv lint
uv run inv fixtures  # re-record the Open-Meteo responses the tests use
```

## Answer bot (stage 2)

A second bot anyone can ask: `/now Graz`, `/week Paris, Texas`, or just a city in a private chat.
Several at once, separated by `;`: `/now Vienna; Graz` answers each, up to 5. Add `°F` for
Fahrenheit; at the end it counts for every city. Its menu lists the commands, and its
description says what it does before anyone presses Start: set both once with
`uv run inv profile` (not on every start, so a cold start answers sooner).

It replies in English, German, Italian, French or Spanish: a local command (`/jetzt`, `/woche`,
`/ora`, `/settimana`, `/maintenant`, `/semaine`, `/ahora`, `/semana`) picks the language,
otherwise the Telegram app's language does.

Nothing about visitors is stored: no files, no database, and the logs name only the command and
the outcome. A 15-minute forecast cache, a limit of 10 questions a minute per chat and 60 a
minute for everyone together live in memory. Messages older than a minute are skipped, and the
webhook refuses a request without the secret header, or over 1 MB, before reading it.

### Hosting on Render (free)

1. In @BotFather, `/newbot` for the answer bot (keep privacy mode on).
2. On [Render](https://render.com): New → Blueprint → this repository. Render reads `render.yaml`,
   creates one free web service, and generates `WEBHOOK_SECRET`.
3. Paste the token into `ANSWER_BOT_TOKEN` when Render asks for it.
4. In Telegram, send `/now Vienna` and `/woche Wien` to the new bot.

Free services sleep after 15 minutes without traffic. A message wakes the service, so the first
reply after a pause takes about a minute. Deploys wait for CI to pass.

### Running it locally

    uv run inv answer      # long polling with ANSWER_BOT_TOKEN from .env

Polling removes the Render webhook. Afterwards, restart the service in Render's dashboard
(Manual Deploy → Restart service); on start it registers the webhook again.

## Data

[Weather data by Open-Meteo.com](https://open-meteo.com/), licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Place lookup uses
[GeoNames](https://www.geonames.org/) through Open-Meteo's geocoding API.
