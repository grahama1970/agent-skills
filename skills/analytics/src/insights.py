#!/usr/bin/env python3
"""
Core analytics functions for timestamped content data.

Works with any JSONL/CSV/JSON data. Auto-detects schema and recommends visualizations.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd


# Chart recommendation rules based on data types
CHART_RECOMMENDATIONS = {
    # (x_type, y_type) -> recommended charts
    ("categorical", "count"): ["bar", "pie"],
    ("categorical", "numerical"): ["bar", "hbar"],
    ("temporal", "count"): ["line", "area"],
    ("temporal", "numerical"): ["line", "area"],
    ("numerical", "numerical"): ["scatter", "line"],
    ("categorical", "categorical"): ["heatmap"],
    ("temporal", "categorical"): ["heatmap"],
}

# create-figure command mapping
CREATE_FIGURE_COMMANDS = {
    "bar": "metrics --type bar",
    "hbar": "metrics --type hbar",
    "pie": "metrics --type pie",
    "line": "training-curves",
    "area": "training-curves",
    "scatter": "parallel-coords",
    "heatmap": "heatmap",
}


def load_data(path: str | Path) -> pd.DataFrame:
    """Load data from JSONL, JSON, or CSV file.

    Auto-detects format from extension and handles common patterns.
    """
    path = Path(path)

    if path.suffix == ".csv":
        df = pd.read_csv(path)
    elif path.suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            # Try common patterns: {"data": [...]} or {"items": [...]}
            for key in ["data", "items", "records", "results"]:
                if key in data and isinstance(data[key], list):
                    df = pd.DataFrame(data[key])
                    break
            else:
                df = pd.DataFrame([data])
        else:
            df = pd.DataFrame()
    else:
        # Default to JSONL
        df = load_jsonl(path)

    return _enrich_dataframe(df)


def _enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived columns for temporal data."""
    if df.empty:
        return df

    # Auto-detect timestamp column
    ts_columns = ["ts", "timestamp", "time", "datetime", "date", "watched_at", "created_at", "created", "updated"]
    ts_col = None
    for col in ts_columns:
        if col in df.columns:
            ts_col = col
            break

    if ts_col:
        df["datetime"] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
        if not df["datetime"].isna().all():
            df["date"] = df["datetime"].dt.date
            df["hour"] = df["datetime"].dt.hour
            df["day_of_week"] = df["datetime"].dt.day_name()
            df["week"] = df["datetime"].dt.isocalendar().week
            df["month"] = df["datetime"].dt.to_period("M")

    return df


def describe_schema(df: pd.DataFrame) -> dict[str, Any]:
    """Discover schema and recommend visualizations.

    Returns column types, statistics, and chart recommendations.
    """
    if df.empty:
        return {"error": "Empty dataframe"}

    schema = {
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "columns": {},
        "recommendations": [],
    }

    for col in df.columns:
        col_info = _analyze_column(df[col], col)
        schema["columns"][col] = col_info

    # Generate chart recommendations
    schema["recommendations"] = _generate_recommendations(df, schema["columns"])

    return schema


