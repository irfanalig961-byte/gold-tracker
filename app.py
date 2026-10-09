import io
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots

# ---------------- settings: the only lines you may ever need to change ----------------
START_DATE = "2026-09-29"
NOTES_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSPU8Q9EaMP1vNOMkcKnnwo5zs3XXyubtLbVWy3__SMqE1FZ1pnZhegHEa6xTzIE2e2MQai1CWmpqjk/pub?gid=0&single=true&output=csv"
# ----------------------------------------------------------------------------------------

st.set_page_config(page_title="Gold Tracker", page_icon="🟡", layout="wide")


@st.cache_data(ttl=3600)            # fetch prices at most once an hour
def load_prices(start):
    tickers = {"GC=F": "Gold", "SI=F": "Silver", "DX-Y.NYB": "Dollar"}
    data = yf.download(list(tickers), start=start, progress=False)["Close"]
    data = data.rename(columns=tickers)[["Gold", "Dollar", "Silver"]].dropna()
    data.index = pd.to_datetime(data.index).tz_localize(None).normalize()
    return data


@st.cache_data(ttl=300)             # re-read your Google Sheet every 5 minutes
def load_notes(url):
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        raise ValueError(f"Google answered with error {r.status_code}.")
    text = r.content.decode("utf-8-sig")
    if text.lstrip().startswith("<"):
        raise ValueError("Google sent a web page instead of the notes. "
                         "Check Share > General access is 'Anyone with the link: Viewer'.")
    notes = pd.read_csv(io.StringIO(text), dtype=str).fillna("")
    notes.columns = [c.strip().lower() for c in notes.columns]
    for col in ["date", "title", "step1", "step2", "step3", "gold_source", "gold_link",
                "dollar_note", "dollar_source", "dollar_link", "silver_note", "silver_source", "silver_link"]:
        if col not in notes.columns:
            notes[col] = ""
    notes["date"] = pd.to_datetime(notes["date"].str.strip(), errors="coerce").dt.normalize()
    return notes.dropna(subset=["date"]).sort_values("date")


def pct(x):
    return "" if pd.isna(x) else f"{x:+.2f}%"


# ---------------- data ----------------
try:
    data = load_prices(START_DATE)
except Exception as e:
    st.error(f"Could not download prices from Yahoo Finance just now. Refresh in a minute. ({e})")
    st.stop()
if data.empty:
    st.error("No prices came back from Yahoo Finance. Refresh in a minute.")
    st.stop()

notes_error = None
try:
    notes = load_notes(NOTES_URL)
except Exception as e:
    notes_error = str(e)
    notes = pd.DataFrame(columns=["date", "title", "step1", "step2", "step3", "gold_source", "gold_link",
                                  "dollar_note", "dollar_source", "dollar_link", "silver_note", "silver_source", "silver_link"])
    notes["date"] = pd.to_datetime(notes["date"])

moves = data.pct_change() * 100                       # daily % change
notes_in_data = notes[notes["date"].isin(data.index)]

# ---------------- header ----------------
st.title("Gold Tracker")
st.caption("Gold next to the asset that usually moves against it (the US dollar) "
           "and the one that usually moves with it (silver). Click any day on the chart to see what happened.")

last = data.index[-1]
c1, c2, c3 = st.columns(3)
for col, name, fmt in [(c1, "Gold", "${:,.0f}"), (c2, "Dollar", "{:.2f}"), (c3, "Silver", "${:.2f}")]:
    label = {"Gold": "Gold (US$/oz)", "Dollar": "US dollar index", "Silver": "Silver (US$/oz)"}[name]
    col.metric(label, fmt.format(data[name].iloc[-1]), pct(moves[name].iloc[-1]))
st.caption(f"Latest close: {last:%a %d %b %Y}. Prices refresh hourly, notes every 5 minutes. "
           f"Notes loaded: {len(notes)}.")
if notes_error:
    st.warning(f"Could not read the notes sheet: {notes_error}")
elif len(notes) == 0:
    st.info("The notes sheet was read, but no rows had a valid date in the 'date' column (e.g. 2026-10-09).")
if st.button("Reload notes now"):
    load_notes.clear()
    st.rerun()

with st.expander("What is measured, and how to read it"):
    st.markdown("""
- **Gold**: COMEX gold futures (GC=F), US dollars per troy ounce, daily closing price. Gold line.
- **Silver**: COMEX silver futures (SI=F), US dollars per troy ounce, daily closing price. Blue line.
- **US dollar index** (DX-Y.NYB): the dollar against six currencies, weighted euro 57.6%, Japanese yen 13.6%,
  British pound 11.9%, Canadian dollar 9.1%, Swedish krona 4.2%, Swiss franc 3.6%. Green line.
- **Black dots**: days with a written note for that line.
- **Daily % change**: today's close compared with yesterday's close.
- **Correlation**: how closely daily % changes move with gold, using all days so far.
  −1 = always opposite, 0 = no link, +1 = always together.
  The dollar is usually negative with gold, silver usually positive.
- Source: Yahoo Finance (prices) and my own notes (news).
""")

