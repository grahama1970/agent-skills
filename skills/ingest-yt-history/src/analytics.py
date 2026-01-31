#!/usr/bin/env python3
"""
Data science analytics for YouTube watch history.

Requires: pandas, matplotlib (optional for charts)

Provides insights for Horus persona understanding of human preferences.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pd = None


def load_to_dataframe(path: str | Path) -> "pd.DataFrame":
    """Load JSONL history into a pandas DataFrame.

    Returns DataFrame with columns:
    - video_id, title, ts, url, products
    - datetime (parsed timestamp)
    - hour, day_of_week, date
    - is_music (inferred from URL)
    """
    if not PANDAS_AVAILABLE:
        raise ImportError("pandas required. Install with: pip install pandas")

    path = Path(path)
    records = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    df = pd.DataFrame(records)

    # Parse timestamps
    if "ts" in df.columns:
        df["datetime"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
        df["date"] = df["datetime"].dt.date
        df["hour"] = df["datetime"].dt.hour
        df["day_of_week"] = df["datetime"].dt.day_name()
        df["week"] = df["datetime"].dt.isocalendar().week
        df["month"] = df["datetime"].dt.to_period("M")

    # Detect music content
    if "url" in df.columns:
        df["is_music"] = df["url"].str.contains("music.youtube.com", na=False)

    return df


def viewing_trends(df: "pd.DataFrame", window: int = 7) -> dict[str, Any]:
    """Compute viewing trends over time.

    Args:
        df: DataFrame from load_to_dataframe
        window: Rolling window size in days

    Returns:
        Dict with trend insights
    """
    if "date" not in df.columns:
        return {"error": "No date column"}

    # Daily counts
    daily = df.groupby("date").size()

    # Rolling average
    rolling = daily.rolling(window=window, min_periods=1).mean()

    # Recent vs historical
    recent_avg = daily.tail(window).mean() if len(daily) >= window else daily.mean()
    historical_avg = daily.mean()

    trend = "increasing" if recent_avg > historical_avg * 1.1 else \
            "decreasing" if recent_avg < historical_avg * 0.9 else "stable"

    return {
        "daily_average": round(historical_avg, 1),
        "recent_average": round(recent_avg, 1),
        "trend": trend,
        "trend_change_pct": round((recent_avg / historical_avg - 1) * 100, 1) if historical_avg > 0 else 0,
        "peak_day": str(daily.idxmax()) if len(daily) > 0 else None,
        "peak_count": int(daily.max()) if len(daily) > 0 else 0,
    }


def session_analysis(df: "pd.DataFrame", gap_minutes: int = 30) -> dict[str, Any]:
    """Detect viewing sessions and analyze patterns.

    A session is a sequence of videos with gaps < gap_minutes.

    Args:
        df: DataFrame from load_to_dataframe
        gap_minutes: Max gap between videos in same session

    Returns:
        Dict with session insights
    """
    if "datetime" not in df.columns or df["datetime"].isna().all():
        return {"error": "No valid timestamps"}

    # Sort by time
    df_sorted = df.sort_values("datetime").dropna(subset=["datetime"])

    if len(df_sorted) < 2:
        return {"total_sessions": 1, "avg_session_length": 1}

    # Calculate gaps between videos
    gaps = df_sorted["datetime"].diff()
    threshold = pd.Timedelta(minutes=gap_minutes)

    # Mark session starts
    session_starts = gaps > threshold
    session_starts.iloc[0] = True  # First video starts a session

    # Assign session IDs
    session_ids = session_starts.cumsum()

    # Session stats
    session_sizes = session_ids.value_counts()

    # Binge detection (sessions with 5+ videos)
    binge_sessions = (session_sizes >= 5).sum()

    return {
        "total_sessions": int(session_ids.max()),
        "avg_session_length": round(session_sizes.mean(), 1),
        "max_session_length": int(session_sizes.max()),
        "binge_sessions": int(binge_sessions),
        "binge_pct": round(binge_sessions / session_ids.max() * 100, 1) if session_ids.max() > 0 else 0,
    }


def time_patterns(df: "pd.DataFrame") -> dict[str, Any]:
    """Analyze viewing patterns by time of day.

    Returns:
        Dict with time-based insights
    """
    if "hour" not in df.columns:
        return {"error": "No hour column"}

    # Hour distribution
    hour_counts = df["hour"].value_counts().sort_index()

    # Peak hours
    peak_hour = int(hour_counts.idxmax()) if len(hour_counts) > 0 else None

    # Time periods
    def get_period(hour):
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"

    df_temp = df.copy()
    df_temp["period"] = df_temp["hour"].apply(get_period)
    period_counts = df_temp["period"].value_counts()

    # Music by time of day (if is_music column exists)
    music_by_hour = None
    if "is_music" in df.columns:
        music_df = df[df["is_music"]]
        if len(music_df) > 0:
            music_peak = int(music_df["hour"].value_counts().idxmax())
            music_by_hour = {
                "music_peak_hour": music_peak,
                "music_peak_period": get_period(music_peak),
            }

    result = {
        "peak_hour": peak_hour,
        "peak_period": get_period(peak_hour) if peak_hour is not None else None,
        "period_distribution": period_counts.to_dict(),
    }

    if music_by_hour:
        result.update(music_by_hour)

    return result


def content_evolution(df: "pd.DataFrame", periods: int = 4) -> dict[str, Any]:
    """Track how content preferences evolve over time.

    Divides history into time periods and compares.

    Args:
        df: DataFrame from load_to_dataframe
        periods: Number of time periods to divide history into

    Returns:
        Dict with evolution insights
    """
    if "datetime" not in df.columns:
        return {"error": "No datetime column"}

    df_sorted = df.sort_values("datetime").dropna(subset=["datetime"])
    if len(df_sorted) < periods * 10:  # Need enough data
        return {"error": "Not enough data for evolution analysis"}

    # Divide into periods
    period_size = len(df_sorted) // periods
    period_dfs = [df_sorted.iloc[i*period_size:(i+1)*period_size] for i in range(periods)]

    evolution = []
    for i, period_df in enumerate(period_dfs):
        period_info = {
            "period": i + 1,
            "start": str(period_df["datetime"].min().date()),
            "end": str(period_df["datetime"].max().date()),
            "count": len(period_df),
        }

        # Music ratio if available
        if "is_music" in period_df.columns:
            music_ratio = period_df["is_music"].mean()
            period_info["music_ratio"] = round(music_ratio * 100, 1)

        evolution.append(period_info)

    # Calculate trend
    if "is_music" in df.columns and len(evolution) >= 2:
        first_music = evolution[0].get("music_ratio", 0)
        last_music = evolution[-1].get("music_ratio", 0)
        music_trend = "increasing" if last_music > first_music + 5 else \
                     "decreasing" if last_music < first_music - 5 else "stable"
    else:
        music_trend = None

    return {
        "periods": evolution,
        "music_trend": music_trend,
    }


def generate_insights(df: "pd.DataFrame") -> dict[str, Any]:
    """Generate all insights for Horus persona.

    Returns comprehensive analysis suitable for persona integration.
    """
    return {
        "summary": {
            "total_videos": len(df),
            "date_range": {
                "start": str(df["datetime"].min().date()) if "datetime" in df.columns else None,
                "end": str(df["datetime"].max().date()) if "datetime" in df.columns else None,
            },
            "music_videos": int(df["is_music"].sum()) if "is_music" in df.columns else None,
        },
        "trends": viewing_trends(df),
        "sessions": session_analysis(df),
        "time_patterns": time_patterns(df),
        "evolution": content_evolution(df),
    }


def format_insights_for_horus(insights: dict[str, Any]) -> str:
    """Format insights as Horus-style narrative.

    Returns text suitable for persona voice.
    """
    lines = ["## Viewing Pattern Analysis\n"]

    # Summary
    summary = insights.get("summary", {})
    lines.append(f"**Observed**: {summary.get('total_videos', 0)} videos across the data range.")
    if summary.get("music_videos"):
        music_pct = summary["music_videos"] / summary["total_videos"] * 100
        lines.append(f"**Music content**: {music_pct:.1f}% of viewing.")
    lines.append("")

    # Trends
    trends = insights.get("trends", {})
    if trends.get("trend"):
        lines.append(f"**Viewing trend**: {trends['trend']} ({trends.get('trend_change_pct', 0):+.1f}% vs historical)")
    lines.append(f"**Daily average**: {trends.get('daily_average', 0)} videos")
    lines.append("")

    # Sessions
    sessions = insights.get("sessions", {})
    if sessions.get("binge_sessions"):
        lines.append(f"**Binge sessions detected**: {sessions['binge_sessions']} ({sessions.get('binge_pct', 0):.1f}% of sessions)")
    lines.append(f"**Average session**: {sessions.get('avg_session_length', 0)} videos")
    lines.append("")

    # Time patterns
    patterns = insights.get("time_patterns", {})
    if patterns.get("peak_period"):
        lines.append(f"**Peak viewing**: {patterns['peak_period']} (hour {patterns.get('peak_hour')})")
    if patterns.get("music_peak_period"):
        lines.append(f"**Music preference**: peaks during {patterns['music_peak_period']}")
    lines.append("")

    # Evolution
    evolution = insights.get("evolution", {})
    if evolution.get("music_trend"):
        lines.append(f"**Music consumption trend**: {evolution['music_trend']}")

    return "\n".join(lines)


def main() -> None:
    """CLI entry point for analytics."""
    import argparse

    parser = argparse.ArgumentParser(description="Data science analytics for YouTube history")
    parser.add_argument("input_path", help="Path to parsed history JSONL file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--horus", action="store_true", help="Format for Horus persona")

    args = parser.parse_args()

    if not PANDAS_AVAILABLE:
        print("Error: pandas required. Install with: pip install pandas", file=sys.stderr)
        sys.exit(1)

    try:
        df = load_to_dataframe(args.input_path)
        insights = generate_insights(df)

        if args.json:
            # Convert periods to strings for JSON serialization
            if "evolution" in insights and "periods" in insights["evolution"]:
                for p in insights["evolution"]["periods"]:
                    if "start" in p:
                        p["start"] = str(p["start"])
                    if "end" in p:
                        p["end"] = str(p["end"])
            print(json.dumps(insights, indent=2, default=str))
        elif args.horus:
            print(format_insights_for_horus(insights))
        else:
            print(format_insights_for_horus(insights))

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