def _analyze_column(series: pd.Series, name: str) -> dict[str, Any]:
    """Analyze a single column to determine type and stats."""
    info: dict[str, Any] = {
        "dtype": str(series.dtype),
        "null_count": int(series.isna().sum()),
        "null_pct": round(series.isna().sum() / len(series) * 100, 1),
    }

    # Handle columns with unhashable types (lists, dicts)
    try:
        info["unique_count"] = int(series.nunique())
    except TypeError:
        # Column contains unhashable types like lists
        info["unique_count"] = -1
        info["semantic_type"] = "complex"
        info["note"] = "Contains unhashable values (lists/dicts)"
        return info

    # Determine semantic type
    if pd.api.types.is_datetime64_any_dtype(series):
        info["semantic_type"] = "temporal"
        valid = series.dropna()
        if len(valid) > 0:
            info["min"] = str(valid.min())
            info["max"] = str(valid.max())
    elif pd.api.types.is_numeric_dtype(series):
        info["semantic_type"] = "numerical"
        info["min"] = float(series.min()) if not series.isna().all() else None
        info["max"] = float(series.max()) if not series.isna().all() else None
        info["mean"] = round(float(series.mean()), 2) if not series.isna().all() else None
        info["std"] = round(float(series.std()), 2) if not series.isna().all() else None
    elif pd.api.types.is_bool_dtype(series):
        info["semantic_type"] = "boolean"
        info["true_count"] = int(series.sum())
        info["true_pct"] = round(series.mean() * 100, 1)
    elif info["unique_count"] <= min(20, len(series) * 0.1):
        # Low cardinality = categorical
        info["semantic_type"] = "categorical"
        info["top_values"] = series.value_counts().head(10).to_dict()
    else:
        info["semantic_type"] = "text"
        info["avg_length"] = round(series.astype(str).str.len().mean(), 1)

    return info


def _generate_recommendations(df: pd.DataFrame, columns: dict) -> list[dict[str, Any]]:
    """Generate chart recommendations based on column types."""
    recommendations = []

    # Find columns by type
    temporal_cols = [c for c, info in columns.items() if info.get("semantic_type") == "temporal"]
    numerical_cols = [c for c, info in columns.items() if info.get("semantic_type") == "numerical"]
    categorical_cols = [c for c, info in columns.items() if info.get("semantic_type") == "categorical"]

    # Time series recommendations
    for t_col in temporal_cols[:2]:  # Limit to first 2
        recommendations.append({
            "name": f"trend_by_{t_col}",
            "description": f"Count over {t_col}",
            "chart_type": "line",
            "encoding": {"x": t_col, "y": "count"},
            "create_figure_cmd": "training-curves",
        })

    # Categorical distribution recommendations
    for c_col in categorical_cols[:3]:  # Limit to first 3
        recommendations.append({
            "name": f"distribution_{c_col}",
            "description": f"Distribution of {c_col}",
            "chart_type": "bar",
            "encoding": {"x": c_col, "y": "count"},
            "create_figure_cmd": "metrics --type bar",
        })

    # Numerical distribution recommendations
    for n_col in numerical_cols[:2]:
        recommendations.append({
            "name": f"histogram_{n_col}",
            "description": f"Histogram of {n_col}",
            "chart_type": "bar",
            "encoding": {"x": f"{n_col}_bins", "y": "count"},
            "create_figure_cmd": "metrics --type bar",
        })

    # Heatmap if we have 2+ categorical columns
    if len(categorical_cols) >= 2:
        recommendations.append({
            "name": f"heatmap_{categorical_cols[0]}_x_{categorical_cols[1]}",
            "description": f"{categorical_cols[0]} vs {categorical_cols[1]}",
            "chart_type": "heatmap",
            "encoding": {"x": categorical_cols[0], "y": categorical_cols[1], "color": "count"},
            "create_figure_cmd": "heatmap",
        })

    # Time x categorical heatmap
    if temporal_cols and categorical_cols:
        recommendations.append({
            "name": f"heatmap_{temporal_cols[0]}_x_{categorical_cols[0]}",
            "description": f"Activity heatmap: {categorical_cols[0]} over time",
            "chart_type": "heatmap",
            "encoding": {"x": temporal_cols[0], "y": categorical_cols[0], "color": "count"},
            "create_figure_cmd": "heatmap",
        })

    # Correlation if 2+ numerical columns
    if len(numerical_cols) >= 2:
        recommendations.append({
            "name": "correlation_matrix",
            "description": f"Correlation between numerical columns",
            "chart_type": "heatmap",
            "encoding": {"x": "column_a", "y": "column_b", "color": "correlation"},
            "create_figure_cmd": "heatmap",
        })

    return recommendations


