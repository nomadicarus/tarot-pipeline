"""
quota.py — daily API request quota tracker with three-mode guardrail.

GUARDRAIL MODES (set in config/settings.py or via CLI --guardrail):

  "preflight"  Pre-run check calculates total jobs vs remaining quota.
               Fits: run proceeds uninterrupted.
               Exceeds: informs user of exact overrun count, asks ONCE upfront,
               then runs to the limit and halts cleanly.
               Safe to leave running remotely once preflight clears.

  "realtime"   No preflight. Runs until quota hit mid-run, then pauses and asks.
               NOT safe for remote unattended runs.

  "off"        No checks or prompts. Runs to completion regardless.

State file: config/quota_state.json  (auto-created; delete to reset)
Timezone:   America/Los_Angeles (PT — handles DST automatically)
"""

import json
import logging
import pathlib
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ROOT       = pathlib.Path(__file__).parent.parent
STATE_FILE = ROOT / "config" / "quota_state.json"
PT         = ZoneInfo("America/Los_Angeles")

VALID_MODES = ("preflight", "realtime", "off")


# ── helpers ────────────────────────────────────────────────────────────────

def _now_pt() -> datetime:
    return datetime.now(tz=PT)

def _today_pt() -> str:
    return _now_pt().strftime("%Y-%m-%d")

def _next_midnight_pt() -> str:
    now = _now_pt()
    midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return midnight.isoformat()

def _empty_state(date: str) -> dict:
    return {
        "date_pt":             date,
        "successful_requests": 0,
        "failed_requests":     0,
        "estimated_cost_usd":  0.0,
        "server_synced":       False,
        "server_count":        None,
        "last_sync_attempt":   None,
        "next_reset":          _next_midnight_pt(),
    }


# ── exceptions ─────────────────────────────────────────────────────────────

class QuotaExceededError(Exception):
    """Raised when quota is exceeded and pipeline should halt."""
    pass

class QuotaUserDeclined(QuotaExceededError):
    """User explicitly declined to continue past quota limit."""
    pass


# ── QuotaTracker ───────────────────────────────────────────────────────────

