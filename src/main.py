thonimport argparse
import json
import logging
from pathlib import Path
from typing import List, Optional

from extractors.twitter_parser import scrape_tweets_for_urls
from extractors.utils_date import parse_since_date, default_since_date
from outputs.exporter import export_data

def load_settings(config_path: Path) -> dict:
    if not config_path.exists():
        logging.warning("Config file %s not found. Using built-in defaults.", config_path)
        return {}

    try:
        with config_path.open("r", encoding="utf-8") as f:
            settings = json.load(f)
        if not isinstance(settings, dict):
            logging.warning("Config file %s does not contain a JSON object. Ignoring.", config_path)
            return {}
        return settings
    except Exception as exc:
        logging.error("Failed to read config from %s: %s", config_path, exc)
        return {}

def resolve_since_date(cli_since: Optional[str], settings: dict):
    if cli_since:
        dt = parse_since_date(cli_since)
        if dt is None:
            logging.error("Invalid --since-date value %s. Falling back to default.", cli_since)
            return default_since_date()
        return dt

    cfg_since = settings.get("since_date")
    if cfg_since:
        dt = parse_since_date(cfg_since)
        if dt is None:
            logging.error("Invalid since_date in settings.json. Falling back to default.")
            return default_since_date()
        return dt

    return default_since_date()

def resolve_export_format(cli_format: Optional[str], settings: dict) -> str:
    if cli_format:
        return cli_format.lower()

    cfg_fmt = settings.get("export_format")
    if isinstance(cfg_fmt, str):
        return cfg_fmt.lower()

    return "json"

def resolve_output_path(
    cli_output: Optional[str],
    export_format: str,
    base_dir: Path,
    settings: dict,
) -> Path:
    if cli_output:
        return Path(cli_output).expanduser().resolve()

    output_dir = settings.get("output_dir") or "data"
    output_file = settings.get("output_filename")

    if not output_file:
        output_file = f"sample_output.{export_format}"

    out_path = (base_dir / output_dir / output_file).resolve()
    return out_path

def read_urls_from_file(path: Path) -> List[str]:
    if not path.exists():
        logging.error("Input file %s does not exist.", path)
        return []

    urls: List[str] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)

    if not urls:
        logging.warning("No URLs found in input file %s.", path)
    return urls

def configure_logging(level_name: Optional[str] = None) -> None:
    level = logging.INFO
    if level_name:
        try:
            level = getattr(logging, level_name.upper(), logging.INFO)
        except Exception:
            level = logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Twitter Tweets Scraper - fetch tweets from public Twitter profiles."
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="Twitter profile URLs (e.g. https://twitter.com/elonmusk). "
             "If omitted, --input-file is used, or data/sample_input.txt by default.",
    )
    parser.add_argument(
        "--input-file",
        "-i",
        help="Path to a text file containing one Twitter URL per line.",
    )
    parser.add_argument(
        "--since-date",
        "-s",
        help="Only include tweets created on or after this date. "
             "Examples: 2024-03-05 or 2024-03-05T00:00:00.",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["json", "csv", "excel", "xml", "html"],
        help="Export format for the scraped tweets (default: json).",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Path to the output file. If not provided, a default under ./data is used.",
    )
    parser.add_argument(
        "--log-level",
        help="Logging level (DEBUG, INFO, WARNING, ERROR). "
             "If not set, falls back to config or INFO.",
    )
    return parser.parse_args()

def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "src" / "config" / "settings.json"
    settings = load_settings(config_path)

    cli_args = parse_args()

    log_level = cli_args.log_level or settings.get("log_level") or "INFO"
    configure_logging(log_level)
    logging.debug("Project root resolved to %s", project_root)

    since_dt = resolve_since_date(cli_args.since_date, settings)
    logging.info("Using since_date filter: %s", since_dt.isoformat())

    export_format = resolve_export_format(cli_args.format, settings)
    logging.info("Using export format: %s", export_format)

    urls: List[str] = []
    if cli_args.urls:
        urls = cli_args.urls
    else:
        input_file = cli_args.input_file
        if input_file:
            urls = read_urls_from_file(Path(input_file))
        else:
            default_input = project_root / "data" / "sample_input.txt"
            logging.info("No URLs provided. Reading from default input file %s", default_input)
            urls = read_urls_from_file(default_input)

    if not urls:
        logging.error("No valid Twitter URLs supplied. Exiting.")
        return

    logging.info("Starting scrape for %d URL(s).", len(urls))

    try:
        tweets = scrape_tweets_for_urls(urls, since_dt)
    except Exception as exc:
        logging.exception("Unhandled error while scraping tweets: %s", exc)
        return

    if not tweets:
        logging.warning("No tweets scraped for the given inputs and filters.")
    else:
        logging.info("Scraped %d tweet(s).", len(tweets))

    output_path = resolve_output_path(cli_args.output, export_format, project_root, settings)
    try:
        export_data(tweets, export_format, output_path)
    except Exception as exc:
        logging.exception("Failed to export data: %s", exc)
        return

    logging.info("Export completed successfully: %s", output_path)

if __name__ == "__main__":
    main()