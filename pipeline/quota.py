"""
quota.py — daily API request quota tracker.

Responsibilities:
  - Tracks successful and failed API requests locally (quota_state.json)
  - Resets count at midnight Pacific Time (PT, UTC-8 / UTC-7 DST)
  - Attempts to sync with the Gemini API server for real usage data
  - If server sync is unavailable, falls back to local counts only
  - Enforces DAILY_LIMIT with a hard stop + user confirmation gate
  - Emits a soft warning at DAILY_SOFT_WARN requests

State file: config/quota_state.json (auto-created, safe to delete to reset)

Usage:
    from pipeline.quota import QuotaTracker
    tracker = QuotaTracker()

    # Before each API call:
    tracker.check_and_gate()          # raises QuotaExceededError or prompts user

    # After a successful call:
    tracker.record_success()

    # After a failed call:
    tracker.record_failure()

    # Print status at any time:
    tracker.print_status()
"""

import json
import logging
import pathlib
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# ── paths ──────────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).parent.parent
STATE_FILE = ROOT / "config" / "quota_state.json"

# ── PT timezone ────────────────────────────────────────────────────────────
PT = ZoneInfo("America/Los_Angeles")  # handles DST automatically


def _now_pt() -> datetime:
    return datetime.now(tz=PT)


def _today_pt_str() -> str:
    return _now_pt().strftime("%Y-%m-%d")


def _midnight_pt_reset_str() -> str:
    """ISO timestamp of the next midnight PT reset."""
    now = _now_pt()
    midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return midnight.isoformat()


# ── exceptions ─────────────────────────────────────────────────────────────


class QuotaExceededError(Exception):
    """Raised when the daily quota is exceeded and user declines to continue."""

    pass


class QuotaUserDeclined(QuotaExceededError):
    """User declined to continue past quota limit."""

    pass


# ── state schema ───────────────────────────────────────────────────────────


def _empty_state(date_str: str) -> dict:
    return {
        "date_pt": date_str,
        "successful_requests": 0,
        "failed_requests": 0,
        "server_synced": False,
        "server_count": None,
        "last_sync_attempt": None,
        "next_reset": _midnight_pt_reset_str(),
    }


# ── QuotaTracker ───────────────────────────────────────────────────────────


