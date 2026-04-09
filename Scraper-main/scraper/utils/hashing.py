import hashlib

def hash_url(url: str) -> str:
    """Generate MD5 hash of a URL."""
    return hashlib.md5(url.encode('utf-8')).hexdigest()

def hash_content(content: str) -> str:
    """Generate SHA-256 hash of HTML content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()
