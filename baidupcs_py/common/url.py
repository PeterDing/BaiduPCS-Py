def is_magnet(url: str) -> bool:
    return url[:7].lower() == "magnet:"