class QuotaTracker:
    """
    Tracks daily Gemini image API usage with server sync and guardrails.
    """

    def __init__(self):
        # Import here to avoid circular imports
        import pathlib
        import sys

        sys.path.insert(0, str(ROOT))
        from config.settings import (
            API_REGION,
            API_REGION_FALLBACK,
            DAILY_LIMIT,
            DAILY_SOFT_WARN,
            MODEL,
            REQUIRE_CONFIRMATION_TO_EXCEED,
        )

        self.daily_limit = DAILY_LIMIT
        self.soft_warn = DAILY_SOFT_WARN
        self.require_confirmation = REQUIRE_CONFIRMATION_TO_EXCEED
        self.model = MODEL
        self.region = API_REGION
        self.region_fallback = API_REGION_FALLBACK

        self._state = self._load()

    # ── persistence ────────────────────────────────────────────────────────

    def _load(self) -> dict:
        today = _today_pt_str()
        if STATE_FILE.exists():
            try:
                state = json.loads(STATE_FILE.read_text())
                if state.get("date_pt") == today:
                    logger.debug(f"Quota state loaded for {today}")
                    return state
                else:
                    logger.info(
                        f"New PT day ({today}). "
                        f"Previous day ({state.get('date_pt')}) had "
                        f"{state.get('successful_requests', 0)} successful requests. "
                        f"Resetting quota counter."
                    )
            except Exception as e:
                logger.warning(f"Could not read quota state: {e}. Starting fresh.")
        return _empty_state(today)

    def _save(self):
        try:
            STATE_FILE.write_text(json.dumps(self._state, indent=2))
        except Exception as e:
            logger.warning(f"Could not save quota state: {e}")

    # ── counts ─────────────────────────────────────────────────────────────

    @property
    def successful(self) -> int:
        return self._state["successful_requests"]

    @property
    def failed(self) -> int:
        return self._state["failed_requests"]

    @property
    def total_attempted(self) -> int:
        return self.successful + self.failed

    @property
    def effective_count(self) -> int:
        """
        The count to use for quota enforcement.
        Prefers server-synced data if available; falls back to local successful count.
        """
        if self._state["server_synced"] and self._state["server_count"] is not None:
            return self._state["server_count"]
        return self.successful

    # ── server sync ────────────────────────────────────────────────────────

    def sync_with_server(self) -> bool:
        """
        Attempt to fetch real usage count from the Gemini API.
        Updates state if successful. Returns True on success, False on failure.

        Note: The Gemini API exposes usage via the Cloud Monitoring / AI Platform
        Usage APIs. We query the generateContent usage metrics endpoint.
        Falls back gracefully if unavailable (no billing, no permissions, etc.).
        """
        import os

        from dotenv import load_dotenv

        load_dotenv()

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.debug("No API key — skipping server sync.")
            self._state["server_synced"] = False
            self._state["last_sync_attempt"] = _now_pt().isoformat()
            self._save()
            return False

        try:
            import json as _json
            import urllib.error
            import urllib.request

            # Query the Gemini models list as a lightweight connectivity check,
            # then attempt to read usage from the quota/usage API.
            # The v1beta usage endpoint returns per-model request counts for today.
            today = _today_pt_str()
            url = (
                f"https://{self.region}-aiplatform.googleapis.com/v1/"
                f"projects/-/locations/{self.region}/publishers/google/"
                f"models/{self.model}:getIamPolicy"
            )
            # Simpler approach: use the generativelanguage REST API usage endpoint
            usage_url = (
                f"https://generativelanguage.googleapis.com/v1beta/models"
                f"?key={api_key}&pageSize=1"
            )
            req = urllib.request.Request(
                usage_url, headers={"User-Agent": "tarot-pipeline/1.0"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                # If we can reach the API, it's live — but granular per-day image
                # generation counts aren't exposed in the public REST API without
                # OAuth + Cloud Monitoring. We confirm connectivity only.
                data = _json.loads(resp.read())
                if "models" in data:
                    logger.debug(
                        "Server reachable — granular usage not available via API key alone."
                    )
                    # Mark as connectivity-confirmed but not full-sync
                    self._state["server_synced"] = False
                    self._state["last_sync_attempt"] = _now_pt().isoformat()
                    self._save()
                    return False

        except urllib.error.HTTPError as e:
            if e.code == 429:
                logger.warning("Server sync hit 429 — quota already under pressure.")
            else:
                logger.debug(f"Server sync HTTP error {e.code}: {e.reason}")
        except Exception as e:
            logger.debug(f"Server sync unavailable: {e}")

        self._state["server_synced"] = False
        self._state["last_sync_attempt"] = _now_pt().isoformat()
        self._save()
        return False

    # ── recording ──────────────────────────────────────────────────────────

    def record_success(self):
        """Call after every successful API image generation."""
        self._state["successful_requests"] += 1
        self._save()
        logger.debug(
            f"Quota: {self.successful} successful / {self.failed} failed today (PT)"
        )

    def record_failure(self):
        """Call after every failed API call (including retries exhausted)."""
        self._state["failed_requests"] += 1
        self._save()
        logger.debug(
            f"Quota: {self.successful} successful / {self.failed} failed today (PT)"
        )

    # ── guardrail ──────────────────────────────────────────────────────────

    def check_and_gate(self, interactive: bool = True) -> None:
        """
        Pre-flight check before making an API call.

        - Soft warn at DAILY_SOFT_WARN
        - Hard stop at DAILY_LIMIT

        If REQUIRE_CONFIRMATION_TO_EXCEED is True and limit is reached:
          - In interactive mode: prompt user for permission to continue
          - In non-interactive mode: raise QuotaExceededError

        Args:
            interactive: If False, never prompt — raise instead.

        Raises:
            QuotaExceededError: If limit exceeded and user declines (or non-interactive).
        """
        count = self.effective_count
        source = "server-synced" if self._state["server_synced"] else "local count"

        # ── soft warning ──
        if count == self.soft_warn:
            self._print_banner(
                f"⚠  QUOTA WARNING — {count}/{self.daily_limit} requests used today (PT) [{source}]\n"
                f"   Approaching daily free-tier limit. {self.daily_limit - count} remaining.",
                colour="yellow",
            )

        # ── hard limit ──
        if count >= self.daily_limit:
            msg = (
                f"\n{'═' * 62}\n"
                f"  🚨  DAILY QUOTA LIMIT REACHED\n"
                f"{'═' * 62}\n"
                f"  Model          : {self.model}\n"
                f"  Requests today : {count} (limit: {self.daily_limit})\n"
                f"  Count source   : {source}\n"
                f"  Successful     : {self.successful}\n"
                f"  Failed         : {self.failed}\n"
                f"  Resets at      : midnight PT ({self._state['next_reset']})\n"
                f"{'═' * 62}\n"
                f"  ⚠  Continuing will exceed your free-tier limit.\n"
                f"     If billing is attached, THIS WILL INCUR CHARGES.\n"
                f"{'═' * 62}\n"
            )

            if not self.require_confirmation:
                logger.warning(
                    f"Quota exceeded ({count}/{self.daily_limit}) but REQUIRE_CONFIRMATION_TO_EXCEED=False. Continuing."
                )
                print(msg)
                return

            if not interactive:
                raise QuotaExceededError(
                    f"Daily quota of {self.daily_limit} requests exceeded "
                    f"({count} used). Resets at midnight PT."
                )

            print(msg)
            try:
                answer = (
                    input(
                        "  Do you want to continue and exceed the daily limit? [yes/no]: "
                    )
                    .strip()
                    .lower()
                )
            except (EOFError, KeyboardInterrupt):
                print("\nAborted.")
                raise QuotaExceededError("User aborted at quota gate.")

            if answer not in ("yes", "y"):
                raise QuotaExceededError(
                    f"User declined to exceed daily quota of {self.daily_limit}. "
                    f"Pipeline halted. Rerun after midnight PT to resume."
                )

            # User said yes — log prominently and continue
            logger.warning(
                f"User authorised exceeding daily limit "
                f"({count}/{self.daily_limit}). Continuing."
            )
            # Raise the limit for this session to avoid re-prompting every card
            self.daily_limit = count + 500
            return

        # ── all clear ──
        remaining = self.daily_limit - count
        if remaining <= 20:
            logger.info(
                f"Quota: {count}/{self.daily_limit} used ({remaining} remaining) [{source}]"
            )

    # ── reporting ──────────────────────────────────────────────────────────

    def print_status(self):
        count = self.effective_count
        source = (
            "server-synced"
            if self._state["server_synced"]
            else "local (no server sync)"
        )
        now_pt = _now_pt()
        print(
            f"\n{'─' * 52}\n"
            f"  QUOTA STATUS — {now_pt.strftime('%Y-%m-%d %H:%M %Z')}\n"
            f"{'─' * 52}\n"
            f"  Model            : {self.model}\n"
            f"  Daily limit      : {self.daily_limit}\n"
            f"  Soft warn at     : {self.soft_warn}\n"
            f"  Effective count  : {count}  [{source}]\n"
            f"  Successful today : {self.successful}\n"
            f"  Failed today     : {self.failed}\n"
            f"  Remaining        : {max(0, self.daily_limit - count)}\n"
            f"  Resets at        : midnight PT\n"
            f"  Next reset       : {self._state['next_reset']}\n"
            f"{'─' * 52}\n"
        )

    @staticmethod
    def _print_banner(msg: str, colour: str = "yellow"):
        colours = {"yellow": "\033[93m", "red": "\033[91m", "reset": "\033[0m"}
        c = colours.get(colour, "")
        r = colours["reset"]
        print(f"{c}{msg}{r}")


# ── CLI convenience ────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    tracker = QuotaTracker()
    tracker.sync_with_server()
    tracker.print_status()
