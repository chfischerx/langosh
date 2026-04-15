"""RSS feed tool for LangGraph agents — fetch and parse RSS feeds."""

import asyncio
import logging
import urllib.request
import xml.etree.ElementTree as ET
from urllib.error import URLError

logger = logging.getLogger(__name__)


def _fetch_articles_raw(url: str, max_items: int = 30) -> list[dict]:
    """Fetch and parse an RSS feed, returning a list of article dicts."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        xml_data = resp.read()

    root = ET.fromstring(xml_data)

    # Handle both RSS (<channel><item>) and Atom (<entry>) feeds
    channel = root.find("channel")
    if channel is not None:
        items = channel.findall("item")[:max_items]
    else:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall("atom:entry", ns)[:max_items]

    articles = []
    for item in items:
        title = (item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title") or "Untitled").strip()
        link = (item.findtext("link") or "").strip()
        # Atom links are in an attribute
        if not link:
            link_el = item.find("{http://www.w3.org/2005/Atom}link")
            if link_el is not None:
                link = link_el.get("href", "").strip()
        desc = (item.findtext("description") or item.findtext("{http://www.w3.org/2005/Atom}summary") or "").strip()
        pub_date = (item.findtext("pubDate") or item.findtext("{http://www.w3.org/2005/Atom}published") or "").strip()

        articles.append({
            "title": title,
            "link": link,
            "description": desc[:500],
            "pub_date": pub_date,
        })

    return articles


def _format_articles(articles: list[dict]) -> str:
    """Format articles into a readable string."""
    parts = []
    for i, a in enumerate(articles, 1):
        entry = f"{i}. {a['title']}"
        if a["pub_date"]:
            entry += f"\n   {a['pub_date']}"
        if a["description"]:
            entry += f"\n   {a['description'][:200]}"
        if a["link"]:
            entry += f"\n   {a['link']}"
        parts.append(entry)
    return "\n\n".join(parts)


async def fetch_rss(url: str, max_items: int = 30) -> str:
    """Fetch and parse an RSS or Atom feed.

    Args:
        url: RSS/Atom feed URL to fetch
        max_items: Maximum number of items to return (default 30)

    Returns:
        Formatted article list, or error message if fetch fails
    """
    try:
        articles = await asyncio.to_thread(_fetch_articles_raw, url, max_items)

        if not articles:
            return f"No articles found in feed at {url}"

        return f"Found {len(articles)} articles:\n\n{_format_articles(articles)}"

    except URLError as e:
        return f"Error fetching feed from {url}: {e}"
    except ET.ParseError as e:
        return f"Error parsing feed from {url}: {e}"
    except Exception as e:
        return f"Unexpected error fetching feed: {e}"
