"""
╔══════════════════════════════════════════════════════════════════════╗
║              TAROT PIPELINE — USER SETTINGS                          ║
║  Edit this file to control model, quota limits, guardrail & costs.  ║
╚══════════════════════════════════════════════════════════════════════╝

GUARDRAIL_MODE controls how quota limits are enforced:

  "preflight"  — (DEFAULT, RECOMMENDED)
                 Calculates total jobs BEFORE starting any API calls.
                 • Run fits within quota  → executes completely uninterrupted.
                 • Run would exceed quota → tells you the overrun count,
                   asks ONCE, then runs to the limit and halts cleanly.
                 ✓ Safe to leave running remotely once preflight clears.

  "realtime"   — No preflight calculation. Runs freely until quota is hit.
                 At the limit: pauses mid-run, shows overrun estimate, asks to continue.
                 ✗ NOT safe to leave running remotely — will pause and wait for input.

  "off"        — No checks, no prompts. Runs to completion regardless of quota.
                 ✗ Will exceed free tier on large runs. Only use with billing attached.

CLI override:  python main.py --guardrail preflight|realtime|off
               (overrides this file for that run only)
"""

# ─────────────────────────────────────────────────────────────────
#  ★  MODEL SELECTION — uncomment the model you want to use  ★
# ─────────────────────────────────────────────────────────────────
#
#  Model                               RPD   RPM    TPM       $/img(1K)  $/img(2K est.)
#  gemini-3.1-flash-image-preview      500   100    200,000   $0.067     $0.08–0.12
#  gemini-2.0-flash-preview-image-gen  500   10     1,000,000 $0.039     $0.04–0.08
#  gemini-2.5-flash-preview-05-20      500   500*   500,000   $0.039     $0.04–0.08
#
#  * RPM limits may vary — verify at aistudio.google.com/quota
#  Batch/optimised routes: ~$0.019–$0.02 per image (2.5 Flash)
# ─────────────────────────────────────────────────────────────────

MODEL: str = "gemini-3.1-flash-image-preview"
# MODEL: str = "gemini-2.0-flash-preview-image-generation"
# MODEL: str = "gemini-2.5-flash-preview-05-20"

# ─────────────────────────────────────────────────────────────────
#  ★  QUOTA & GUARDRAIL  ★
# ─────────────────────────────────────────────────────────────────

DAILY_LIMIT: int     = 500    # max requests per day (free tier ceiling)
DAILY_SOFT_WARN: int = 450    # warn at this count (90% of free tier)

GUARDRAIL_MODE: str  = "preflight"   # "preflight" | "realtime" | "off"

# ─────────────────────────────────────────────────────────────────
#  ★  COST TRACKING  ★
#  Set per-image cost for your active model (conservative 2K estimate).
#  Set to 0.0 to disable cost tracking.
# ─────────────────────────────────────────────────────────────────

COST_PER_IMAGE_USD: float = 0.10   # gemini-3.1-flash-image-preview @ ~2K
# COST_PER_IMAGE_USD: float = 0.06  # gemini-2.5-flash estimate
# COST_PER_IMAGE_USD: float = 0.0   # disable cost tracking

COST_WARN_USD: float = 5.00        # warn when estimated run cost exceeds this

# ─────────────────────────────────────────────────────────────────
#  ★  RATE LIMITING  ★
#  RPM_LIMIT: requests per minute for the active model (see table above).
#  API_CALL_DELAY: auto-derived from RPM. Override manually if needed.
# ─────────────────────────────────────────────────────────────────

RPM_LIMIT: int        = 100          # gemini-3.1-flash: 100 RPM
TPM_LIMIT: int        = 200_000      # gemini-3.1-flash: 200k TPM

# Minimum safe delay derived from RPM. Increase if you hit 429s.
API_CALL_DELAY: float = max(60.0 / RPM_LIMIT, 1.0)

# ─────────────────────────────────────────────────────────────────
#  ★  ENDPOINT  ★
# ─────────────────────────────────────────────────────────────────

API_REGION: str          = "us-central1"   # avoids region-locking
API_REGION_FALLBACK: str = "global"

QUOTA_TIMEZONE: str      = "America/Los_Angeles"   # PT, handles DST

# ─────────────────────────────────────────────────────────────────
#  ★  RETRY  ★
# ─────────────────────────────────────────────────────────────────

MAX_RETRIES: int              = 2
RETRY_BASE_DELAY: float       = 15.0
RATE_LIMIT_RETRY_DELAY: float = 60.0   # seconds × attempt number on 429
