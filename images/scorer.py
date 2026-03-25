import os

try:
    from PIL import Image
except ImportError:
    Image = None


def score_image(image_path, image_source="unknown"):
    """Score an image for Twitter engagement potential. Returns dict with score and details."""
    if not image_path or not os.path.exists(image_path):
        return {"score": 0, "details": "No image file", "penalties": []}

    score = 0
    details = []

    # Base: image exists and is valid
    try:
        file_size = os.path.getsize(image_path)
    except OSError:
        return {"score": 0, "details": "Cannot read file", "penalties": []}

    if file_size < 1000:  # < 1KB = not a real image
        return {"score": 0, "details": "File too small (likely broken)", "penalties": ["tiny file"]}

    if file_size > 5 * 1024 * 1024:  # > 5MB = Twitter rejects
        return {"score": 0, "details": "File too large for Twitter (>5MB)", "penalties": ["over 5MB"]}

    score += 30
    details.append("Valid image (+30)")

    # Source quality bonus
    if image_source in ("article_og", "article_twitter"):
        score += 25
        details.append(f"Source: {image_source} (+25)")
    elif image_source in ("unsplash", "pexels"):
        score += 15
        details.append(f"Source: {image_source} (+15)")

    # File size bonuses
    if file_size < 1 * 1024 * 1024:  # < 1MB
        score += 5
        details.append("Under 1MB (+5)")
    if file_size > 50 * 1024:  # > 50KB (not a placeholder)
        score += 5
        details.append("Over 50KB (+5)")

    # Resolution and aspect ratio (requires Pillow)
    if Image:
        try:
            with Image.open(image_path) as img:
                width, height = img.size

                if width >= 800 and height >= 400:
                    score += 20
                    details.append(f"Resolution {width}x{height} >= 800x400 (+20)")

                    if width >= 1200 and height >= 628:
                        score += 10
                        details.append("Ideal Twitter size >= 1200x628 (+10)")

                if height > 0:
                    ratio = width / height
                    if 1.6 <= ratio <= 2.2:
                        score += 15
                        details.append(f"Landscape ratio {ratio:.1f} (+15)")
        except Exception:
            pass  # Can't read dimensions, skip these bonuses

    score = min(score, 100)
    return {
        "score": score,
        "details": ", ".join(details),
        "penalties": [],
    }
