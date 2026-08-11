"""Minimal Streamlit dashboard for CARTOON NICHE RADAR outputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "data" / "reports"
SCORED = ROOT / "data" / "scored"


def main() -> None:
    st.set_page_config(page_title="CARTOON NICHE RADAR", layout="wide")
    st.title("CARTOON NICHE RADAR")
    st.caption(
        "Empirical niche research dashboard. Opportunity scores are INFERENCE. "
        "Winners are not declared when evidence gates fail."
    )

    top20_path = REPORTS / "top20_niches.csv"
    highlights_path = REPORTS / "highlights.json"
    summary_path = REPORTS / "SUMMARY.md"
    scores_path = SCORED / "niche_scores.csv"

    if not top20_path.exists():
        st.warning("No reports yet. Run: `cnr run-all --use-sample` or live collect.")
        return

    import json

    highlights = json.loads(highlights_path.read_text(encoding="utf-8")) if highlights_path.exists() else {}
    st.subheader("Highlights")
    cols = st.columns(5)
    for col, (name, payload) in zip(cols, highlights.items()):
        with col:
            st.markdown(f"**{name}**")
            if payload is None:
                st.info("INSUFFICIENT_DATA")
            else:
                st.write(f"{payload.get('AGE')} · {payload.get('THEME')}")
                st.metric("Opportunity", payload.get("OPPORTUNITY_SCORE"))

    st.subheader("TOP-20 niches")
    top20 = pd.read_csv(top20_path)
    st.dataframe(top20, use_container_width=True)

    if scores_path.exists():
        st.subheader("All scored niches")
        scores = pd.read_csv(scores_path)
        st.dataframe(scores, use_container_width=True)

    if summary_path.exists():
        st.subheader("Summary")
        st.markdown(summary_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
