"""
Vera AI Challenge — Configuration
Loads environment variables and provides global settings.
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()



# --- Team Metadata ---
TEAM_NAME: str = os.getenv("TEAM_NAME", "VeraEngine")
TEAM_MEMBERS: list[str] = json.loads(os.getenv("TEAM_MEMBERS", '["Prakash"]'))
CONTACT_EMAIL: str = os.getenv("CONTACT_EMAIL", "prakash@example.com")
BOT_VERSION: str = os.getenv("BOT_VERSION", "1.0.0")

# --- Engine Tuning ---
# Minimum seconds between sends to the same merchant
MERCHANT_COOLDOWN_SECONDS: int = int(os.getenv("MERCHANT_COOLDOWN_SECONDS", "3600"))
# Maximum actions per tick
MAX_ACTIONS_PER_TICK: int = int(os.getenv("MAX_ACTIONS_PER_TICK", "10"))