def flexible_group_by(
    df: pd.DataFrame,
    group_col: str,
    agg_col: str | None = None,
    agg_func: Literal["count", "sum", "mean", "min", "max"] = "count",
) -> dict[str, Any]:
    """Flexible grouping by any column with any aggregation.

    Args:
        df: DataFrame to analyze
        group_col: Column to group by
        agg_col: Column to aggregate (None for count)
        agg_func: Aggregation function

    Returns:
        Dict with grouped data ready for visualization
    """
    if group_col not in df.columns:
        return {"error": f"Column '{group_col}' not found"}

    if agg_func == "count" or agg_col is None:
        grouped = df.groupby(group_col).size()
        agg_label = "count"
    else:
        if agg_col not in df.columns:
            return {"error": f"Column '{agg_col}' not found"}
        grouped = df.groupby(group_col)[agg_col].agg(agg_func)
        agg_label = f"{agg_func}_{agg_col}"

    result = {
        "group_by": group_col,
        "aggregation": agg_label,
        "data": {str(k): float(v) if pd.notna(v) else 0 for k, v in grouped.items()},
        "total_groups": len(grouped),
        "chart_spec": {
            "chart_type": "bar",
            "encoding": {"x": group_col, "y": agg_label},
            "create_figure_cmd": "metrics --type bar",
        },
    }

    return result


