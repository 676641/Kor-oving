import json
import re
import datetime as dt
from typing import Any, Dict, List

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Øvingslogg", page_icon="🎶", layout="centered")
st.title("🎶 Øvingslogg – juleferien")

# ----------------------------
# Konfig (faste valg)
# ----------------------------
VOICE_GROUPS = {
    "1. tenor": ["Martin", "Herman", "Trygve", "Kristoffer", "Håkon Gåskjenn"],
    "2. tenor": ["Eirik", "Rasmus", "Julian", "Steffen", "Leon", "Emil", "Mikael", "Kristian"],
    "1. bass":  ["Mats", "Birk", "Borgar", "Theo", "Jakob", "Harald", "Erling"],
    "2. bass":  ["Maxi", "Erlend", "Andreas", "Håkon Aase", "Marcus", "Jens"],
}

MINUTES = [10, 15, 20, 25, 30, 40, 45, 60, 75, 90]

PRACTICE_ITEMS = [
    "Oppvarming",
    "Stemmeøvelser",
    "Deilig er jorden",
    "O helga natt",
    "Glade jul",
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
        return pd.DataFrame(columns=["ts", "date", "voice_group", "member", "minutes", "practiced"])

    df = pd.DataFrame(entries)
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0).astype(int)
    return df

# ----------------------------
# Session state (for å skjule logg før submit)
# ----------------------------
if "show_log" not in st.session_state:
    st.session_state.show_log = False
if "last_member" not in st.session_state:
    st.session_state.last_member = None
if "last_voice_group" not in st.session_state:
    st.session_state.last_voice_group = None

# ----------------------------
# UI
# ----------------------------
issue_number = int(st.secrets["GITHUB_ISSUE_NUMBER"])

with st.form("logg", clear_on_submit=True):
    voice_group = st.selectbox("Stemmegruppe", list(VOICE_GROUPS.keys()), index=0)
    member = st.selectbox("Hvem er du?", VOICE_GROUPS[voice_group], index=0)
    minutes = st.selectbox("Hvor lenge øvde du?", MINUTES, index=MINUTES.index(30) if 30 in MINUTES else 0)

    st.write("Hva øvde du på?")
    practiced = []
    cols = st.columns(2)
    for i, opt in enumerate(PRACTICE_ITEMS):
        col = cols[i % 2]
        if col.checkbox(opt, value=False):
            practiced.append(opt)

    submit = st.form_submit_button("✅ Logg øving")

if submit:
    entry = {
        "v": 1,
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "date": dt.date.today().isoformat(),
        "voice_group": voice_group,
        "member": member,
        "minutes": int(minutes),
        "practiced": practiced,
    }

    try:
        post_issue_comment(issue_number, encode_entry_as_comment(entry))
        st.success("Logget! 🎉")
        load_log_df.clear()

        # vis logg først etter submit, og husk hvem som nettopp logget
        st.session_state.show_log = True
        st.session_state.last_member = member
        st.session_state.last_voice_group = voice_group

        st.rerun()
    except requests.HTTPError as e:
        st.error(f"Klarte ikke å lagre til GitHub (HTTP-feil). {e}")
    except Exception as e:
        st.error(f"Noe gikk galt: {e}")

# ----------------------------
# Vis kun individuell logg (kun etter submit)
# ----------------------------
if st.session_state.show_log and st.session_state.last_member:
    st.divider()
    who = f"{st.session_state.last_member} ({st.session_state.last_voice_group})"
    st.subheader(f"📒 Din øvingslogg: {who}")

    df = load_log_df(issue_number)

    # filtrer på personen som nettopp logget
    df = df[
        (df["member"] == st.session_state.last_member)
        & (df["voice_group"] == st.session_state.last_voice_group)
    ].copy()

    if df.empty:
        st.info("Fant ingen logger for deg ennå.")
    else:
        df = df.sort_values("ts", ascending=False)
        df["practiced"] = df["practiced"].apply(lambda x: ", ".join(x) if isinstance(x, list) else "")

        st.dataframe(df[["date", "minutes", "practiced"]], use_container_width=True)

        st.subheader("📊 Oppsummering")
        st.metric("Totalt minutter", int(df["minutes"].sum()))
        st.metric("Antall økter", int(len(df)))
