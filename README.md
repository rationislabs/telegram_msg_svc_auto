# telegram_msg_svc_auto

Every morning, one Telegram post with the day's weather for your city: a short caption you can
read in the notification, and a chart of today's temperature and chance of rain.

<!-- screenshot of a post -->

## Set up

1. **Get a bot token.** In Telegram, talk to [@BotFather](https://t.me/BotFather): `/newbot`.
   If a token was ever pasted into a chat, `/revoke` it and use the new one.
2. **Make a private channel** and add the bot as an admin with **Post messages**.
3. Fill in `.env`:

   ```bash
   cp .env.example .env && chmod 600 .env   # then paste TELEGRAM_BOT_TOKEN
   uv sync
   # post any message in the channel, then:
   uv run inv chat-id                        # copy the channel's id (-100…) into CHAT_ID
   uv run inv send-now                       # a post right now, to check how it looks
   ```

4. **Run it:**

   ```bash
   docker compose up -d --build
   ```

It posts at `POST_AT` in `TZ`. If the machine was asleep then, it posts as soon as it is back,
the same day, once.

## Watching the containers

To watch the containers, images, volumes and logs in a terminal UI, run [lazydocker](https://github.com/jesseduffield/lazydocker) (optional):

```bash
lazydocker
```

## Settings (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | From @BotFather. Required. |
| `CHAT_ID` | — | The channel, from `uv run inv chat-id`. Required. |
| `CITY` | `Vienna` | Looked up once at start; the log says which place it found. |
| `POST_AT` | `07:00` | When to post, in `TZ`. |
| `TZ` | `Europe/Vienna` | Time zone for `POST_AT` and for "today". |
| `UNITS` | `metric` | `metric` or `imperial`. |

## When something goes wrong

- Open-Meteo down: it retries every 15 minutes, four times, then posts one line saying there is
  no forecast today.
- No air-quality data: the post goes out without that line.
- "Telegram refused the post" in the logs: check `CHAT_ID` and that the bot is an admin of the
  channel with Post messages.
- "TELEGRAM_BOT_TOKEN rejected": make a new token in @BotFather.

## Development

```bash
uv run inv test      # offline; never contacts Telegram
uv run inv lint
uv run inv fixtures  # re-record the Open-Meteo responses the tests use
```

## Data

[Weather data by Open-Meteo.com](https://open-meteo.com/), licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Place lookup uses
[GeoNames](https://www.geonames.org/) through Open-Meteo's geocoding API.
