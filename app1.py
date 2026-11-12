import time

import pandas as pd
import requests
import streamlit as st

# ============================================================
# PAGE CONFIGURATION
# ============================================================
st.set_page_config(page_title="Calories Burnt Tracker", page_icon="🔥", layout="wide")
NINJA_API_URL = "https://api.api-ninjas.com/v1/caloriesburned"
KG_TO_LB = 2.20462


# ============================================================
# API NINJAS - CALORIES BURNED
# Returns calories_per_hour for the given body weight (in pounds).
# Total calories are computed locally as calories_per_hour * minutes / 60,
# so the result works for any duration.
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)
def search_exercise_api(activity, weight_lb, api_key):
    headers = {"X-Api-Key": api_key}
    params = {"activity": activity, "weight": int(weight_lb)}
    for attempt in range(3):
        try:
            response = requests.get(NINJA_API_URL, headers=headers, params=params, timeout=20)
            if response.status_code == 429:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                return [], "API Ninjas rate limit exceeded. Try again shortly."
            if response.status_code in (401, 403):
                return [], "Invalid API Ninjas key (or your plan does not allow this request)."
            response.raise_for_status()
            data = response.json()
            results = []
            for item in data:
                try:
                    cph = float(item.get("calories_per_hour"))
                except (TypeError, ValueError):
                    continue
                name = (item.get("name") or "").strip()
                if name and cph >= 0:
                    results.append({"name": name, "calories_per_hour": cph})
            return results, None
        except requests.exceptions.RequestException as exc:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                return [], f"Connection error: {exc}"
        except ValueError:
            return [], "API Ninjas returned an invalid response."
    return [], "Unable to retrieve exercise information."


# ============================================================
# SESSION STATE
# ============================================================
if "exercise_log" not in st.session_state:
    st.session_state.exercise_log = []

# ============================================================
# SIDEBAR - API KEY AND PROFILE
# ============================================================
with st.sidebar:
    st.title("⚙️ Settings")
    st.subheader("API Ninjas Configuration")
    api_key = st.text_input(
        "API Ninjas Key",
        type="password",
        placeholder="Enter your API key",
        help="Used only for exercise searches in this session.",
    )
    st.caption("Get a free key at https://api-ninjas.com/register")

    st.divider()
    st.subheader("Your details")
    weight_unit = st.radio("Weight unit", ["kg", "lb"], horizontal=True)
    if weight_unit == "kg":
        body_weight = st.number_input("Body weight (kg)", min_value=23.0, max_value=226.0, value=70.0, step=0.5)
        weight_lb = body_weight * KG_TO_LB
    else:
        body_weight = st.number_input("Body weight (lb)", min_value=50.0, max_value=500.0, value=154.0, step=1.0)
        weight_lb = body_weight
    weight_lb = max(50.0, min(500.0, weight_lb))

    maintenance = st.number_input(
        "Daily maintenance calories (kcal)",
        min_value=0, max_value=10000, value=2000, step=50,
        help="Calories your body uses in a day WITHOUT exercise (BMR/TDEE). "
             "Set to 0 to compare food only against exercise.",
    )

st.title("🔥 Calories Burnt Tracker")
st.caption("Log exercise, enter calories eaten, and see your calorie deficit or surplus.")

# ============================================================
# ADD EXERCISE
# ============================================================
st.subheader("🏃 Add Exercise")
query = st.text_input("Search activity", placeholder="Example: running, cycling, skiing, yoga", key="activity_query")

if len(query.strip()) >= 2:
    if not api_key:
        st.info("Enter your API Ninjas key in the sidebar to search.")
    else:
        with st.spinner("Searching API Ninjas..."):
            activities, api_error = search_exercise_api(query.strip(), weight_lb, api_key)
        if api_error:
            st.error(api_error)
        elif activities:
            labels = [f"{a['name']} | {a['calories_per_hour']:.0f} kcal / hour" for a in activities]
            idx = st.selectbox("Select an activity", range(len(activities)), format_func=lambda i: labels[i])
            minutes = st.number_input("Duration (minutes)", min_value=1, max_value=1440, value=30, step=5)
            burned = activities[idx]["calories_per_hour"] * minutes / 60
            st.metric("Estimated calories burned", f"{burned:.0f} kcal")
            if st.button("➕ Add exercise", type="primary"):
                st.session_state.exercise_log.append({
                    "Activity": activities[idx]["name"],
                    "Minutes": int(minutes),
                    "Calories burned": round(burned, 1),
                })
                st.rerun()
        else:
            st.warning("No matching activities found. Try a simpler word, e.g. 'run' or 'swim'.")

# ============================================================
# EXERCISE LOG
# ============================================================
st.divider()
st.subheader("📋 Today's Exercise")
log = st.session_state.exercise_log
if log:
    for i, row in enumerate(log):
        c1, c2, c3, c4 = st.columns([5, 2, 2, 1])
        c1.write(row["Activity"])
        c2.write(f"{row['Minutes']} min")
        c3.write(f"{row['Calories burned']:.0f} kcal")
        if c4.button("🗑️", key=f"del_{i}"):
            st.session_state.exercise_log.pop(i)
            st.rerun()
    if st.button("Clear all exercise"):
        st.session_state.exercise_log = []
        st.rerun()
else:
    st.info("No exercise logged yet.")

total_burned = sum(r["Calories burned"] for r in log)

# ============================================================
# CALORIES CONSUMED + DEFICIT / SURPLUS
# ============================================================
st.divider()
st.subheader("🍽️ Calories Consumed (Food)")
consumed = st.number_input(
    "Total calories eaten today (kcal)",
    min_value=0.0, max_value=20000.0, value=0.0, step=50.0,
)

total_expenditure = maintenance + total_burned
balance = consumed - total_expenditure  # negative = deficit, positive = surplus

st.subheader("📊 Daily Calorie Balance")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Consumed (food)", f"{consumed:.0f} kcal")
m2.metric("Maintenance", f"{maintenance:.0f} kcal")
m3.metric("Burned (exercise)", f"{total_burned:.0f} kcal")
m4.metric("Total expenditure", f"{total_expenditure:.0f} kcal")

if consumed == 0:
    st.info("Enter the calories you ate to see your deficit or surplus.")
elif balance < 0:
    st.success(f"✅ Calorie DEFICIT: {abs(balance):.0f} kcal")
elif balance > 0:
    st.warning(f"⚠️ Calorie SURPLUS: {balance:.0f} kcal")
else:
    st.info("Balanced: calories eaten equal calories used.")

if consumed > 0:
    st.progress(max(0.0, min(consumed / max(total_expenditure, 1), 1.0)))
    st.caption(f"Deficit/surplus = consumed ({consumed:.0f}) - maintenance ({maintenance:.0f}) - exercise ({total_burned:.0f})")

st.divider()
st.caption(
    "Calories burned are estimates from API Ninjas, scaled to your body weight and duration. "
    "Maintenance calories are the figure you enter."
)
