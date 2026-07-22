# Shadow Worker

v0 shell: capture rambling thoughts via a Telegram bot, triage them into tasks with an
LLM, and surface a prioritized daily/weekly/monthly view. See
`.claude/plans` (or the plan shared with you) for the full design and build milestones.

## Setup

1. Create a Telegram bot via [@BotFather](https://t.me/BotFather):
   - `/newbot` and follow the prompts to get a token.
   - In bot settings, disable "Allow Groups" (`/setjoingroups` -> disable).
   - Don't share the bot's username publicly.
2. Generate a start secret: `python -c "import secrets; print(secrets.token_urlsafe(16))"`
3. Create a free [Neon](https://neon.tech) Postgres project and grab its connection string
   (use the `postgresql+asyncpg://...` form for `DATABASE_URL`).
4. Copy `.env.example` to `.env` and fill in the values.
5. Install dependencies: `pip install -e ".[dev]"`
6. Apply the schema: `alembic upgrade head`
7. Sanity-check your LLM config before running the bot: `python scripts/validate_llm.py`
   (swap `LLM_PROVIDER`/`LLM_MODEL`/`LLM_BASE_URL` in `.env` to try DeepSeek or Ollama —
   no code changes needed)
8. Run the bot: `python -m app.bot.main`
9. Claim the bot by opening `https://t.me/<your_bot_username>?start=<TELEGRAM_START_SECRET>`.

## Local development

Use a **second** bot (e.g. `yourapp_dev_bot`) and a **second** free Neon project for local
testing, so you never run two pollers against the same token and never mix test data into
your real digest. Point your local `.env` at the dev bot/database; keep the prod
bot/database only in the deployed environment's secrets.

## Deploying (Fly.io)

1. Install the Fly CLI and log in: `curl -L https://fly.io/install.sh | sh`, then `fly auth login`.
2. Repeat steps 1-3 above for a **separate prod** bot token + Neon project (keep this
   distinct from your dev bot/database).
3. Edit `fly.toml`'s `app` name to something globally unique, or let `fly launch` pick one
   for you (it will detect the `Dockerfile` and reuse this `fly.toml`).
4. Set secrets instead of using a `.env` file in production:
   ```
   fly secrets set \
     TELEGRAM_BOT_TOKEN=... \
     TELEGRAM_START_SECRET=... \
     DATABASE_URL=... \
     LLM_PROVIDER=... \
     LLM_MODEL=... \
     LLM_API_KEY=... \
     LLM_BASE_URL=... \
     DIGEST_HOUR=7 \
     TZ=...
   ```
5. Apply the schema against the prod database once (locally, pointed at the prod
   `DATABASE_URL`, or via `fly ssh console` after first deploy): `alembic upgrade head`
6. Deploy: `fly deploy`
7. Claim the deployed bot the same way as local: open
   `https://t.me/<your_prod_bot_username>?start=<TELEGRAM_START_SECRET>`.
8. Watch for the 07:00 daily push to arrive unattended for a couple of days — that's the
   real acceptance test for the shell.
