"""Big 4 Firm & City Recommender: Streamlit front end.

Run:  streamlit run app/streamlit_app.py

Reads only precomputed files from data/processed/ and data/manual/ (no network calls,
no paid APIs). User inputs live in the session and are never saved.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.demo_data import demo_tables  # noqa: E402
from recommender import UserInputs, load_tables, recommend  # noqa: E402
from recommender.criteria import load_criteria  # noqa: E402
from recommender.schemas import FIRMS, SERVICE_LINES  # noqa: E402

st.set_page_config(page_title="Big 4 Firm & City Recommender", page_icon="🗺️", layout="wide")

FIRM_COLORS = {"Deloitte": [134, 188, 37], "PwC": [224, 48, 30], "EY": [255, 230, 0], "KPMG": [0, 51, 141]}


@st.cache_data(show_spinner="Loading data...")
def get_tables() -> tuple[dict[str, pd.DataFrame], bool]:
    """Real tables if the pipeline has run, otherwise synthetic demo tables."""
    try:
        return load_tables(), False
    except FileNotFoundError:
        return demo_tables(), True


tables, using_demo = get_tables()
labels, crits = load_criteria()
active_cats = [k for k in labels if any(c.category == k and c.mvp for c in crits)]

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("About you")
    service_line = st.selectbox("Service line", SERVICE_LINES)
    firms = st.multiselect("Firms you'd consider", FIRMS, default=list(FIRMS))
    use_salary = st.checkbox("I have a specific salary in mind", value=False)
    salary = st.number_input("Base salary ($)", 40_000, 200_000, 80_000, 1_000) if use_salary else None

    st.header("What matters to you")
    st.caption("0 = ignore, 5 = very important")
    weights = {k: st.slider(labels[k], 0, 5, 3 if k in ("pay", "cost_of_living") else 0, key=f"w_{k}")
               for k in active_cats}

    st.header("Must-haves")
    no_tax = st.checkbox("No state income tax")
    states = sorted(tables["offices"]["state"].dropna().unique())
    exclude = st.multiselect("Exclude states", states)
    max_rent = st.number_input("Max monthly rent ($, 0 = no limit)", 0, 6000, 0, 100)
    max_miles = st.slider("Max miles from office", 1, 50, 20)
    min_walk = st.slider("Min walkability index (0 = no minimum)", 0, 20, 0)
    top_n = st.slider("Metros to show", 1, 10, 5)

# ------------------------------------------------------------------ main
st.title("Big 4 Firm & City Recommender")
st.caption("For McCombs MPA graduates: find a firm, office, metro and neighborhood that fit you.")
if using_demo:
    st.warning("Showing **synthetic demo data** (made-up numbers). Run the data pipeline "
               "(`python ingest/run_all.py`) to see real results.")
if not firms:
    st.info("Pick at least one firm in the sidebar.")
    st.stop()
if not any(weights.values()):
    st.info("Set at least one importance slider above 0 to personalize the ranking. "
            "Until then every metro scores 50.")

inputs = UserInputs(
    service_line=service_line, salary=float(salary) if salary else None, firms=tuple(firms),
    weights={k: float(v) for k, v in weights.items() if v}, no_state_income_tax=no_tax,
    exclude_states=tuple(exclude), max_rent=float(max_rent) or None, max_miles_to_office=float(max_miles),
    min_walk_index=float(min_walk) or None, top_n_metros=top_n,
)

try:
    results = recommend(tables, inputs)
except Exception as e:  # surface data problems instead of a stack trace
    st.error(f"Could not compute recommendations: {e}")
    st.stop()

if not results:
    st.warning("No metros match your must-haves. Loosen a filter in the sidebar.")
    st.stop()

# ------------------------------------------------------------------ map
offices_all = tables["offices"]
off_pts = offices_all[offices_all["firm"].isin(firms)].dropna(subset=["lat", "lon"]).copy()
off_pts["color"] = off_pts["firm"].map(FIRM_COLORS)
top_codes = [r["metro"]["cbsa_code"] for r in results]
off_pts["top"] = off_pts["cbsa_code"].isin(top_codes)

zip_pts = pd.concat([r["zips"].assign(metro=r["metro"]["cbsa_name"]) for r in results if len(r["zips"])],
                    ignore_index=True) if any(len(r["zips"]) for r in results) else pd.DataFrame()

layers = [pdk.Layer("ScatterplotLayer", off_pts[~off_pts["top"]], get_position="[lon, lat]",
                    get_fill_color="color", get_radius=6000, radius_min_pixels=3, opacity=0.35,
                    pickable=True),
          pdk.Layer("ScatterplotLayer", off_pts[off_pts["top"]], get_position="[lon, lat]",
                    get_fill_color="color", get_line_color=[0, 0, 0], stroked=True, line_width_min_pixels=2,
                    get_radius=12000, radius_min_pixels=8, pickable=True)]
if len(zip_pts):
    layers.append(pdk.Layer("ScatterplotLayer", zip_pts, get_position="[lon, lat]",
                            get_fill_color=[30, 120, 255], get_radius=1500, radius_min_pixels=5, pickable=True))
st.pydeck_chart(pdk.Deck(
    layers=layers, map_style="light",
    initial_view_state=pdk.ViewState(latitude=39.0, longitude=-96.0, zoom=3.3),
    tooltip={"text": "{firm} {office_name}\n{city}, {state}"}))
st.caption("Large outlined dots: offices in your top metros. Faded dots: other offices. "
           "Blue dots: recommended ZIPs. Colors: Deloitte green, PwC red, EY yellow, KPMG blue.")

# ------------------------------------------------------------------ results
for rank, r in enumerate(results, 1):
    m, offs, zips = r["metro"], r["offices"], r["zips"]
    with st.expander(f"#{rank}  {m['cbsa_name']}  ·  score {m['score']:.0f}", expanded=rank == 1):
        c1, c2, c3 = st.columns(3)
        c1.metric("Estimated salary", f"${m['salary']:,.0f}")
        c2.metric("Take-home (after tax)", f"${m['net']:,.0f}")
        c3.metric("Real take-home (price-adjusted)", f"${m['real_take_home']:,.0f}")
        for reason in (m.get("reasons") or []):
            st.markdown(f"- {reason}")
        if m.get("low_confidence"):
            st.caption("Some inputs were missing for this metro and were filled with the median.")
        if m.get("salary_estimated_multiplier"):
            st.caption("No local wage data; salary shown is the national base.")

        st.subheader("Offices")
        cols = ["firm", "office_name", "address", "office_type", "salary_est", "service_line_confirmed"]
        st.dataframe(offs[[c for c in cols if c in offs]].rename(columns={
            "salary_est": "est. salary", "service_line_confirmed": f"{service_line} confirmed"}),
            hide_index=True, width="stretch")

        st.subheader("Neighborhoods (ZIPs near the top office)")
        if len(zips):
            zc = ["zcta", "score", "miles_to_office", "zori_latest", "walk_index"]
            st.dataframe(zips[[c for c in zc if c in zips]].round(1), hide_index=True,
                         width="stretch")
            for _, z in zips.head(3).iterrows():
                for reason in (z.get("reasons") or []):
                    st.markdown(f"- **{z['zcta']}**: {reason}")
        else:
            st.caption("No ZIPs matched your filters (or ZIP data isn't built yet).")

st.divider()
st.caption("Political data is never used in scoring. Data: Census, BEA, BLS, FBI, FEMA, EPA, Zillow, "
           "OpenStreetMap contributors, NOAA. Your inputs are not saved.")
