import logging
import sys
import os

def setup_logger(name: str) -> logging.Logger:
    """Enterprise-grade structured logging for high-performance scraping."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Configure format
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(message)s'
    )
    
    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    # Optional: Log to file for big operations
    os.makedirs("data/logs", exist_ok=True)
    fh = logging.FileHandler("data/logs/scraper_engine.log")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    return logger
