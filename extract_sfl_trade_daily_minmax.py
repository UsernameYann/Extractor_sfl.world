#!/usr/bin/env python3
"""Extract SFL trade CSV data and keep only daily min/max per item."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://sfl.world"

# Embedded list to avoid downloading structure.json on daily runs.
ITEM_CSV_URLS: Dict[int, str] = {
    201: f"{BASE_URL}/api/v1/trade/csv/201.csv",
    202: f"{BASE_URL}/api/v1/trade/csv/202.csv",
    203: f"{BASE_URL}/api/v1/trade/csv/203.csv",
    204: f"{BASE_URL}/api/v1/trade/csv/204.csv",
    205: f"{BASE_URL}/api/v1/trade/csv/205.csv",
    206: f"{BASE_URL}/api/v1/trade/csv/206.csv",
    207: f"{BASE_URL}/api/v1/trade/csv/207.csv",
    208: f"{BASE_URL}/api/v1/trade/csv/208.csv",
    209: f"{BASE_URL}/api/v1/trade/csv/209.csv",
    210: f"{BASE_URL}/api/v1/trade/csv/210.csv",
    211: f"{BASE_URL}/api/v1/trade/csv/211.csv",
    212: f"{BASE_URL}/api/v1/trade/csv/212.csv",
    213: f"{BASE_URL}/api/v1/trade/csv/213.csv",
    214: f"{BASE_URL}/api/v1/trade/csv/214.csv",
    215: f"{BASE_URL}/api/v1/trade/csv/215.csv",
    216: f"{BASE_URL}/api/v1/trade/csv/216.csv",
    217: f"{BASE_URL}/api/v1/trade/csv/217.csv",
    251: f"{BASE_URL}/api/v1/trade/csv/251.csv",
    252: f"{BASE_URL}/api/v1/trade/csv/252.csv",
    253: f"{BASE_URL}/api/v1/trade/csv/253.csv",
    254: f"{BASE_URL}/api/v1/trade/csv/254.csv",
    255: f"{BASE_URL}/api/v1/trade/csv/255.csv",
    256: f"{BASE_URL}/api/v1/trade/csv/256.csv",
    257: f"{BASE_URL}/api/v1/trade/csv/257.csv",
    258: f"{BASE_URL}/api/v1/trade/csv/258.csv",
    259: f"{BASE_URL}/api/v1/trade/csv/259.csv",
    260: f"{BASE_URL}/api/v1/trade/csv/260.csv",
    261: f"{BASE_URL}/api/v1/trade/csv/261.csv",
    262: f"{BASE_URL}/api/v1/trade/csv/262.csv",
    263: f"{BASE_URL}/api/v1/trade/csv/263.csv",
    264: f"{BASE_URL}/api/v1/trade/csv/264.csv",
    265: f"{BASE_URL}/api/v1/trade/csv/265.csv",
    266: f"{BASE_URL}/api/v1/trade/csv/266.csv",
    267: f"{BASE_URL}/api/v1/trade/csv/267.csv",
    268: f"{BASE_URL}/api/v1/trade/csv/268.csv",
    601: f"{BASE_URL}/api/v1/trade/csv/601.csv",
    602: f"{BASE_URL}/api/v1/trade/csv/602.csv",
    603: f"{BASE_URL}/api/v1/trade/csv/603.csv",
    604: f"{BASE_URL}/api/v1/trade/csv/604.csv",
    605: f"{BASE_URL}/api/v1/trade/csv/605.csv",
    614: f"{BASE_URL}/api/v1/trade/csv/614.csv",
    636: f"{BASE_URL}/api/v1/trade/csv/636.csv",
    641: f"{BASE_URL}/api/v1/trade/csv/641.csv",
    642: f"{BASE_URL}/api/v1/trade/csv/642.csv",
    643: f"{BASE_URL}/api/v1/trade/csv/643.csv",
    644: f"{BASE_URL}/api/v1/trade/csv/644.csv",
    645: f"{BASE_URL}/api/v1/trade/csv/645.csv",
    663: f"{BASE_URL}/api/v1/trade/csv/663.csv",
    665: f"{BASE_URL}/api/v1/trade/csv/665.csv",
    2631: f"{BASE_URL}/api/v1/trade/csv/2631.csv",
    2632: f"{BASE_URL}/api/v1/trade/csv/2632.csv",
    2633: f"{BASE_URL}/api/v1/trade/csv/2633.csv",
    2634: f"{BASE_URL}/api/v1/trade/csv/2634.csv",
    2636: f"{BASE_URL}/api/v1/trade/csv/2636.csv",
    2637: f"{BASE_URL}/api/v1/trade/csv/2637.csv",
    2638: f"{BASE_URL}/api/v1/trade/csv/2638.csv",
    2639: f"{BASE_URL}/api/v1/trade/csv/2639.csv",
    2986: f"{BASE_URL}/api/v1/trade/csv/2986.csv",
    2987: f"{BASE_URL}/api/v1/trade/csv/2987.csv",
    2988: f"{BASE_URL}/api/v1/trade/csv/2988.csv",
}


def fetch_text(url: str, timeout: int = 30) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/csv,application/json,text/plain,*/*",
        },
    )
    with urlopen(req, timeout=timeout) as response:
        raw = response.read()
    return raw.decode("utf-8")


def fetch_text_with_retry(
    url: str,
    timeout: int,
    retry_max_attempts: int,
    retry_backoff_seconds: float,
) -> str:
    retryable_statuses = {429, 500, 502, 503, 504}

    for attempt in range(1, retry_max_attempts + 1):
        try:
            return fetch_text(url, timeout=timeout)
        except HTTPError as exc:
            is_retryable = exc.code in retryable_statuses
            is_last = attempt >= retry_max_attempts
            if (not is_retryable) or is_last:
                raise
        except URLError:
            is_last = attempt >= retry_max_attempts
            if is_last:
                raise

        delay = retry_backoff_seconds * (2 ** (attempt - 1))
        time.sleep(delay)

    raise RuntimeError("Unreachable retry state")


def iter_items() -> Iterable[Tuple[int, str]]:
    for item_id in sorted(ITEM_CSV_URLS.keys()):
        yield item_id, ITEM_CSV_URLS[item_id]


def parse_csv_points(csv_text: str) -> Iterable[Tuple[str, float]]:
    for line in csv_text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) < 2:
            continue
        ts = parts[0].strip()
        raw_value = parts[1].strip()

        try:
            # Input format example: 2026-05-07T13:00:00Z
            day = datetime.fromisoformat(ts.replace("Z", "+00:00")).date().isoformat()
            value = float(raw_value)
        except ValueError:
            continue

        yield day, value


def compute_daily_minmax(points: Iterable[Tuple[str, float]]) -> Dict[str, Tuple[float, float, int]]:
    result: Dict[str, Tuple[float, float, int]] = {}
    for day, value in points:
        if day not in result:
            result[day] = (value, value, 1)
            continue

        current_min, current_max, count = result[day]
        new_min = value if value < current_min else current_min
        new_max = value if value > current_max else current_max
        result[day] = (new_min, new_max, count + 1)

    return result


def rolling_window_bounds_utc(days: int = 30) -> Tuple[date, date]:
    # Keep only fully completed UTC days: [today-(days), today-1]
    today_utc = datetime.now(timezone.utc).date()
    end_date = today_utc - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)
    return start_date, end_date


def is_in_window(day_iso: str, start_date: date, end_date: date) -> bool:
    try:
        day = datetime.strptime(day_iso, "%Y-%m-%d").date()
    except ValueError:
        return False
    return start_date <= day <= end_date


def write_output(rows: List[Dict[str, object]], output_path: Path, compact: bool) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    by_item: Dict[int, List[Dict[str, object]]] = {}

    for row in rows:
        item_id = cast(int, row["item_id"])
        by_item.setdefault(item_id, []).append(
            {
                "date": row["date"],
                "mini": row["mini"],
                "max": row["max"],
            }
        )

    payload = {str(item_id): by_item[item_id] for item_id in sorted(by_item.keys())}

    with output_path.open("w", encoding="utf-8") as f:
        if compact:
            json.dump(payload, f, ensure_ascii=True, separators=(",", ":"))
        else:
            json.dump(payload, f, ensure_ascii=True, indent=2)
        f.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download SFL trade CSV files and export daily min/max values as JSON (rolling 30 complete UTC days, static item URL constants)."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("daily_minmax_all.json"),
        help="Output JSON path.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Write compact JSON without indentation.",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=30,
        help="Number of complete UTC days to keep (default: 30).",
    )
    parser.add_argument(
        "--throttle-ms",
        type=int,
        default=200,
        help="Delay between API calls in milliseconds (default: 200).",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="HTTP timeout in seconds (default: 30).",
    )
    parser.add_argument(
        "--retry-max-attempts",
        type=int,
        default=4,
        help="Max attempts for retryable API failures (default: 4).",
    )
    parser.add_argument(
        "--retry-backoff-seconds",
        type=float,
        default=1.0,
        help="Base backoff in seconds (default: 1.0).",
    )
    args = parser.parse_args()

    rows: List[Dict[str, object]] = []
    items = list(iter_items())

    if not items:
        print("ERROR: No valid items found in structure.", file=sys.stderr)
        return 1

    if args.window_days < 1:
        print("ERROR: --window-days must be >= 1", file=sys.stderr)
        return 1
    if args.throttle_ms < 0:
        print("ERROR: --throttle-ms must be >= 0", file=sys.stderr)
        return 1
    if args.timeout_seconds < 1:
        print("ERROR: --timeout-seconds must be >= 1", file=sys.stderr)
        return 1
    if args.retry_max_attempts < 1:
        print("ERROR: --retry-max-attempts must be >= 1", file=sys.stderr)
        return 1
    if args.retry_backoff_seconds <= 0:
        print("ERROR: --retry-backoff-seconds must be > 0", file=sys.stderr)
        return 1

    start_date, end_date = rolling_window_bounds_utc(days=args.window_days)

    throttle_seconds = args.throttle_ms / 1000.0

    for index, (item_id, csv_url) in enumerate(items):
        try:
            csv_text = fetch_text_with_retry(
                csv_url,
                timeout=args.timeout_seconds,
                retry_max_attempts=args.retry_max_attempts,
                retry_backoff_seconds=args.retry_backoff_seconds,
            )
        except (HTTPError, URLError) as exc:
            local_csv = Path(f"{item_id}.csv")
            if local_csv.exists():
                csv_text = local_csv.read_text(encoding="utf-8")
                print(
                    f"INFO: Remote fetch failed for {item_id}, use local {local_csv.name}",
                    file=sys.stderr,
                )
            else:
                print(f"WARN: Skip {item_id}, fetch failed: {exc}", file=sys.stderr)
                continue

        if throttle_seconds > 0 and index < len(items) - 1:
            time.sleep(throttle_seconds)

        daily = compute_daily_minmax(parse_csv_points(csv_text))
        for day in sorted(daily.keys()):
            if not is_in_window(day, start_date, end_date):
                continue
            min_v, max_v, count = daily[day]
            rows.append(
                {
                    "item_id": item_id,
                    "date": day,
                    "mini": float(format(min_v, ".12g")),
                    "max": float(format(max_v, ".12g")),
                }
            )

    rows.sort(
        key=lambda r: (
            cast(int, r["item_id"]),
            cast(str, r["date"]),
        )
    )
    write_output(rows, args.output, compact=args.compact)

    print(
        f"Done. {len(items)} items processed, {len(rows)} daily rows written to {args.output} "
        f"for UTC window {start_date.isoformat()} -> {end_date.isoformat()} (today excluded)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
