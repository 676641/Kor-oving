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
MEMBERS = [
    "Sopran 1 – Anna", "Sopran 2 – Kari",
    "Alt 1 – Ida", "Alt 2 – Mari",
    "Tenor – Per", "Bass – Ola",
]
MINUTES = [10, 15, 20, 25, 30, 40, 45, 60, 75, 90]

# Dette er nå "Hva øvde du på?" (checkboxes)
PRACTICE_ITEMS = [
    "Oppvarming",
    "Stemmeøvelser",
    # Eksempelsanger (foreløpig)
    "Deilig er jorden",
    "O helga natt",
    "Glade jul",
]

# JSON markør i kommentar for enkel parsing
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
            entry = json.loads(raw)
            entries.append(entry)
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

# ----------------------------
# UI
# ----------------------------
issue_number = int(st.secrets["GITHUB_ISSUE_NUMBER"])

with st.form("logg", clear_on_submit=True):
    member = st.selectbox("Hvem er du?", MEMBERS, index=0)
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
        "member": member,
        "minutes": int(minutes),
        "practiced": practiced,   # <— her ligger alt som ble huket av
    }

    try:
        comment_body = encode_entry_as_comment(entry)
        post_issue_comment(issue_number, comment_body)
        st.success("Logget! 🎉")
        load_log_df.clear()
        st.rerun()
    except requests.HTTPError as e:
        st.error(f"Klarte ikke å lagre til GitHub (HTTP-feil). {e}")
    except Exception as e:
        st.error(f"Noe gikk galt: {e}")

st.divider()

# ----------------------------
# Visning + leaderboard
# ----------------------------
df = load_log_df(issue_number)

if df.empty:
    st.info("Ingen øvinger logget ennå.")
else:
    st.subheader("📒 Siste logger")
    show = df.sort_values("ts", ascending=False).copy()
    show["practiced"] = show["practiced"].apply(lambda x: ", ".join(x) if isinstance(x, list) else "")
    st.dataframe(show[["date", "member", "minutes", "practiced"]], use_container_width=True)

    st.subheader("🏆 Leaderboard")
    per_person = df.groupby("member", as_index=False)["minutes"].sum().sort_values("minutes", ascending=False)
    st.dataframe(per_person, use_container_width=True)

    st.subheader("📊 Totalt")
    st.metric("Totale minutter", int(df["minutes"].sum()))
    st.metric("Antall økter", int(len(df)))
