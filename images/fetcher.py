import os
import re
import json
import hashlib
from datetime import datetime

import requests
from bs4 import BeautifulSoup

import config

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "this", "that", "these", "those", "and", "but", "or", "nor", "not",
    "for", "with", "about", "from", "into", "through", "during", "before",
    "after", "above", "below", "between", "out", "off", "over", "under",
    "again", "further", "then", "once", "here", "there", "when", "where",
    "why", "how", "all", "each", "every", "both", "few", "more", "most",
    "other", "some", "such", "only", "own", "same", "than", "too", "very",
    "just", "because", "much", "now", "also", "back", "new", "way",
    "breaking", "tweet", "post", "fact", "take", "people", "realize",
    "don't", "here's", "what", "it's", "they", "them", "their", "you",
    "your", "most", "many", "still", "even", "well", "almost",
}


def should_attach_image(post_type):
    """Decide if this tweet type should get an image."""
    # Engagement questions perform better text-only
    if post_type == "question":
        return False
    return True


def extract_article_image(article_url):
    """Extract og:image or twitter:image from an article URL.
    Returns (image_url, source_type) or (None, None).
    """
    try:
        resp = requests.get(article_url, headers=HEADERS, timeout=8, allow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return None, None

    try:
        soup = BeautifulSoup(resp.text[:50000], "html.parser")  # Limit parsing to first 50KB
    except Exception:
        return None, None

    # Try og:image first
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        url = og["content"].strip()
        if url and _is_valid_image_url(url):
            return _make_absolute(url, article_url), "article_og"

    # Try twitter:image
    tw = soup.find("meta", attrs={"name": "twitter:image"})
    if tw and tw.get("content"):
        url = tw["content"].strip()
        if url and _is_valid_image_url(url):
            return _make_absolute(url, article_url), "article_twitter"

    return None, None


def extract_keywords(tweet_text):
    """Extract 2-3 search keywords from tweet content."""
    # Remove emojis and special chars
    clean = re.sub(r"[^\w\s]", " ", tweet_text)
    clean = re.sub(r"\s+", " ", clean).strip()

    words = clean.lower().split()
    # Filter: remove stopwords, short words, numbers
    keywords = [w for w in words if len(w) >= 4 and w not in STOPWORDS and not w.isdigit()]

    # Take top 3 longest (usually the most specific)
    keywords.sort(key=len, reverse=True)
    return keywords[:3]


def search_unsplash(keywords, api_key):
    """Search Unsplash for a landscape image. Returns URL or None."""
    if not api_key:
        return None
    query = " ".join(keywords)
    try:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": 3, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {api_key}"},
            timeout=8,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            return results[0]["urls"]["regular"]
    except Exception:
        pass
    return None


def search_pexels(keywords, api_key):
    """Search Pexels for a landscape image. Returns URL or None."""
    if not api_key:
        return None
    query = " ".join(keywords)
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": 3, "orientation": "landscape"},
            headers={"Authorization": api_key},
            timeout=8,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if photos:
            return photos[0]["src"]["large"]
    except Exception:
        pass
    return None


def find_image_for_post(post_content, source_urls_json, image_config=None, exclude_urls=None):
    """Find the best image for a tweet, avoiding already-used images.
    Returns (image_url, source_type) or (None, None).
    """
    if exclude_urls is None:
        exclude_urls = set()

    source_urls = []
    if source_urls_json:
        try:
            source_urls = json.loads(source_urls_json) if isinstance(source_urls_json, str) else source_urls_json
        except (json.JSONDecodeError, TypeError):
            pass

    # Strategy 1: Extract from source articles (free, most relevant)
    for url in source_urls[:5]:
        if url:
            img_url, source_type = extract_article_image(url)
            if img_url and img_url not in exclude_urls:
                return img_url, source_type

    # Strategy 2: Stock photo search
    keywords = extract_keywords(post_content)
    if keywords and image_config:
        unsplash_key = image_config.get("unsplash_api_key", "") or getattr(config, "UNSPLASH_ACCESS_KEY", "")
        pexels_key = image_config.get("pexels_api_key", "") or getattr(config, "PEXELS_API_KEY", "")

        img_url = search_unsplash(keywords, unsplash_key)
        if img_url and img_url not in exclude_urls:
            return img_url, "unsplash"

        img_url = search_pexels(keywords, pexels_key)
        if img_url and img_url not in exclude_urls:
            return img_url, "pexels"

    return None, None


def download_image(image_url, post_id="0"):
    """Download image to local data/images/ directory. Returns local path or None."""
    image_dir = getattr(config, "IMAGE_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "images"))
    os.makedirs(image_dir, exist_ok=True)

    try:
        resp = requests.get(image_url, headers=HEADERS, timeout=15, stream=True)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "jpeg" in content_type or "jpg" in content_type:
            ext = "jpg"
        elif "png" in content_type:
            ext = "png"
        elif "webp" in content_type:
            ext = "webp"
        elif "gif" in content_type:
            ext = "gif"
        else:
            # Guess from URL
            url_lower = image_url.lower()
            if ".png" in url_lower:
                ext = "png"
            elif ".webp" in url_lower:
                ext = "webp"
            else:
                ext = "jpg"

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        url_hash = hashlib.md5(image_url.encode()).hexdigest()[:8]
        filename = f"{post_id}_{timestamp}_{url_hash}.{ext}"
        filepath = os.path.join(image_dir, filename)

        # Download with size limit (5MB)
        size = 0
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                size += len(chunk)
                if size > 5 * 1024 * 1024:
                    f.close()
                    os.remove(filepath)
                    return None
                f.write(chunk)

        return filepath

    except Exception:
        return None


def _is_valid_image_url(url):
    """Check if URL looks like an image."""
    if not url or len(url) < 10:
        return False
    # Reject data URIs and SVGs
    if url.startswith("data:") or url.endswith(".svg"):
        return False
    return True


def _make_absolute(url, base_url):
    """Convert relative URL to absolute."""
    if url.startswith("http"):
        return url
    if url.startswith("//"):
        return "https:" + url
    from urllib.parse import urljoin
    return urljoin(base_url, url)
