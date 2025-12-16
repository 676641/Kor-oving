import json
import re
import datetime as dt
from typing import Any, Dict, List

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Øvingslogg", page_icon="⚔️", layout="centered")
st.title("⚔️ Øvingslogg – juleferien ⚔️")

# ----------------------------
# Konfig
# ----------------------------
MEMBERS = [
    # 1. tenor
    "Martin", "Herman", "Trygve", "Kristoffer", "Håkon Gåskjenn",
    # 2. tenor
    "Eirik", "Rasmus", "Julian", "Steffen", "Leon", "Emil", "Mikael", "Kristian",
    # 1. bass
    "Mats", "Birk", "Borgar", "Theo", "Jakob", "Harald", "Erling",
    # 2. bass
    "Maxi", "Erlend", "Andreas", "Håkon Aase", "Marcus", "Jens",
]

MINUTES = [10, 15, 20, 25, 30, 40, 45, 60, 75, 90]

# "Hva øvde du på?" (checkboxes)
PRACTICE_ITEMS = [
    "Oppvarming",
    "Stemmeøvelser",
    # sangliste
    "Slått til riddere",
    "Ridder kai",
    "Akevitten",
    "MAR-Schlägers vol. 2",
    "Nå, e nu alla",
    "Norge",
    "Så rå",
    "Gryning vid havet",
    "Ode til 2. bass",
    "Kjærlighet for en natt",
    "Bergmannen",
    "Now and forever",
    "Der skåles",
    "Slem",
    "Olav Trygvason",
    "Hjertet slår",
]

BEGIN = "OVINGSLOGG_V1_BEGIN"
END = "OVINGSLOGG_V1_END"

# ----------------------------
# GitHub helpers
# ----------------------------
def gh_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {st.secrets['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "streamlit-ovingslogg",
    }

def gh_base() -> str:
    owner = st.secrets["GITHUB_OWNER"]
    repo = st.secrets["GITHUB_REPO"]
    return f"https://api.github.com/repos/{owner}/{repo}"

def post_issue_comment(issue_number: int, body: str) -> None:
    url = f"{gh_base()}/issues/{issue_number}/comments"
    r = requests.post(url, headers=gh_headers(), json={"body": body}, timeout=20)
    r.raise_for_status()

def list_issue_comments(issue_number: int) -> List[Dict[str, Any]]:
    all_comments: List[Dict[str, Any]] = []
    page = 1
    while True:
        url = f"{gh_base()}/issues/{issue_number}/comments"
        r = requests.get(
            url,
            headers=gh_headers(),
            params={"per_page": 100, "page": page},
            timeout=20,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        all_comments.extend(batch)
        page += 1
    return all_comments

def encode_entry_as_comment(entry: Dict[str, Any]) -> str:
    payload = json.dumps(entry, ensure_ascii=False)
    return f"{BEGIN}\n```json\n{payload}\n```\n{END}"

def extract_entries_from_comments(comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    pattern = re.compile(rf"{BEGIN}\s*```json\s*(\{{.*?\}})\s*```\s*{END}", re.DOTALL)

    for c in comments:
        body = c.get("body", "") or ""
        m = pattern.search(body)
        if not m:
            continue
        raw = m.group(1)
        try:
            entries.append(json.loads(raw))
        except json.JSONDecodeError:
            continue

    return entries

@st.cache_data(ttl=30)
def load_log_df(issue_number: int) -> pd.DataFrame:
    comments = list_issue_comments(issue_number)
    entries = extract_entries_from_comments(comments)
    if not entries:
        return pd.DataFrame(columns=["ts", "date", "member", "minutes", "practiced"])

    df = pd.DataFrame(entries)
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0).astype(int)
    return df

def render_member_log(issue_number: int, member_name: str) -> None:
    st.divider()
    st.subheader(f"📒 Øvingslogg – {member_name}")

    df = load_log_df(issue_number)
    df = df[df["member"] == member_name].copy()

    if df.empty:
        st.info("Ingen økter logget ennå.")
        return

    df = df.sort_values("ts", ascending=False)
    df["practiced"] = df["practiced"].apply(lambda x: ", ".join(x) if isinstance(x, list) else "")

    st.dataframe(df[["date", "minutes", "practiced"]], use_container_width=True)

    st.subheader("📊 Oppsummering")
    st.metric("Totalt minutter", int(df["minutes"].sum()))
    st.metric("Antall økter", int(len(df)))

# ----------------------------
# Session state
# ----------------------------
if "show_log" not in st.session_state:
    st.session_state.show_log = False
if "selected_member" not in st.session_state:
    st.session_state.selected_member = MEMBERS[0]

# ----------------------------
# UI
# ----------------------------
issue_number = int(st.secrets["GITHUB_ISSUE_NUMBER"])

with st.form("logg", clear_on_submit=True):
    member = st.selectbox("Hvem er du?", MEMBERS, index=MEMBERS.index(st.session_state.selected_member))
    minutes = st.selectbox("Hvor lenge øvde du?", MINUTES, index=MINUTES.index(30))

    st.write("Hva øvde du på?")
    practiced = []
    cols = st.columns(2)
    for i, opt in enumerate(PRACTICE_ITEMS):
        if cols[i % 2].checkbox(opt, value=False):
            practiced.append(opt)

    col_a, col_b = st.columns(2)
    submit = col_a.form_submit_button("✅ Logg øving")
    show_log = col_b.form_submit_button("📒 Vis logg")

# Oppdater valgt medlem i state (så "Vis logg" alltid viser riktig)
st.session_state.selected_member = member

# "Vis logg" (uten å logge ny økt)
if show_log:
    st.session_state.show_log = True
    # ikke nødvendigvis cache-clear her, bare vis det som finnes
    st.rerun()

# Logg øving
if submit:
    entry = {
        "v": 1,
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "date": dt.date.today().isoformat(),
        "member": member,
        "minutes": int(minutes),
        "practiced": practiced,
    }

    try:
        post_issue_comment(issue_number, encode_entry_as_comment(entry))
        st.success("Logget! 🎉")
        load_log_df.clear()  # sørg for at ny logg kommer med

        st.session_state.show_log = True  # vis logg etter submit også
        st.rerun()
    except requests.HTTPError as e:
        st.error(f"Klarte ikke å lagre til GitHub (HTTP-feil). {e}")
    except Exception as e:
        st.error(f"Noe gikk galt: {e}")

# Vis individuell logg (kun hvis bruker har trykket "Vis logg" eller har logget)
if st.session_state.show_log and st.session_state.selected_member:
    render_member_log(issue_number, st.session_state.selected_member)
