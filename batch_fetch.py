"""
batch_fetch.py — 批次預先抓取所有站點資料
使用方式：python batch_fetch.py [--skip-existing] [--line R]

GEMINI_API_KEY 需設為環境變數
"""
import asyncio, json, logging, argparse
from pathlib import Path
from main import STATION_NAMES, DATA_DIR, fetch_and_cache

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def run_batch(skip_existing: bool, line_filter: str | None, concurrency: int = 3):
    stations = list(STATION_NAMES.keys())
    if line_filter:
        stations = [s for s in stations if s.startswith(line_filter.upper())]

    if skip_existing:
        stations = [s for s in stations if not (DATA_DIR / f"{s}.json").exists()]

    logger.info(f"Will fetch {len(stations)} stations (concurrency={concurrency})")

    sem = asyncio.Semaphore(concurrency)

    async def fetch_one(sid):
        async with sem:
            await fetch_and_cache(sid)
            await asyncio.sleep(1.5)  # 避免 rate limit

    tasks = [fetch_one(sid) for sid in stations]
    await asyncio.gather(*tasks)

    cached = len(list(DATA_DIR.glob("*.json")))
    logger.info(f"Done. Cached: {cached}/{len(STATION_NAMES)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument("--line", type=str, default=None, help="只抓特定線路，如 R, BL, G")
    parser.add_argument("--concurrency", type=int, default=3)
    args = parser.parse_args()
    asyncio.run(run_batch(args.skip_existing, args.line, args.concurrency))