class QuotaTracker:

    def __init__(self, guardrail_mode: Optional[str] = None):
        sys.path.insert(0, str(ROOT))
        from config.settings import (
            MODEL, DAILY_LIMIT, DAILY_SOFT_WARN,
            API_REGION, API_REGION_FALLBACK,
            GUARDRAIL_MODE, COST_PER_IMAGE_USD, COST_WARN_USD,
        )
        self.model           = MODEL
        self.daily_limit     = DAILY_LIMIT
        self.soft_warn       = DAILY_SOFT_WARN
        self.region          = API_REGION
        self.region_fallback = API_REGION_FALLBACK
        self.cost_per_image  = COST_PER_IMAGE_USD
        self.cost_warn       = COST_WARN_USD

        mode = (guardrail_mode or GUARDRAIL_MODE).lower()
        if mode not in VALID_MODES:
            raise ValueError(
                f"Invalid guardrail mode '{mode}'. Choose from: {VALID_MODES}"
            )
        self.guardrail_mode = mode

        self._state = self._load()
        self._user_approved_overrun = False

    # ── persistence ────────────────────────────────────────────────────────

    def _load(self) -> dict:
        today = _today_pt()
        if STATE_FILE.exists():
            try:
                state = json.loads(STATE_FILE.read_text())
                if state.get("date_pt") == today:
                    logger.debug(f"Quota state loaded for {today}")
                    return state
                else:
                    logger.info(
                        f"New PT day ({today}). Previous day "
                        f"({state.get('date_pt')}) used "
                        f"{state.get('successful_requests', 0)} requests "
                        f"(est. ${state.get('estimated_cost_usd', 0.0):.2f}). "
                        f"Resetting."
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
    def estimated_cost(self) -> float:
        return self._state.get("estimated_cost_usd", 0.0)

    @property
    def effective_count(self) -> int:
        """Server-synced count if available, else local successful count."""
        if self._state["server_synced"] and self._state["server_count"] is not None:
            return self._state["server_count"]
        return self.successful

    @property
    def remaining(self) -> int:
        return max(0, self.daily_limit - self.effective_count)

    # ── server sync ────────────────────────────────────────────────────────

    def sync_with_server(self) -> bool:
        """
        Attempt to confirm API connectivity.
        Granular per-day image counts require OAuth + Cloud Monitoring
        (not available via API key alone). Falls back to local counts.
        """
        import os
        from dotenv import load_dotenv
        load_dotenv()

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.debug("No API key — skipping server sync.")
            self._finalize_sync(False, "no API key")
            return False

        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models"
                f"?key={api_key}&pageSize=1"
            )
            req = urllib.request.Request(
                url, headers={"User-Agent": "tarot-pipeline/1.0"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
                if "models" in data:
                    logger.debug(
                        "API reachable. Granular usage requires OAuth + "
                        "Cloud Monitoring. Using local count."
                    )
                    self._finalize_sync(False, "API reachable, granular usage unavailable")
                    return False
        except urllib.error.HTTPError as e:
            if e.code == 429:
                logger.warning("Server sync hit 429 — quota already under pressure.")
                self._finalize_sync(False, "429 during sync")
            else:
                self._finalize_sync(False, f"HTTP {e.code}")
        except Exception as e:
            self._finalize_sync(False, str(e)[:80])

        return False

    def _finalize_sync(self, success: bool, note: str = ""):
        self._state["server_synced"]     = success
        self._state["last_sync_attempt"] = _now_pt().isoformat()
        if note:
            self._state["sync_note"] = note
        self._save()

    # ── recording ──────────────────────────────────────────────────────────

    def record_success(self):
        """Call after every successful API image generation."""
        self._state["successful_requests"] += 1
        self._state["estimated_cost_usd"] = round(
            self.successful * self.cost_per_image, 4
        )
        self._save()

        if self.cost_warn > 0 and self.estimated_cost >= self.cost_warn:
            logger.warning(
                f"Cost warning: est. spend today ${self.estimated_cost:.2f} "
                f"(threshold: ${self.cost_warn:.2f})"
            )
        logger.debug(
            f"Quota: {self.successful} ok / {self.failed} failed  "
            f"est. ${self.estimated_cost:.2f}  ({self.remaining} remaining)"
        )

    def record_failure(self):
        """Call after every failed API call (retries exhausted)."""
        self._state["failed_requests"] += 1
        self._save()
        logger.debug(
            f"Quota: {self.successful} ok / {self.failed} failed today (PT)"
        )

    # ── preflight check ────────────────────────────────────────────────────

    def preflight(self, total_jobs: int) -> None:
        """
        Pre-run quota check (preflight mode only).
        Called once before the pipeline loop with the total planned API calls.

        Raises:
            QuotaUserDeclined: if user declines to proceed.
        """
        if self.guardrail_mode in ("off", "realtime"):
            return

        used      = self.effective_count
        remaining = self.remaining
        source    = "server-synced" if self._state["server_synced"] else "local count"
        est_cost  = total_jobs * self.cost_per_image

        if total_jobs <= remaining:
            print(
                f"\n  ✓ Preflight OK — {total_jobs} jobs  "
                f"({remaining} quota remaining, est. ${est_cost:.2f})  [{source}]\n"
            )
            return

        overrun = total_jobs - remaining
        print(
            f"\n{'═' * 64}\n"
            f"  ⚠  PREFLIGHT: RUN WOULD EXCEED DAILY LIMIT\n"
            f"{'═' * 64}\n"
            f"  Model              : {self.model}\n"
            f"  Jobs this run      : {total_jobs}  (est. ${est_cost:.2f})\n"
            f"  Quota used today   : {used}/{self.daily_limit}  [{source}]\n"
            f"  Remaining today    : {remaining}\n"
            f"  Will complete      : {remaining} cards today\n"
            f"  Overrun            : {overrun} calls beyond free-tier limit\n"
            f"  Resets at          : {self._state['next_reset']}\n"
            f"{'═' * 64}\n"
        )

        try:
            answer = input(
                f"  Proceed? Will run {remaining} cards then halt. [yes/no]: "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise QuotaUserDeclined("Preflight aborted by user.")

        if answer not in ("yes", "y"):
            raise QuotaUserDeclined(
                f"User declined at preflight. "
                f"Rerun after midnight PT for remaining {overrun} cards."
            )

        self._user_approved_overrun = True
        print(f"\n  Proceeding. Will halt after {remaining} cards.\n")

    # ── per-call gate ──────────────────────────────────────────────────────

    def check_and_gate(self) -> None:
        """
        Per-call quota check. Behaviour depends on guardrail_mode.

        "off"       — always passes.
        "preflight" — halts cleanly at limit (user was informed at preflight).
        "realtime"  — prompts user when limit is hit, once per session.

        Raises:
            QuotaExceededError:  limit hit in preflight mode.
            QuotaUserDeclined:   user declined in realtime mode.
        """
        if self.guardrail_mode == "off":
            return

        count  = self.effective_count
        source = "server-synced" if self._state["server_synced"] else "local count"

        # Soft warning
        if count == self.soft_warn:
            print(
                f"\n  \033[93m⚠  Quota soft warning: "
                f"{count}/{self.daily_limit} used today [{source}]\033[0m"
            )

        if count < self.daily_limit:
            return

        # Limit reached
        if self.guardrail_mode == "preflight":
            raise QuotaExceededError(
                f"Daily limit of {self.daily_limit} reached ({count} used). "
                f"Halting cleanly. Rerun after midnight PT."
            )

        # realtime mode
        if self._user_approved_overrun:
            return

        print(
            f"\n{'═' * 64}\n"
            f"  🚨  DAILY QUOTA LIMIT REACHED\n"
            f"{'═' * 64}\n"
            f"  Model            : {self.model}\n"
            f"  Requests today   : {count}/{self.daily_limit}  [{source}]\n"
            f"  Estimated cost   : ${self.estimated_cost:.2f}\n"
            f"  Successful       : {self.successful}\n"
            f"  Failed           : {self.failed}\n"
            f"  Resets at        : {self._state['next_reset']}\n"
            f"{'═' * 64}\n"
            f"  ⚠  Continuing will exceed free-tier limit.\n"
            f"     If billing is attached, THIS WILL INCUR CHARGES.\n"
            f"{'═' * 64}\n"
        )

        try:
            answer = input(
                "  Continue past limit? [yes/no]: "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise QuotaUserDeclined("Aborted at realtime quota gate.")

        if answer not in ("yes", "y"):
            raise QuotaUserDeclined(
                f"User declined. Rerun after midnight PT."
            )

        self._user_approved_overrun = True
        logger.warning(
            f"User authorised exceeding daily limit ({count}/{self.daily_limit})."
        )

    # ── status display ─────────────────────────────────────────────────────

    def print_status(self):
        count  = self.effective_count
        source = (
            "server-synced"
            if self._state["server_synced"]
            else "local (no server sync)"
        )
        note   = self._state.get("sync_note", "")
        now_pt = _now_pt()
        mode_note = {
            "preflight": "pre-run check, uninterrupted once cleared",
            "realtime":  "prompts at limit mid-run (not remote-safe)",
            "off":       "no checks — use with billing attached only",
        }.get(self.guardrail_mode, "")

        print(
            f"\n{'─' * 56}\n"
            f"  QUOTA STATUS — {now_pt.strftime('%Y-%m-%d %H:%M %Z')}\n"
            f"{'─' * 56}\n"
            f"  Model            : {self.model}\n"
            f"  Guardrail mode   : {self.guardrail_mode}  ({mode_note})\n"
            f"  Daily limit      : {self.daily_limit}\n"
            f"  Soft warn at     : {self.soft_warn}\n"
            f"  Effective count  : {count}  [{source}]\n"
            + (f"  Sync note        : {note}\n" if note else "")
            + f"  Successful today : {self.successful}\n"
            f"  Failed today     : {self.failed}\n"
            f"  Est. cost today  : ${self.estimated_cost:.2f}  "
            f"(@ ${self.cost_per_image}/img)\n"
            f"  Remaining        : {self.remaining}\n"
            f"  Resets at        : midnight PT ({self._state['next_reset']})\n"
            f"{'─' * 56}\n"
        )


# ── CLI convenience ────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    tracker = QuotaTracker()
    tracker.sync_with_server()
    tracker.print_status()
