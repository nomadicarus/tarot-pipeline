"""
╔══════════════════════════════════════════════════════════════════╗
║              TAROT PIPELINE — USER SETTINGS                      ║
║                                                                  ║
║  Edit this file to control model choice and daily spend limits.  ║
╚══════════════════════════════════════════════════════════════════╝

DAILY_LIMIT:  Max API image requests per day (PT timezone, resets midnight PT).
              Free tier = 500 requests/day. Set lower to stay within budget.
              Pipeline will HALT and ask permission before exceeding this.

MODEL:        Gemini image generation model to use.
              Options:
                "gemini-2.5-flash-preview-05-20"  ← recommended (500/day free)
                "gemini-3.1-flash-image-preview"  ← Nano Banana 2
                "gemini-3-pro-image-preview"       ← highest quality, lower quota

REQUIRE_CONFIRMATION_TO_EXCEED:
              If True (recommended), pipeline stops and asks before crossing
              DAILY_LIMIT. If False, pipeline runs uninterrupted (use with care
              if billing is attached — costs real money beyond free tier).

API_REGION:   Endpoint region. "us-central1" avoids region-locking issues.
              Fallback: "global" if regional endpoint unavailable.
"""

# ─────────────────────────────────────────────────────────────────
#  ★  PRIMARY USER SETTINGS — CHANGE THESE  ★
# ─────────────────────────────────────────────────────────────────

MODEL = "gemini-2.0-flash-preview-image-generation"
# MODEL = "gemini-3.1-flash-image-preview"
# MODEL = "gemini-3-pro-image-preview"

DAILY_LIMIT: int = 500  # requests per day (free tier ceiling)
DAILY_SOFT_WARN: int = 450  # warn at this count (90% of free tier)

REQUIRE_CONFIRMATION_TO_EXCEED: bool = True  # STRONGLY RECOMMENDED: True

API_REGION: str = "us-central1"  # regional endpoint
API_REGION_FALLBACK: str = "global"

# ─────────────────────────────────────────────────────────────────
#  Timing
# ─────────────────────────────────────────────────────────────────

QUOTA_TIMEZONE = "US/Pacific"  # PT — resets at midnight Pacific Time
# UTC-8 standard / UTC-7 daylight saving

# ─────────────────────────────────────────────────────────────────
#  Rate limiting (inter-request delay)
# ─────────────────────────────────────────────────────────────────

# Delay between API calls in seconds.
# Free tier (~3 RPM image): 20s is safe.
# Paid tier (~10 RPM image): 8s is safe.
API_CALL_DELAY: float = 20.0

# Retry settings
MAX_RETRIES: int = 2
RETRY_BASE_DELAY: float = 15.0  # exponential backoff base (seconds)
RATE_LIMIT_RETRY_DELAY: float = 60.0  # extra wait on 429 (× attempt number)
