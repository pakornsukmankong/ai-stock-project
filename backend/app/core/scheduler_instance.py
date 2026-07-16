from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Pin to UTC so cron jobs fire at deterministic UTC hours regardless of the
# host's timezone. All job schedules are expressed in UTC (e.g. the SET pre-open
# briefing at 02:00 UTC = 09:00 ICT).
scheduler = AsyncIOScheduler(timezone="UTC")
