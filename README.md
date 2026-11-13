# CS-project-regional-price
price differences across the uzbekistan cities
# Regional Price & Deals — Fergana Valley Channel Platform

Course project (CS Python, TTPU 2026-27).

A Django-managed Telegram channel platform for the Fergana Valley region
(Qo'qon, Farg'ona, Andijon, Namangan, Marg'ilon), helping subscribers
save money through promotions, price tracking, price comparison,
product reviews, life hacks, and store news.

**Status:** In development (Week 2 of 8) — Parts 1–7 done (Docker skeleton, apps, location, catalog and price models).

## Stack
- Python 3.11+
- Django 5.x
- SQLite (shared Docker volume)
- python-telegram-bot 21.x
- Docker Compose (web + worker services)

## Setup
Requirements: Docker with Docker Compose, and a Telegram bot token from
[@BotFather](https://t.me/BotFather).

1. Create your local settings file and fill in `TELEGRAM_BOT_TOKEN`:
   ```bash
   cp .env.example .env
   ```
2. Build and start both services:
   ```bash
   docker compose up --build
   ```
3. Open http://localhost:8000/ (site) or http://localhost:8000/health/
   (health check). In Telegram, send `/start`, `/ping` or `/status` to the bot.
4. Create an admin user for http://localhost:8000/admin/:
   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

Useful commands:
```bash
docker compose exec web python manage.py test   # run the Django tests
docker compose logs -f worker                   # follow the bot logs
docker compose down                             # stop (add -v to delete the database)
```

## Project structure
```
docker-compose.yml   two services + the shared "data" volume
.env.example         template for the local .env file
web/                 Django project (config = settings, core = app)
worker/              Telegram bot (python-telegram-bot, long polling)
```

- **web** applies migrations on start and serves Django on port 8000.
- **worker** starts after web is healthy and runs the bot. Without a
  token it stops with an error message in the logs.
- Both services mount the `data` volume at `/data`, so they use the same
  SQLite file, `/data/db.sqlite3`.

## Architecture
_Diagram and explanation coming in Part 30._

## License
Educational project — TTPU CS 2026-27.