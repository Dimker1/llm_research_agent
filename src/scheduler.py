"""
生产调度器：每周一定时运行周报生成任务。
用法：python -m src.scheduler
"""

import logging

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _load_schedule() -> dict:
    try:
        with open("config/settings.yaml", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cfg.get("scheduler", {})
    except Exception:
        return {}


def _run():
    from src.main import run_weekly
    logger.info("[scheduler] triggering weekly digest...")
    try:
        run_weekly()
    except Exception as e:
        logger.error(f"[scheduler] weekly digest failed: {e}", exc_info=True)


def main():
    schedule_cfg = _load_schedule()
    day_of_week = schedule_cfg.get("day_of_week", "mon")
    hour = schedule_cfg.get("hour", 9)
    minute = schedule_cfg.get("minute", 0)
    tz = schedule_cfg.get("timezone", "Asia/Shanghai")

    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(
        _run, "cron",
        day_of_week=day_of_week,
        hour=hour, minute=minute,
        id="weekly_digest",
    )

    logger.info(
        f"[scheduler] started — will run every {day_of_week.upper()} at {hour:02d}:{minute:02d} {tz}"
    )
    logger.info("[scheduler] press Ctrl+C to stop")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("[scheduler] stopped")


if __name__ == "__main__":
    main()
