"""Thin wrapper around the unofficial `garminconnect` library.

Handles login (including MFA), session token caching, and shaping the raw
Garmin Connect API responses into the fields the Phit backend needs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from garminconnect import Garmin
from garminconnect.exceptions import GarminConnectAuthenticationError

TOKEN_STORE = str(Path(os.environ.get("GARMIN_TOKEN_STORE", "~/.phit/garmin_tokens")).expanduser())

RUNNING_TYPE_PREFIXES = ("running", "track_running", "trail_running", "treadmill_running")


class GarminSession:
    """Holds the single logged-in Garmin client for this local app."""

    def __init__(self) -> None:
        self._client: Garmin | None = None
        self._pending_mfa_state: Any = None
        self.display_name: str | None = None

    @property
    def connected(self) -> bool:
        return self._client is not None

    def connect(self, email: str | None = None, password: str | None = None) -> dict[str, Any]:
        """Try to connect, first via cached tokens, then via credentials.

        Returns a dict describing the outcome:
          {"status": "connected", "display_name": ...}
          {"status": "mfa_required"}
          {"status": "error", "message": ...}
        """
        email = email or os.environ.get("GARMIN_EMAIL")
        password = password or os.environ.get("GARMIN_PASSWORD")

        client = Garmin(email=email, password=password, return_on_mfa=True)
        try:
            result = client.login(tokenstore=TOKEN_STORE)
        except GarminConnectAuthenticationError as exc:
            return {"status": "error", "message": str(exc)}
        except Exception as exc:  # noqa: BLE001 - surface any Garmin/network failure to the UI
            return {"status": "error", "message": str(exc)}

        needs_mfa, client_state = result
        if needs_mfa:
            self._pending_mfa_state = client_state
            self._client = client
            return {"status": "mfa_required"}

        self._client = client
        self.display_name = getattr(client, "display_name", None)
        Path(TOKEN_STORE).parent.mkdir(parents=True, exist_ok=True)
        return {"status": "connected", "display_name": self.display_name}

    def submit_mfa(self, code: str) -> dict[str, Any]:
        if self._client is None or self._pending_mfa_state is None:
            return {"status": "error", "message": "No pending MFA login"}
        try:
            self._client.resume_login(self._pending_mfa_state, code)
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "message": str(exc)}

        self._pending_mfa_state = None
        self.display_name = getattr(self._client, "display_name", None)
        Path(TOKEN_STORE).parent.mkdir(parents=True, exist_ok=True)
        try:
            self._client.client.dump(TOKEN_STORE)
        except Exception:  # noqa: BLE001 - token persistence is best-effort
            pass
        return {"status": "connected", "display_name": self.display_name}

    def require_client(self) -> Garmin:
        if self._client is None:
            raise RuntimeError("Not connected to Garmin. Call /api/connect first.")
        return self._client


def _is_running(activity: dict[str, Any]) -> bool:
    type_key = ((activity.get("activityType") or {}).get("typeKey") or "").lower()
    return type_key in RUNNING_TYPE_PREFIXES


def _pace_per_km(distance_m: float | None, duration_s: float | None) -> float | None:
    if not distance_m or not duration_s:
        return None
    km = distance_m / 1000.0
    if km <= 0:
        return None
    return (duration_s / 60.0) / km


def format_pace(pace_min_per_km: float | None) -> str:
    if pace_min_per_km is None:
        return "--"
    minutes = int(pace_min_per_km)
    seconds = round((pace_min_per_km - minutes) * 60)
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}/km"


def summarize_activity(activity: dict[str, Any]) -> dict[str, Any]:
    distance_m = activity.get("distance")
    duration_s = activity.get("duration")
    pace = _pace_per_km(distance_m, duration_s)
    return {
        "id": activity.get("activityId"),
        "name": activity.get("activityName"),
        "date": activity.get("startTimeLocal"),
        "type": ((activity.get("activityType") or {}).get("typeKey")),
        "distance_km": round(distance_m / 1000.0, 2) if distance_m else None,
        "duration_s": duration_s,
        "pace_min_per_km": round(pace, 3) if pace is not None else None,
        "pace_display": format_pace(pace),
        "avg_hr": activity.get("averageHR"),
        "max_hr": activity.get("maxHR"),
        "avg_cadence": activity.get("averageRunningCadenceInStepsPerMinute"),
        "elevation_gain_m": activity.get("elevationGain"),
        "calories": activity.get("calories"),
    }


def list_recent_runs(session: GarminSession, limit: int = 20) -> list[dict[str, Any]]:
    client = session.require_client()
    activities = client.get_activities(0, max(limit * 3, limit), None)
    runs = [a for a in activities if _is_running(a)][:limit]
    return [summarize_activity(a) for a in runs]


def get_run_detail(session: GarminSession, activity_id: str) -> dict[str, Any]:
    client = session.require_client()
    activity = client.get_activity(activity_id)
    summary = summarize_activity(activity)

    splits_raw = client.get_activity_splits(activity_id)
    laps = []
    for lap in splits_raw.get("lapDTOs", []):
        lap_distance = lap.get("distance")
        lap_duration = lap.get("duration")
        lap_pace = _pace_per_km(lap_distance, lap_duration)
        laps.append(
            {
                "distance_km": round(lap_distance / 1000.0, 2) if lap_distance else None,
                "duration_s": lap_duration,
                "pace_display": format_pace(lap_pace),
                "avg_hr": lap.get("averageHR"),
                "max_hr": lap.get("maxHR"),
                "avg_cadence": lap.get("averageRunningCadenceInStepsPerMinute"),
                "elevation_gain_m": lap.get("elevationGain"),
            }
        )
    summary["laps"] = laps
    return summary


def _delta(a: float | None, b: float | None) -> dict[str, Any] | None:
    if a is None or b is None:
        return None
    diff = b - a
    pct = (diff / a * 100.0) if a else None
    return {"diff": round(diff, 3), "pct": round(pct, 1) if pct is not None else None}


def compare_runs(session: GarminSession, id_a: str, id_b: str) -> dict[str, Any]:
    run_a = get_run_detail(session, id_a)
    run_b = get_run_detail(session, id_b)

    metrics = ["distance_km", "duration_s", "pace_min_per_km", "avg_hr", "max_hr", "avg_cadence", "elevation_gain_m", "calories"]
    deltas = {metric: _delta(run_a.get(metric), run_b.get(metric)) for metric in metrics}

    return {"run_a": run_a, "run_b": run_b, "deltas": deltas}
