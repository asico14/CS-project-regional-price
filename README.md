# CS-project-regional-price
price differences across the uzbekistan cities
# Regional Price & Deals — Fergana Valley Channel Platform

Course project (CS Python, TTPU 2026-27).

A Django-managed Telegram channel platform for the Fergana Valley region
(Qo'qon, Farg'ona, Andijon, Namangan, Marg'ilon), helping subscribers
save money through promotions, price tracking, price comparison,
product reviews, life hacks, and store news.

**Status:** In development — Parts 1–20 of 30 done (catalog, prices, baskets, staff pages, Post model).

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
5. (Optional) Load demo data — cities, stores, products, 30 days of prices, promotions:
   ```bash
   docker compose exec web python manage.py seed_demo
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
  SQLite file, `/data/db.sqlite3`, and the same uploaded photos, `/data/media`.

## Languages
Uzbek is the default language and Russian is the second one. The
buttons in the top bar switch the site language. Every post has its
own language, and generated posts come from one set of templates
(`web/templates/posts/generators/`) translated through gettext.

Translations live in `web/locale/<language>/LC_MESSAGES/django.po`.
The compiled `django.mo` files are committed too, so the Docker image
does not need the gettext tools. After editing a `.po` file run
`python manage.py compilemessages` (needs gettext installed).

Only the navigation, login and home page are translated so far; the
other staff pages are still in English.

## Pages (staff only)
Log in at http://localhost:8000/login/ with a staff account
(`createsuperuser` makes one).

| Page | URL |
|---|---|
| Enter today's prices for a store | `/prices/entry/` |
| Products: list, search, add, edit | `/products/` |
| Product: current prices and 30-day price chart | `/products/<id>/` |
| Stores: list by city, add, edit | `/stores/` |
| Baskets: compare the cost of a shopping list between stores | `/baskets/` |
| Admin (all data, including posts) | `/admin/` |

## Architecture
_Diagram and explanation coming in Part 30._

## License
Educational project — TTPU CS 2026-27.