# ---------------- chart ----------------
corr_dollar = moves["Gold"].expanding(min_periods=4).corr(moves["Dollar"])
corr_silver = moves["Gold"].expanding(min_periods=4).corr(moves["Silver"])

fig = make_subplots(
    rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.07,
    row_heights=[0.34, 0.2, 0.2, 0.26],
    subplot_titles=["Gold, US$ per troy ounce (black dots = days with notes)",
                    "US dollar index: usually moves OPPOSITE to gold",
                    "Silver, US$ per troy ounce: usually moves WITH gold",
                    "Correlation with gold so far (−1 opposite · 0 no link · +1 together)"])
fig.add_trace(go.Scatter(x=data.index, y=data["Gold"], name="Gold", mode="lines+markers",
                         marker=dict(size=6), line=dict(color="goldenrod")), row=1, col=1)
fig.add_trace(go.Scatter(x=data.index, y=data["Dollar"], name="Dollar", line=dict(color="seagreen")), row=2, col=1)
fig.add_trace(go.Scatter(x=data.index, y=data["Silver"], name="Silver", line=dict(color="steelblue")), row=3, col=1)
fig.add_trace(go.Scatter(x=corr_dollar.index, y=corr_dollar, name="Dollar vs gold",
                         line=dict(color="seagreen")), row=4, col=1)
fig.add_trace(go.Scatter(x=corr_silver.index, y=corr_silver, name="Silver vs gold",
                         line=dict(color="steelblue")), row=4, col=1)
fig.add_hline(y=0, line_color="grey", row=4, col=1)
fig.update_yaxes(range=[-1, 1], title_text="−1 to +1", row=4, col=1)
fig.update_yaxes(title_text="US$/oz", row=1, col=1)
fig.update_yaxes(title_text="Index", row=2, col=1)
fig.update_yaxes(title_text="US$/oz", row=3, col=1)
# black dots: days with a note, on each line that has news for that day
for row_no, name, note_col, link_col, label in [(1, "Gold", "title", "gold_link", "Gold news"),
                                                (2, "Dollar", "dollar_note", "dollar_link", "Dollar news"),
                                                (3, "Silver", "silver_note", "silver_link", "Silver news")]:
    has = notes_in_data[(notes_in_data[note_col] != "") | (notes_in_data[link_col] != "")]
    if len(has):
        fig.add_trace(go.Scatter(x=has["date"], y=data.loc[has["date"], name], mode="markers",
                                 marker=dict(size=11, color="black"), text=has[note_col],
                                 hoverinfo="text", name=label, showlegend=False),
                      row=row_no, col=1)
fig.update_layout(height=900, hovermode="x unified", clickmode="event+select",
                  legend=dict(orientation="h", y=-0.05), margin=dict(t=40, b=10))

event = st.plotly_chart(fig, width="stretch", on_select="rerun",
                        selection_mode="points", key="chart")

# which day did the viewer pick?
picked = None
try:
    pts = event.selection.points
    if pts:
        picked = pd.Timestamp(str(pts[0]["x"])[:10])
except Exception:
    pass

all_days = list(data.index[::-1])
default = notes_in_data["date"].iloc[-1] if len(notes_in_data) else data.index[-1]
if picked is not None and picked in data.index:
    default = picked
day = st.selectbox("Day", all_days, index=all_days.index(default),
                   format_func=lambda d: d.strftime("%a %d %b %Y") + ("  ●" if d in set(notes_in_data["date"]) else ""))

# ---------------- day file ----------------
left, right = st.columns([3, 2])
with left:
    st.subheader(day.strftime("%A %d %B %Y"))
    row = notes_in_data[notes_in_data["date"] == day]
    if len(row):
        n = row.iloc[-1]
        st.markdown(f"#### {n['title']}")
        steps = [s for s in [n["step1"], n["step2"], n["step3"]] if s.strip()]
        st.markdown("\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)))
        if n["gold_link"]:
            st.markdown(f"📰 Gold news: [{n['gold_source'] or 'read the article'}]({n['gold_link']})")
        if n["dollar_note"] or n["dollar_link"]:
            line = f"💵 Dollar: {n['dollar_note']}" if n["dollar_note"] else "💵 Dollar news:"
            if n["dollar_link"]:
