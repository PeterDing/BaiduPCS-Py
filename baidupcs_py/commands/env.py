from pathlib import Path

# Local data directory
DATA_DIR = Path("~") / ".baidupcs-py"

# Account data path
ACCOUNT_DATA_PATH = DATA_DIR / "accounts.pk"

# Logging path
LOG_PATH = DATA_DIR / "running.log"

# Logging level
LOG_LEVEL = "CRITICAL"