def numerical_stats(df: pd.DataFrame, columns: list[str] | None = None) -> dict[str, Any]:
    """Compute statistics for numerical columns.

    Args:
        df: DataFrame to analyze
        columns: Specific columns (None for all numerical)

    Returns:
        Dict with statistics and correlation matrix
    """
    if columns:
        num_cols = [c for c in columns if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
    else:
        num_cols = df.select_dtypes(include=["number"]).columns.tolist()

    if not num_cols:
        return {"error": "No numerical columns found"}

    stats = {}
    for col in num_cols:
        series = df[col].dropna()
        stats[col] = {
            "count": len(series),
            "mean": round(float(series.mean()), 4),
            "std": round(float(series.std()), 4),
            "min": float(series.min()),
            "25%": float(series.quantile(0.25)),
            "50%": float(series.quantile(0.50)),
            "75%": float(series.quantile(0.75)),
            "max": float(series.max()),
        }

    result: dict[str, Any] = {"columns": stats}

    # Correlation matrix if multiple columns
    if len(num_cols) >= 2:
        corr = df[num_cols].corr()
        result["correlation"] = {
            str(i): {str(j): round(corr.loc[i, j], 3) for j in corr.columns}
            for i in corr.index
        }
        result["chart_spec"] = {
            "chart_type": "heatmap",
            "encoding": {"x": "column_a", "y": "column_b", "color": "correlation"},
            "create_figure_cmd": "heatmap",
        }

    return result


def export_chart_spec(
    df: pd.DataFrame,
    chart_name: str,
    x_col: str,
    y_col: str | None = None,
    color_col: str | None = None,
    chart_type: str = "bar",
    agg_func: str = "count",
) -> dict[str, Any]:
    """Export a chart specification ready for create-figure.

    Args:
        df: DataFrame with data
        chart_name: Name for the chart
        x_col: X-axis column
        y_col: Y-axis column (None for count)
        color_col: Color encoding column (for heatmaps)
        chart_type: Type of chart (bar, line, heatmap, etc.)
        agg_func: Aggregation function

    Returns:
        Chart spec with data in create-figure format
    """
    if x_col not in df.columns:
        return {"error": f"Column '{x_col}' not found"}

    spec: dict[str, Any] = {
        "name": chart_name,
        "chart_type": chart_type,
        "encoding": {"x": x_col},
        "create_figure_cmd": CREATE_FIGURE_COMMANDS.get(chart_type, "metrics"),
    }

    if chart_type == "heatmap":
        if not y_col or y_col not in df.columns:
            return {"error": "Heatmap requires y_col"}

        pivot = df.pivot_table(index=y_col, columns=x_col, aggfunc="size", fill_value=0)
        spec["data"] = {
            str(row): {str(col): int(pivot.loc[row, col]) for col in pivot.columns}
            for row in pivot.index
        }
        spec["encoding"]["y"] = y_col
        spec["encoding"]["color"] = "count"

    elif chart_type in ["bar", "hbar", "pie"]:
        if y_col and y_col in df.columns:
            grouped = df.groupby(x_col)[y_col].agg(agg_func)
        else:
            grouped = df.groupby(x_col).size()

        spec["data"] = {"metrics": {str(k): float(v) for k, v in grouped.items()}}
        spec["encoding"]["y"] = y_col or "count"

    elif chart_type in ["line", "area"]:
        if y_col and y_col in df.columns:
            grouped = df.groupby(x_col)[y_col].agg(agg_func)
        else:
            grouped = df.groupby(x_col).size()

        spec["data"] = {
            chart_name: {
                "x": list(range(len(grouped))),
                "y": [float(v) for v in grouped.values],
            }
        }
        spec["encoding"]["y"] = y_col or "count"

    return spec


def load_jsonl(path: str | Path) -> pd.DataFrame:
    """Load JSONL file into DataFrame.

    Auto-detects timestamp column from common names:
    - ts, timestamp, time, datetime, date, watched_at, created_at

    Returns DataFrame with standardized columns including 'datetime'.
    """
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

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # Auto-detect timestamp column
    ts_columns = ["ts", "timestamp", "time", "datetime", "date", "watched_at", "created_at"]
    ts_col = None
    for col in ts_columns:
        if col in df.columns:
            ts_col = col
            break

    if ts_col:
        df["datetime"] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
        df["date"] = df["datetime"].dt.date
        df["hour"] = df["datetime"].dt.hour
        df["day_of_week"] = df["datetime"].dt.day_name()
        df["week"] = df["datetime"].dt.isocalendar().week
        df["month"] = df["datetime"].dt.to_period("M")

    # Detect music content from URL if present
    if "url" in df.columns:
        df["is_music"] = df["url"].str.contains("music.youtube.com", na=False)

    return df


def viewing_trends(df: pd.DataFrame, window: int = 7) -> dict[str, Any]:
    """Compute viewing trends with rolling averages.

    Args:
        df: DataFrame with 'date' column
        window: Rolling window size in days

    Returns:
        Dict with trend analysis
    """
    if "date" not in df.columns or df["date"].isna().all():
        return {"error": "No valid date data"}

    # Daily counts
    daily = df.groupby("date").size()

    if len(daily) == 0:
        return {"error": "No data points"}

    # Rolling average
    rolling = daily.rolling(window=window, min_periods=1).mean()

    # Recent vs historical comparison
    recent_avg = float(daily.tail(window).mean()) if len(daily) >= window else float(daily.mean())
    historical_avg = float(daily.mean())

    # Determine trend
    if historical_avg > 0:
        change_pct = (recent_avg / historical_avg - 1) * 100
        trend = "increasing" if change_pct > 10 else "decreasing" if change_pct < -10 else "stable"
    else:
        change_pct = 0
        trend = "unknown"

    return {
        "daily_average": round(historical_avg, 1),
        "recent_average": round(recent_avg, 1),
        "trend": trend,
        "trend_change_pct": round(change_pct, 1),
        "peak_day": str(daily.idxmax()) if len(daily) > 0 else None,
        "peak_count": int(daily.max()) if len(daily) > 0 else 0,
        "total_days": len(daily),
        "window_days": window,
    }


def session_analysis(df: pd.DataFrame, gap_minutes: int = 30) -> dict[str, Any]:
    """Detect viewing sessions and analyze patterns.

    A session is a sequence of items with gaps < gap_minutes.

    Args:
        df: DataFrame with 'datetime' column
        gap_minutes: Max gap between items in same session

    Returns:
        Dict with session insights
    """
    if "datetime" not in df.columns or df["datetime"].isna().all():
        return {"error": "No valid timestamp data"}

    df_sorted = df.sort_values("datetime").dropna(subset=["datetime"])

    if len(df_sorted) < 2:
        return {"total_sessions": 1, "avg_session_length": len(df_sorted)}

    # Calculate time gaps between consecutive items
    gaps = df_sorted["datetime"].diff()
    threshold = pd.Timedelta(minutes=gap_minutes)

    # Mark session starts (first item or gap > threshold)
    session_starts = gaps > threshold
    session_starts.iloc[0] = True

    # Assign session IDs
    session_ids = session_starts.cumsum()

    # Session statistics
    session_sizes = session_ids.value_counts()

    # Binge detection (5+ items in session)
    binge_threshold = 5
    binge_sessions = int((session_sizes >= binge_threshold).sum())
    total_sessions = int(session_ids.max())

    return {
        "total_sessions": total_sessions,
        "avg_session_length": round(float(session_sizes.mean()), 1),
        "max_session_length": int(session_sizes.max()),
        "min_session_length": int(session_sizes.min()),
        "binge_sessions": binge_sessions,
        "binge_pct": round(binge_sessions / total_sessions * 100, 1) if total_sessions > 0 else 0,
        "gap_minutes": gap_minutes,
    }


def time_patterns(df: pd.DataFrame) -> dict[str, Any]:
    """Analyze viewing patterns by time of day.

    Returns:
        Dict with time-based insights
    """
    if "hour" not in df.columns:
        return {"error": "No hour data"}

    # Hour distribution
    hour_counts = df["hour"].value_counts().sort_index()

    if len(hour_counts) == 0:
        return {"error": "No hour data"}

    # Peak hour
    peak_hour = int(hour_counts.idxmax())

    # Time period classification
    def get_period(hour: int) -> str:
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

    result = {
        "peak_hour": peak_hour,
        "peak_period": get_period(peak_hour),
        "period_distribution": period_counts.to_dict(),
        "hour_distribution": {str(h): int(c) for h, c in hour_counts.items()},
    }

    # Music-specific patterns if available
    if "is_music" in df.columns:
        music_df = df[df["is_music"]]
        if len(music_df) > 0:
            music_hour_counts = music_df["hour"].value_counts()
            if len(music_hour_counts) > 0:
                music_peak = int(music_hour_counts.idxmax())
                result["music_peak_hour"] = music_peak
                result["music_peak_period"] = get_period(music_peak)

    return result


def content_evolution(df: pd.DataFrame, periods: int = 4) -> dict[str, Any]:
    """Track how content preferences evolve over time.

    Divides history into equal time periods and compares.

    Args:
        df: DataFrame with 'datetime' column
        periods: Number of time periods to analyze

    Returns:
        Dict with evolution insights
    """
    if "datetime" not in df.columns:
        return {"error": "No datetime column"}

    df_sorted = df.sort_values("datetime").dropna(subset=["datetime"])

    if len(df_sorted) < periods * 10:
        return {"error": f"Not enough data for {periods} periods (need at least {periods * 10} items)"}

    # Divide into equal-sized periods
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
            music_ratio = float(period_df["is_music"].mean())
            period_info["music_ratio_pct"] = round(music_ratio * 100, 1)

        evolution.append(period_info)

    # Calculate overall trends
    result: dict[str, Any] = {"periods": evolution}

    if "is_music" in df.columns and len(evolution) >= 2:
        first_music = evolution[0].get("music_ratio_pct", 0)
        last_music = evolution[-1].get("music_ratio_pct", 0)
        change = last_music - first_music
        result["music_trend"] = "increasing" if change > 5 else "decreasing" if change < -5 else "stable"
        result["music_change_pct"] = round(change, 1)

    return result


def generate_insights(path: str | Path) -> dict[str, Any]:
    """Generate comprehensive insights from JSONL data.

    Args:
        path: Path to JSONL file

    Returns:
        Dict with all analysis results
    """
    df = load_jsonl(path)

    if df.empty:
        return {"error": "No data loaded"}

    insights: dict[str, Any] = {
        "summary": {
            "total_items": len(df),
            "date_range": {},
        },
        "trends": viewing_trends(df),
        "sessions": session_analysis(df),
        "time_patterns": time_patterns(df),
        "evolution": content_evolution(df),
    }

    # Add date range to summary
    if "datetime" in df.columns and not df["datetime"].isna().all():
        valid_dates = df["datetime"].dropna()
        if len(valid_dates) > 0:
            insights["summary"]["date_range"] = {
                "start": str(valid_dates.min().date()),
                "end": str(valid_dates.max().date()),
            }

    # Add music stats if available
    if "is_music" in df.columns:
        music_count = int(df["is_music"].sum())
        insights["summary"]["music_items"] = music_count
        insights["summary"]["music_pct"] = round(music_count / len(df) * 100, 1)

    return insights


def format_for_horus(insights: dict[str, Any]) -> str:
    """Format insights as Horus-style narrative.

    Returns text in persona voice suitable for integration.
    """
    lines = ["## Viewing Pattern Analysis\n"]

    # Summary
    summary = insights.get("summary", {})
    total = summary.get("total_items", 0)
    date_range = summary.get("date_range", {})

    if date_range.get("start"):
        lines.append(f"**Observation period**: {date_range.get('start')} to {date_range.get('end')}")
    lines.append(f"**Total content consumed**: {total:,} items")

    if summary.get("music_pct"):
        lines.append(f"**Music content ratio**: {summary['music_pct']:.1f}%")
    lines.append("")

    # Trends
    trends = insights.get("trends", {})
    if trends.get("trend") and trends["trend"] != "unknown":
        trend_desc = {
            "increasing": "Your consumption has intensified",
            "decreasing": "Your engagement has waned",
            "stable": "Your patterns remain consistent",
        }.get(trends["trend"], "Pattern unclear")

        change = trends.get("trend_change_pct", 0)
        lines.append(f"**Trend**: {trend_desc} ({change:+.1f}% vs historical average)")
        lines.append(f"**Daily average**: {trends.get('daily_average', 0):.1f} items")
    lines.append("")

    # Sessions
    sessions = insights.get("sessions", {})
    if sessions.get("total_sessions"):
        lines.append(f"**Viewing sessions**: {sessions['total_sessions']:,} detected")
        lines.append(f"**Average session**: {sessions.get('avg_session_length', 0):.1f} items")

        if sessions.get("binge_sessions", 0) > 0:
            lines.append(f"**Binge sessions**: {sessions['binge_sessions']} ({sessions.get('binge_pct', 0):.1f}% of sessions)")
            lines.append("  _Extended immersion detected - deep engagement with content._")
    lines.append("")

    # Time patterns
    patterns = insights.get("time_patterns", {})
    if patterns.get("peak_period"):
        period_desc = {
            "morning": "dawn hours",
            "afternoon": "midday",
            "evening": "twilight",
            "night": "nocturnal hours",
        }.get(patterns["peak_period"], patterns["peak_period"])

        lines.append(f"**Peak activity**: {period_desc} (hour {patterns.get('peak_hour')})")

        if patterns.get("music_peak_period"):
            music_period = {
                "morning": "sunrise contemplation",
                "afternoon": "focused work",
                "evening": "transitional moods",
                "night": "introspective darkness",
            }.get(patterns["music_peak_period"], patterns["music_peak_period"])
            lines.append(f"**Music peaks during**: {music_period}")
    lines.append("")

    # Evolution
    evolution = insights.get("evolution", {})
    if evolution.get("music_trend"):
        trend_narrative = {
            "increasing": "Music consumption grows - perhaps seeking more atmospheric immersion",
            "decreasing": "Music consumption wanes - focus shifting elsewhere",
            "stable": "Musical preferences remain anchored",
        }.get(evolution["music_trend"], "")

        if trend_narrative:
            lines.append(f"**Evolution**: {trend_narrative}")
            lines.append(f"  _(Change: {evolution.get('music_change_pct', 0):+.1f}% across observation period)_")

    return "\n".join(lines)
