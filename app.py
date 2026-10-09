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

COLS = ["date", "title", "step1", "step2", "step3", "gold_source", "gold_link",
        "dollar_note", "dollar_source", "dollar_link", "silver_note", "silver_source", "silver_link"]

   st.set_page_config(page_title="Gold Tracker", page_icon="logo.png", layout="wide")
   st.logo("logo.png", size="large")

@st.cache_data(ttl=3600)
def load_prices(start):
    tickers = {"GC=F": "Gold", "SI=F": "Silver", "DX-Y.NYB": "Dollar"}
    data = yf.download(list(tickers), start=start, progress=False)["Close"]
    data = data.rename(columns=tickers)[["Gold", "Dollar", "Silver"]].dropna()
    data.index = pd.to_datetime(data.index).tz_localize(None).normalize()
    return data


@st.cache_data(ttl=300)
def load_notes(url):
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200: raise ValueError(f"Google answered with error {r.status_code}.")
    text = r.content.decode("utf-8-sig")
    if text.lstrip().startswith("<"): raise ValueError("Google sent a web page instead of the notes.")
    notes = pd.read_csv(io.StringIO(text), dtype=str).fillna("")
    notes.columns = [c.strip().lower() for c in notes.columns]
    for col in [c for c in COLS if c not in notes.columns]: notes[col] = ""
    notes["date"] = pd.to_datetime(notes["date"].str.strip(), errors="coerce").dt.normalize()
    return notes.dropna(subset=["date"]).sort_values("date")


def pct(x):
    return "" if pd.isna(x) else f"{x:+.2f}%"


def news_line(icon, label, note, source, link):
    text = f"{icon} {label}: {note}" if note else f"{icon} {label} news:"
    return text + (f" [{source or 'read the article'}]({link})" if link else "")


# ---------------- data ----------------
try:
    data = load_prices(START_DATE)
except Exception as e:
    st.error(f"Could not download prices from Yahoo Finance just now. Refresh in a minute. ({e})")
    st.stop()
if data.empty: st.error("No prices came back from Yahoo Finance. Refresh in a minute."); st.stop()

notes_error = None
try:
    notes = load_notes(NOTES_URL)
except Exception as e:
    notes_error = str(e)
    notes = pd.DataFrame(columns=COLS)
    notes["date"] = pd.to_datetime(notes["date"])

moves = data.pct_change() * 100
notes_in_data = notes[notes["date"].isin(data.index)]

# ---------------- header ----------------
st.title("Gold Tracker")
st.caption("Gold next to the asset that usually moves against it (the US dollar) "
           "and the one that usually moves with it (silver). Click any day on the chart to see what happened.")

last = data.index[-1]
c1, c2, c3 = st.columns(3)
c1.metric("Gold (US$/oz)", f"${data['Gold'].iloc[-1]:,.0f}", pct(moves["Gold"].iloc[-1]))
c2.metric("US dollar index", f"{data['Dollar'].iloc[-1]:.2f}", pct(moves["Dollar"].iloc[-1]))
c3.metric("Silver (US$/oz)", f"${data['Silver'].iloc[-1]:.2f}", pct(moves["Silver"].iloc[-1]))
st.caption(f"Latest close: {last:%a %d %b %Y}. Prices refresh hourly, notes every 5 minutes. "
           f"Notes loaded: {len(notes)}.")
if notes_error: st.warning(f"Could not read the notes sheet: {notes_error}")
if not notes_error and len(notes) == 0: st.info("The notes sheet was read, but no rows had a valid date (e.g. 2026-10-09).")
if st.button("Reload notes now"): load_notes.clear(); st.rerun()

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
gold_days = notes_in_data[(notes_in_data["title"] != "") | (notes_in_data["gold_link"] != "")]
dollar_days = notes_in_data[(notes_in_data["dollar_note"] != "") | (notes_in_data["dollar_link"] != "")]
silver_days = notes_in_data[(notes_in_data["silver_note"] != "") | (notes_in_data["silver_link"] != "")]
fig.add_trace(go.Scatter(x=gold_days["date"], y=data["Gold"].reindex(gold_days["date"]), mode="markers",
                         marker=dict(size=11, color="black"), text=gold_days["title"],
                         hoverinfo="text", name="Gold news", showlegend=False), row=1, col=1)
fig.add_trace(go.Scatter(x=dollar_days["date"], y=data["Dollar"].reindex(dollar_days["date"]), mode="markers",
                         marker=dict(size=11, color="black"), text=dollar_days["dollar_note"],
                         hoverinfo="text", name="Dollar news", showlegend=False), row=2, col=1)
fig.add_trace(go.Scatter(x=silver_days["date"], y=data["Silver"].reindex(silver_days["date"]), mode="markers",
                         marker=dict(size=11, color="black"), text=silver_days["silver_note"],
                         hoverinfo="text", name="Silver news", showlegend=False), row=3, col=1)
