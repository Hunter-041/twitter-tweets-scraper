thonimport csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

logger = logging.getLogger(__name__)

def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

def _flatten_for_tabular(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    flattened: List[Dict[str, Any]] = []
    for row in rows:
        user = row.get("user") or {}
        flat_row = {
            "bookmark_count": row.get("bookmark_count"),
            "created_at": row.get("created_at"),
            "conversation_id_str": row.get("conversation_id_str"),
            "favorite_count": row.get("favorite_count"),
            "full_text": row.get("full_text"),
            "reply_count": row.get("reply_count"),
            "retweet_count": row.get("retweet_count"),
            "views_count": row.get("views_count"),
            "user_name": user.get("name"),
            "user_followers_count": user.get("followers_count"),
            "user_screen_name": user.get("screen_name"),
            "user_url": user.get("url"),
        }
        flattened.append(flat_row)
    return flattened

def _export_json(data: List[Dict[str, Any]], output_path: Path) -> None:
    _ensure_parent_dir(output_path)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Exported %d tweet(s) to JSON: %s", len(data), output_path)

def _export_csv(data: List[Dict[str, Any]], output_path: Path) -> None:
    _ensure_parent_dir(output_path)
    flattened = _flatten_for_tabular(data)
    if not flattened:
        # Write an empty CSV with headers
        headers = [
            "bookmark_count",
            "created_at",
            "conversation_id_str",
            "favorite_count",
            "full_text",
            "reply_count",
            "retweet_count",
            "views_count",
            "user_name",
            "user_followers_count",
            "user_screen_name",
            "user_url",
        ]
        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
    else:
        headers = list(flattened[0].keys())
        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for row in flattened:
                writer.writerow(row)

    logger.info("Exported %d tweet(s) to CSV: %s", len(data), output_path)

def _export_excel(data: List[Dict[str, Any]], output_path: Path) -> None:
    _ensure_parent_dir(output_path)
    flattened = _flatten_for_tabular(data)
    df = pd.DataFrame(flattened)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="tweets")
    logger.info("Exported %d tweet(s) to Excel: %s", len(data), output_path)

def _export_xml(data: List[Dict[str, Any]], output_path: Path) -> None:
    from xml.etree.ElementTree import Element, SubElement, ElementTree

    _ensure_parent_dir(output_path)

    root = Element("tweets")
    for row in data:
        tweet_el = SubElement(root, "tweet")
        for key in (
            "bookmark_count",
            "created_at",
            "conversation_id_str",
            "favorite_count",
            "full_text",
            "reply_count",
            "retweet_count",
            "views_count",
        ):
            val = row.get(key)
            if val is None:
                continue
            child = SubElement(tweet_el, key)
            child.text = str(val)

        user = row.get("user") or {}
        user_el = SubElement(tweet_el, "user")
        for key in ("name", "followers_count", "screen_name", "url"):
            val = user.get(key)
            if val is None:
                continue
            child = SubElement(user_el, key)
            child.text = str(val)

    tree = ElementTree(root)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    logger.info("Exported %d tweet(s) to XML: %s", len(data), output_path)

def _export_html(data: List[Dict[str, Any]], output_path: Path) -> None:
    _ensure_parent_dir(output_path)
    flattened = _flatten_for_tabular(data)
    df = pd.DataFrame(flattened)

    html_table = df.to_html(index=False, escape=True)
    html_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Twitter Tweets Scraper - Export</title>
    <style>
        body {{
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            margin: 2rem;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 0.5rem;
            vertical-align: top;
        }}
        th {{
            background-color: #f4f4f4;
        }}
    </style>
</head>
<body>
<h1>Twitter Tweets Export</h1>
<p>Total tweets: {len(data)}</p>
{html_table}
</body>
</html>
"""
    with output_path.open("w", encoding="utf-8") as f:
        f.write(html_page)

    logger.info("Exported %d tweet(s) to HTML: %s", len(data), output_path)

def export_data(data: List[Dict[str, Any]], fmt: str, output_path: Path) -> None:
    fmt = fmt.lower()
    if fmt == "json":
        _export_json(data, output_path)
    elif fmt == "csv":
        _export_csv(data, output_path)
    elif fmt == "excel":
        _export_excel(data, output_path)
    elif fmt == "xml":
        _export_xml(data, output_path)
    elif fmt == "html":
        _export_html(data, output_path)
    else:
        raise ValueError(f"Unsupported export format: {fmt}")