fig.update_layout(height=900, hovermode="x unified", clickmode="event+select",
                  legend=dict(orientation="h", y=-0.05), margin=dict(t=40, b=10))

event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points", key="chart")

# which day did the viewer pick?
try:
    pts = event.selection.points
    picked = pd.Timestamp(str(pts[0]["x"])[:10]) if pts else None
except Exception:
    picked = None

all_days = list(data.index[::-1])
note_days = set(notes_in_data["date"])
default = notes_in_data["date"].iloc[-1] if len(notes_in_data) else data.index[-1]
default = picked if picked is not None and picked in data.index else default
day = st.selectbox("Day", all_days, index=all_days.index(default),
                   format_func=lambda d: d.strftime("%a %d %b %Y") + ("  ●" if d in note_days else ""))

# ---------------- day file ----------------
left, right = st.columns([3, 2])
row = notes_in_data[notes_in_data["date"] == day]
n = row.iloc[-1] if len(row) else None
left.subheader(day.strftime("%A %d %B %Y"))
if n is None: left.info("No note for this day yet.")
if n is not None: left.markdown(f"#### {n['title']}")
if n is not None: left.markdown("\n".join(f"{i}. {t}" for i, t in enumerate([t for t in [n["step1"], n["step2"], n["step3"]] if t.strip()], 1)))
if n is not None and n["gold_link"]: left.markdown(news_line("📰", "Gold", "", n["gold_source"], n["gold_link"]))
if n is not None and (n["dollar_note"] or n["dollar_link"]): left.markdown(news_line("💵", "Dollar", n["dollar_note"], n["dollar_source"], n["dollar_link"]))
if n is not None and (n["silver_note"] or n["silver_link"]): left.markdown(news_line("🥈", "Silver", n["silver_note"], n["silver_source"], n["silver_link"]))

right.markdown("**Prices that day**")
right.dataframe(pd.DataFrame({"Close": data.loc[day].round(2), "Day change": moves.loc[day].map(pct)}), width="stretch")
g, x, s = moves.loc[day, "Gold"], moves.loc[day, "Dollar"], moves.loc[day, "Silver"]
check = bool(pd.notna(g) and abs(g) >= 0.05)
if check: right.write("✅ Dollar moved opposite to gold." if g * x < 0 else "❌ Dollar moved the same way as gold.")
if check: right.write("✅ Silver moved with gold." if g * s > 0 else "❌ Silver moved against gold.")

# ---------------- correlation summary ----------------
st.divider()
m = moves.dropna()
a, b = st.columns(2)
a.metric("Dollar vs gold, correlation so far", f"{m['Gold'].corr(m['Dollar']):+.2f}",
         help="−1 = always opposite, +1 = always together")
b.metric("Silver vs gold, correlation so far", f"{m['Gold'].corr(m['Silver']):+.2f}",
         help="−1 = always opposite, +1 = always together")
st.caption(f"Based on {len(m)} trading days. Fewer than 20 days is only a rough guide.")

# ---------------- all notes ----------------
st.subheader("All notes")
show = notes.copy()
show["date"] = show["date"].dt.date
if len(show) == 0: st.write("No notes yet.")
if len(show) > 0: st.dataframe(show[["date", "title", "step1", "step2", "step3", "gold_link",
                                     "dollar_note", "dollar_link", "silver_note", "silver_link"]],
                               width="stretch", hide_index=True,
                               column_config={"gold_link": st.column_config.LinkColumn("Gold news"),
                                              "dollar_link": st.column_config.LinkColumn("Dollar news"),
                                              "silver_link": st.column_config.LinkColumn("Silver news")})


# ---------------- Excel downloads ----------------
def excel_bytes(prices, events, weekly=None):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        prices.to_excel(xl, sheet_name="Daily prices")
        events.to_excel(xl, sheet_name="Events", index=False)
        if weekly is not None: weekly.to_excel(xl, sheet_name="Weekly")
    return buf.getvalue()


prices = data.round(2).join(moves.round(2).add_suffix(" % change"))
prices.index = prices.index.date
prices.index.name = "Date"
weekly = data.resample("W-FRI").last()
weekly = weekly.round(2).join((weekly.pct_change() * 100).round(2).add_suffix(" % week"))
weekly.index = weekly.index.date
weekly.index.name = "Week ending"

week_start = (last - pd.Timedelta(days=last.weekday())).date()
d1, d2 = st.columns(2)
d1.download_button("Download everything (Excel)", excel_bytes(prices, show, weekly),
                   file_name=f"gold_tracker_{date.today().isoformat()}.xlsx")
d2.download_button("Download this week (Excel)",
                   excel_bytes(prices[prices.index >= week_start], show[show["date"] >= week_start]),
                   file_name=f"gold_week_of_{week_start.isoformat()}.xlsx")
