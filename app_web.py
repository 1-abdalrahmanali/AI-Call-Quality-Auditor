import sqlite3
import pandas as pd
import json
import os
from datetime import datetime, date, timedelta
import streamlit as st
from openai import OpenAI

# ==========================================
# 1. CONFIGURATION
# ==========================================
SERVER_GROQ_KEY = "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"
DB_FILE = "enterprise_qa.db"
BANNED_WORDS_FILE = "banned_words.json"
LOGIN_PASSWORD = "Abdalrahman2026"

st.set_page_config(page_title="Enterprise QA Console", page_icon="🎧", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 2. DATABASE
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY, name TEXT, team TEXT, email TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS calls (
                    id TEXT PRIMARY KEY, agent_id TEXT, date TEXT, duration TEXT,
                    audio_file TEXT, transcription TEXT, qa_score REAL, grammar_score REAL,
                    status TEXT, profanity_detected INTEGER,
                    FOREIGN KEY(agent_id) REFERENCES agents(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS reports (
                    call_id TEXT PRIMARY KEY, language TEXT, summary TEXT,
                    violations TEXT, grammar_feedback TEXT, manager_notes TEXT,
                    FOREIGN KEY(call_id) REFERENCES calls(id))''')
    conn.commit()
    conn.close()

init_db()

def run_query(query, params=()):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def execute_query(query, params=()):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

# ==========================================
# 3. BANNED WORDS (used by the auditor + editable in Settings)
# ==========================================
def load_banned_words():
    if os.path.exists(BANNED_WORDS_FILE):
        try:
            with open(BANNED_WORDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"english_banned": [], "spanish_banned": [], "english_offensive": [], "spanish_offensive": []}

def save_banned_words(data):
    with open(BANNED_WORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ==========================================
# 4. SMALL HELPERS
# ==========================================
def format_dt(raw, fmt="%b %d, %Y \u00b7 %I:%M %p"):
    if not raw:
        return "\u2014"
    try:
        return datetime.fromisoformat(raw).strftime(fmt)
    except Exception:
        return raw

def status_class(status):
    return {"Passed": "ok", "Warning": "warn", "Critical": "bad"}.get(status, "warn")

def status_badge(status):
    cls = status_class(status)
    return f'<span class="badge badge-{cls}">{status}</span>'

def derive_reason(violations_json, profanity_flag, summary):
    try:
        violations = json.loads(violations_json) if violations_json else []
    except Exception:
        violations = []
    if violations:
        first = violations[0]
        return first if len(violations) == 1 else f"{first} (+{len(violations) - 1} more)"
    if profanity_flag:
        return "Offensive language detected"
    if summary:
        return (summary[:90] + "\u2026") if len(summary) > 90 else summary
    return "Below quality threshold"

# ==========================================
# 5. AUTH GATE
# ==========================================
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]:
        return True

    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown('<div class="auth-card">', unsafe_allow_html=True)
        st.markdown('<div class="auth-eyebrow">ENTERPRISE QA CONSOLE</div>', unsafe_allow_html=True)
        st.markdown('<div class="auth-title">Sign in</div>', unsafe_allow_html=True)
        password_input = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="Password")
        if st.button("Sign in", use_container_width=True, type="primary"):
            if password_input == LOGIN_PASSWORD:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        st.markdown('</div>', unsafe_allow_html=True)
    return False

# ==========================================
# 6. ROUTING
# ==========================================
def go_to(page, agent_id=None, call_id=None):
    st.query_params.clear()
    st.query_params["page"] = page
    if agent_id is not None:
        st.query_params["agent_id"] = str(agent_id)
    if call_id is not None:
        st.query_params["call_id"] = str(call_id)
    st.rerun()

# ==========================================
# 7. GLOBAL STYLES
# ==========================================
LOGIN_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&display=swap');
.auth-card { background:#141b2d; border:1px solid #262f45; border-radius:14px; padding:36px 32px; }
.auth-eyebrow { font-family:'Inter',sans-serif; color:#6c7a94; font-size:11px; font-weight:600; letter-spacing:1.5px; margin-bottom:6px; }
.auth-title { font-family:'Space Grotesk',sans-serif; color:#f1f5f9; font-size:26px; font-weight:600; margin-bottom:18px; }
</style>
"""

APP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.main { background-color: #0a0e17; }
h1, h2, h3 { font-family: 'Space Grotesk', sans-serif !important; color: #f1f5f9; }

/* Top bar */
.page-eyebrow { color:#6c7a94; font-size:12px; font-weight:600; letter-spacing:1.5px; text-transform:uppercase; margin-bottom:2px; }
.page-title { font-family:'Space Grotesk',sans-serif; color:#f1f5f9; font-size:30px; font-weight:600; margin-bottom:4px; }
.page-sub { color:#8b96ab; font-size:14px; margin-bottom:22px; }

/* Search */
div[data-testid="stTextInput"] input {
    background-color:#141b2d !important; border:1px solid #262f45 !important;
    border-radius:10px !important; color:#f1f5f9 !important; padding:12px 16px !important;
}
div[data-testid="stTextInput"] input:focus {
    border-color:#6366f1 !important; box-shadow:0 0 0 3px rgba(99,102,241,0.18) !important;
}

/* Badges */
.badge { padding:4px 11px; border-radius:20px; font-size:12px; font-weight:600; white-space:nowrap; }
.badge-ok { background:rgba(52,211,153,0.14); color:#34d399; }
.badge-warn { background:rgba(251,191,36,0.14); color:#fbbf24; }
.badge-bad { background:rgba(248,113,113,0.14); color:#f87171; }

/* Section headers */
.section-title { font-family:'Space Grotesk',sans-serif; color:#f1f5f9; font-size:17px; font-weight:600; margin:6px 0 12px 0; display:flex; align-items:center; gap:8px; }
.section-count { color:#6c7a94; font-size:13px; font-weight:500; }

/* Row containers */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background-color:#111726 !important; border-color:#232c42 !important; border-radius:10px !important;
}

/* Table header row */
.tbl-head { color:#6c7a94; font-size:11px; font-weight:600; letter-spacing:0.8px; text-transform:uppercase; padding:0 4px 8px 4px; }

.agent-name-cell { color:#f1f5f9; font-weight:600; font-size:14.5px; }
.muted-cell { color:#8b96ab; font-size:13.5px; }
.score-cell { color:#f1f5f9; font-weight:600; font-size:14.5px; }

.reason-text { color:#c3cbdb; font-size:13.5px; }

.empty-state { text-align:center; padding:60px 20px; color:#6c7a94; }
.empty-state-title { font-family:'Space Grotesk',sans-serif; color:#c3cbdb; font-size:18px; font-weight:600; margin-bottom:6px; }

.divider-line { height:1px; background:#1c2438; margin:26px 0; border:none; }

.sidebar-brand { font-family:'Space Grotesk',sans-serif; color:#f1f5f9; font-size:19px; font-weight:600; margin-bottom:2px; }
.sidebar-tag { color:#6c7a94; font-size:12.5px; margin-bottom:18px; }
</style>
"""

def section_title(icon, text, count=None):
    count_html = f'<span class="section-count">&nbsp;&middot;&nbsp;{count}</span>' if count is not None else ""
    st.markdown(f'<div class="section-title">{icon} {text}{count_html}</div>', unsafe_allow_html=True)

def empty_state(title, subtitle):
    st.markdown(f'''
        <div class="empty-state">
            <div class="empty-state-title">{title}</div>
            <div>{subtitle}</div>
        </div>
    ''', unsafe_allow_html=True)

# ==========================================
# 8. SIDEBAR
# ==========================================
def render_sidebar(current_page):
    with st.sidebar:
        st.markdown('<div class="sidebar-brand">\U0001F3A7 Enterprise QA</div>', unsafe_allow_html=True)
        st.markdown('<div class="sidebar-tag">Manager Console</div>', unsafe_allow_html=True)

        if st.button("\U0001F4CB  Dashboard", use_container_width=True, key="nav_dashboard",
                     type="primary" if current_page == "dashboard" else "secondary"):
            go_to("dashboard")
        if st.button("\U0001F465  Agents", use_container_width=True, key="nav_agents",
                     type="primary" if current_page in ("agents", "agent", "call") else "secondary"):
            go_to("agents")
        if st.button("\U0001F3A4  Run AI Audit", use_container_width=True, key="nav_auditor",
                     type="primary" if current_page == "auditor" else "secondary"):
            go_to("auditor")
        if st.button("\u2699\uFE0F  Settings", use_container_width=True, key="nav_settings",
                     type="primary" if current_page == "settings" else "secondary"):
            go_to("settings")

        st.markdown('<hr class="divider-line">', unsafe_allow_html=True)
        if st.button("\U0001F512  Logout", use_container_width=True, key="nav_logout"):
            st.session_state["password_correct"] = False
            st.query_params.clear()
            st.rerun()
        st.caption("Admin: Abdalrahman Ali")

# ==========================================
# 9. DASHBOARD (workflow-first: search, filters, critical calls)
# ==========================================
def render_dashboard():
    st.markdown('<div class="page-eyebrow">OVERVIEW</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-title">Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Find an agent or call, then jump straight into the report.</div>', unsafe_allow_html=True)

    search_term = st.text_input(
        "search", label_visibility="collapsed",
        placeholder="\U0001F50E  Search by agent name, employee ID, or call ID\u2026",
        key="global_search"
    )

    if search_term.strip():
        term = f"%{search_term.strip()}%"
        agent_hits = run_query("SELECT id, name, team FROM agents WHERE name LIKE ? OR id LIKE ?", (term, term))
        call_hits = run_query(
            """SELECT c.id as call_id, c.agent_id, a.name as agent_name, c.date, c.status
               FROM calls c LEFT JOIN agents a ON c.agent_id = a.id
               WHERE c.id LIKE ? ORDER BY c.date DESC LIMIT 10""", (term,)
        )

        st.markdown("<br>", unsafe_allow_html=True)
        section_title("\U0001F50E", "Search results")

        if agent_hits.empty and call_hits.empty:
            empty_state("No matches", "Try a different name, employee ID, or call ID.")
        else:
            for _, row in agent_hits.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 2, 1.2])
                    c1.markdown(f'<div class="agent-name-cell">{row["name"]}</div>', unsafe_allow_html=True)
                    c2.markdown(f'<div class="muted-cell">Agent \u00b7 {row["id"]} \u00b7 {row["team"] or "\u2014"}</div>', unsafe_allow_html=True)
                    if c3.button("Open profile", key=f"srch_agent_{row['id']}", use_container_width=True):
                        go_to("agent", agent_id=row["id"])
            for _, row in call_hits.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 2, 1.2])
                    c1.markdown(f'<div class="agent-name-cell">{row["call_id"]}</div>', unsafe_allow_html=True)
                    c2.markdown(f'<div class="muted-cell">Call \u00b7 {row["agent_name"] or "Unknown agent"} \u00b7 {format_dt(row["date"])}</div>', unsafe_allow_html=True)
                    if c3.button("Open report", key=f"srch_call_{row['call_id']}", use_container_width=True):
                        go_to("call", call_id=row["call_id"])
        st.markdown('<hr class="divider-line">', unsafe_allow_html=True)

    # ---- Filters ----
    all_calls = run_query("""
        SELECT c.id as call_id, c.agent_id, a.name as agent_name, a.team as team,
               c.date, c.qa_score, c.status
        FROM calls c LEFT JOIN agents a ON c.agent_id = a.id
        ORDER BY c.date DESC
    """)
    teams = run_query("SELECT DISTINCT team FROM agents WHERE team IS NOT NULL AND team != ''")
    team_options = ["All teams"] + sorted(teams["team"].tolist()) if not teams.empty else ["All teams"]

    f1, f2, f3 = st.columns([2, 1.3, 2])
    with f1:
        default_start = date.today() - timedelta(days=30)
        date_range = st.date_input("Date range", value=(default_start, date.today()), key="filter_dates")
    with f2:
        team_filter = st.selectbox("Team", team_options, key="filter_team")
    with f3:
        status_filter = st.multiselect("Status", ["Critical", "Warning", "Passed"],
                                        default=["Critical", "Warning", "Passed"], key="filter_status")

    filtered = all_calls.copy()
    if not filtered.empty:
        filtered["_date_only"] = pd.to_datetime(filtered["date"], errors="coerce").dt.date
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_d, end_d = date_range
            filtered = filtered[(filtered["_date_only"] >= start_d) & (filtered["_date_only"] <= end_d)]
        if team_filter != "All teams":
            filtered = filtered[filtered["team"] == team_filter]
        if status_filter:
            filtered = filtered[filtered["status"].isin(status_filter)]

    st.markdown("<br>", unsafe_allow_html=True)
    section_title("\U0001F4CB", "Calls", count=len(filtered))

    if filtered.empty:
        if all_calls.empty:
            empty_state("No calls yet", "Run your first AI audit to start building the call log.")
        else:
            empty_state("No calls match these filters", "Try widening the date range or status filter.")
    else:
        hc1, hc2, hc3, hc4, hc5, hc6 = st.columns([2.3, 2, 1.8, 1.2, 1.3, 1.4])
        for col, label in zip([hc1, hc2, hc3, hc4, hc5], ["Agent", "Call ID", "Date", "Score", "Status"]):
            col.markdown(f'<div class="tbl-head">{label}</div>', unsafe_allow_html=True)

        for _, row in filtered.head(30).iterrows():
            with st.container(border=True):
                c1, c2, c3, c4, c5, c6 = st.columns([2.3, 2, 1.8, 1.2, 1.3, 1.4])
                c1.markdown(f'<div class="agent-name-cell">{row["agent_name"] or "Unknown"}</div>', unsafe_allow_html=True)
                c2.markdown(f'<div class="muted-cell">{row["call_id"]}</div>', unsafe_allow_html=True)
                c3.markdown(f'<div class="muted-cell">{format_dt(row["date"], "%b %d, %Y")}</div>', unsafe_allow_html=True)
                c4.markdown(f'<div class="score-cell">{row["qa_score"]}/10</div>', unsafe_allow_html=True)
                c5.markdown(status_badge(row["status"]), unsafe_allow_html=True)
                if c6.button("Open report", key=f"dash_call_{row['call_id']}", use_container_width=True):
                    go_to("call", call_id=row["call_id"])
        if len(filtered) > 30:
            st.caption(f"Showing 30 of {len(filtered)} matching calls \u2014 narrow the filters to see more precisely.")

    # ---- Critical calls (always visible, independent of filters) ----
    st.markdown('<hr class="divider-line">', unsafe_allow_html=True)
    critical_df = run_query("""
        SELECT c.id as call_id, c.qa_score, a.name as agent_name, a.id as agent_id,
               c.profanity_detected, r.summary, r.violations
        FROM calls c
        JOIN agents a ON c.agent_id = a.id
        JOIN reports r ON c.id = r.call_id
        WHERE c.status = 'Critical'
        ORDER BY c.date DESC
    """)
    section_title("\U0001F534", "Critical calls needing review", count=len(critical_df))

    if critical_df.empty:
        empty_state("Nothing critical right now", "Critical calls will show up here the moment they're flagged.")
    else:
        for _, row in critical_df.iterrows():
            reason = derive_reason(row["violations"], row["profanity_detected"], row["summary"])
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2, 1, 4, 1.6])
                c1.markdown(f'<div class="agent-name-cell">{row["agent_name"]}</div>', unsafe_allow_html=True)
                c2.markdown(f'<div class="score-cell">{row["qa_score"]}/10</div>', unsafe_allow_html=True)
                c3.markdown(f'<div class="reason-text">{reason}</div>', unsafe_allow_html=True)
                if c4.button("Open report", key=f"crit_{row['call_id']}", use_container_width=True, type="primary"):
                    go_to("call", call_id=row["call_id"])

# ==========================================
# 10. AGENTS DIRECTORY
# ==========================================
def render_agents():
    st.markdown('<div class="page-eyebrow">TEAM</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-title">Agents</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Open an agent to see their full call history.</div>', unsafe_allow_html=True)

    df = run_query("""
        SELECT a.id, a.name, a.team,
               MAX(c.date) as last_call,
               SUM(CASE WHEN c.status = 'Critical' THEN 1 ELSE 0 END) as critical_count,
               COUNT(c.id) as total_calls
        FROM agents a
        LEFT JOIN calls c ON a.id = c.agent_id
        GROUP BY a.id
        ORDER BY a.name
    """)

    if df.empty:
        empty_state("No agents yet", "Agents are added automatically the first time you audit one of their calls.")
        return

    hc1, hc2, hc3, hc4, hc5, hc6 = st.columns([2.4, 1.6, 1.8, 1.8, 1.6, 1.4])
    for col, label in zip([hc1, hc2, hc3, hc4, hc5], ["Agent", "Employee ID", "Team", "Last call", "Critical calls"]):
        col.markdown(f'<div class="tbl-head">{label}</div>', unsafe_allow_html=True)

    for _, row in df.iterrows():
        with st.container(border=True):
            c1, c2, c3, c4, c5, c6 = st.columns([2.4, 1.6, 1.8, 1.8, 1.6, 1.4])
            c1.markdown(f'<div class="agent-name-cell">{row["name"]}</div>', unsafe_allow_html=True)
            c2.markdown(f'<div class="muted-cell">{row["id"]}</div>', unsafe_allow_html=True)
            c3.markdown(f'<div class="muted-cell">{row["team"] or "\u2014"}</div>', unsafe_allow_html=True)
            c4.markdown(f'<div class="muted-cell">{format_dt(row["last_call"], "%b %d, %Y")}</div>', unsafe_allow_html=True)
            crit = int(row["critical_count"] or 0)
            crit_html = f'<span class="badge badge-bad">{crit}</span>' if crit > 0 else '<span class="muted-cell">0</span>'
            c5.markdown(crit_html, unsafe_allow_html=True)
            if c6.button("Open calls", key=f"agent_open_{row['id']}", use_container_width=True):
                go_to("agent", agent_id=row["id"])

# ==========================================
# 11. AGENT DETAILS
# ==========================================
def render_agent_detail(agent_id):
    agent_df = run_query("SELECT * FROM agents WHERE id = ?", (agent_id,))
    if agent_df.empty:
        empty_state("Agent not found", "This agent may have been removed.")
        if st.button("\u2190 Back to Agents", key="back_agents_missing"):
            go_to("agents")
        return
    agent = agent_df.iloc[0]

    if st.button("\u2190 Back to Agents", key="back_agents"):
        go_to("agents")

    st.markdown('<div class="page-eyebrow">AGENT PROFILE</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-title">{agent["name"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-sub">Employee ID {agent["id"]} \u00b7 {agent["team"] or "No team set"}</div>', unsafe_allow_html=True)

    calls_df = run_query(
        "SELECT id as call_id, date, duration, qa_score, status FROM calls WHERE agent_id = ? ORDER BY date DESC",
        (agent_id,)
    )

    section_title("\U0001F4DE", "Calls", count=len(calls_df))

    if calls_df.empty:
        empty_state("No calls audited yet", "Run an AI audit for this agent to see reports here.")
        return

    hc1, hc2, hc3, hc4, hc5, hc6 = st.columns([1.8, 1.8, 1.2, 1.2, 1.4, 1.4])
    for col, label in zip([hc1, hc2, hc3, hc4, hc5], ["Call ID", "Date", "Duration", "Score", "Status"]):
        col.markdown(f'<div class="tbl-head">{label}</div>', unsafe_allow_html=True)

    for _, row in calls_df.iterrows():
        with st.container(border=True):
            c1, c2, c3, c4, c5, c6 = st.columns([1.8, 1.8, 1.2, 1.2, 1.4, 1.4])
            c1.markdown(f'<div class="agent-name-cell">{row["call_id"]}</div>', unsafe_allow_html=True)
            c2.markdown(f'<div class="muted-cell">{format_dt(row["date"])}</div>', unsafe_allow_html=True)
            c3.markdown(f'<div class="muted-cell">{row["duration"] or "\u2014"}</div>', unsafe_allow_html=True)
            c4.markdown(f'<div class="score-cell">{row["qa_score"]}/10</div>', unsafe_allow_html=True)
            c5.markdown(status_badge(row["status"]), unsafe_allow_html=True)
            if c6.button("View report", key=f"view_call_{row['call_id']}", use_container_width=True):
                go_to("call", call_id=row["call_id"])

# ==========================================
# 12. CALL REPORT
# ==========================================
def render_call_report(call_id):
    call_df = run_query("""
        SELECT c.*, a.name as agent_name, a.id as agent_id_ref,
               r.language, r.summary, r.violations, r.grammar_feedback
        FROM calls c
        JOIN agents a ON c.agent_id = a.id
        JOIN reports r ON c.id = r.call_id
        WHERE c.id = ?
    """, (call_id,))

    if call_df.empty:
        empty_state("Report not found", "This call may have been removed.")
        if st.button("\u2190 Back to Agents", key="back_missing_call"):
            go_to("agents")
        return
    call_data = call_df.iloc[0]

    if st.button("\u2190 Back to agent", key="back_agent_from_call"):
        go_to("agent", agent_id=call_data["agent_id_ref"])

    st.markdown('<div class="page-eyebrow">CALL REPORT</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-title">{call_data["id"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-sub">{call_data["agent_name"]} \u00b7 {format_dt(call_data["date"])}</div>', unsafe_allow_html=True)

    if call_data["audio_file"] and os.path.exists(call_data["audio_file"]):
        st.audio(call_data["audio_file"])
    else:
        st.caption("Audio file no longer available on this server.")

    sc1, sc2, sc3 = st.columns(3)
    sc1.metric("QA Score", f"{call_data['qa_score']}/10")
    sc2.metric("Status", call_data["status"])
    sc3.metric("Profanity", "Yes" if call_data["profanity_detected"] else "No")

    st.markdown('<hr class="divider-line">', unsafe_allow_html=True)

    with st.expander("\U0001F4DD Executive summary", expanded=True):
        st.write(call_data["summary"])

    with st.expander("\U0001F5E3\uFE0F Speech transcription"):
        st.write(call_data["transcription"])

    with st.expander("\U0001F6A8 Compliance & violations", expanded=True):
        try:
            violations = json.loads(call_data["violations"]) if call_data["violations"] else []
        except Exception:
            violations = []
        if violations:
            for v in violations:
                st.error(f"\u2022 {v}")
        else:
            st.success("No compliance violations detected.")

    with st.expander("\u270D\uFE0F Grammar & syntax"):
        try:
            grammar = json.loads(call_data["grammar_feedback"]) if call_data["grammar_feedback"] else []
        except Exception:
            grammar = []
        if grammar:
            for idx, err in enumerate(grammar, 1):
                st.markdown(f"**Issue #{idx}**")
                st.warning(f"Spoken: {err.get('error')}")
                st.success(f"Correction: {err.get('correction')}")
                st.caption(f"Reason: {err.get('reason')}")
                st.markdown("---")
        else:
            st.success("No grammar errors detected.")

    st.download_button(
        label="\U0001F4E5 Download report (CSV)",
        data=pd.DataFrame([call_data]).to_csv(index=False),
        file_name=f"Report_{call_id}.csv",
        mime="text/csv",
    )

# ==========================================
# 13. RUN AI AUDIT
# ==========================================
def render_auditor():
    st.markdown('<div class="page-eyebrow">NEW AUDIT</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-title">Run AI Audit</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Upload a call recording to transcribe, score, and file it automatically.</div>', unsafe_allow_html=True)

    with st.form("audit_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            agent_id = st.text_input("Employee ID (required)", placeholder="e.g. EMP001")
        with col2:
            agent_name = st.text_input("Agent name", placeholder="e.g. John Doe")
        with col3:
            agent_team = st.text_input("Team / department", placeholder="e.g. Technical Support")

        uploaded_file = st.file_uploader("Upload audio recording", type=["mp3", "wav", "m4a"])
        submit_btn = st.form_submit_button("\U0001F680 Run audit", type="primary", use_container_width=True)

    if submit_btn:
        if not agent_id or not agent_name or not uploaded_file:
            st.error("Please fill in all agent details and upload an audio file.")
        else:
            with st.spinner("Whisper & Llama are analyzing the call\u2026"):
                try:
                    call_uid = f"CALL_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    audio_path = f"temp_{call_uid}.mp3"
                    with open(audio_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    client = OpenAI(api_key=SERVER_GROQ_KEY, base_url="https://api.groq.com/openai/v1")
                    banned_rules = load_banned_words()

                    with open(audio_path, "rb") as audio_file:
                        transcript_response = client.audio.transcriptions.create(model="whisper-large-v3", file=audio_file)
                    transcript_text = transcript_response.text

                    prompt = f"""
                    You are a strict Enterprise Quality Assurance Auditor.
                    Transcript: "{transcript_text}"
                    Reference Lists: Banned: {banned_rules.get('english_banned', [])}, Offensive: {banned_rules.get('english_offensive', [])}
                    Tasks:
                    1. Detect language.
                    2. Check for banned/offensive words exactly. Set has_profanity.
                    3. Check STRICT GRAMMAR ERRORS ONLY. Ignore style/politeness.
                    4. Write an executive summary.
                    Return EXACT JSON:
                    {{"language": "English/Spanish", "has_profanity": true/false, "offensive_words_found": [], "banned_words_found": [], "grammar_errors": [{{"error": "str", "correction": "str", "reason": "str"}}], "audit_summary": "str"}}
                    """

                    response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        response_format={"type": "json_object"},
                        messages=[{"role": "user", "content": prompt}]
                    )
                    result = json.loads(response.choices[0].message.content)

                    base_score = 10.0
                    all_violations = result.get("offensive_words_found", []) + result.get("banned_words_found", [])
                    grammar_errs = result.get("grammar_errors", [])

                    base_score -= (len(result.get("offensive_words_found", [])) * 2.0)
                    base_score -= (len(result.get("banned_words_found", [])) * 1.0)
                    base_score -= min(len(grammar_errs) * 0.25, 2.0)
                    final_score = round(max(0.0, min(10.0, base_score)), 2)

                    status = "Passed" if final_score >= 8 else ("Warning" if final_score >= 5 else "Critical")
                    profanity_flag = 1 if result.get("has_profanity") else 0

                    execute_query("INSERT OR IGNORE INTO agents (id, name, team, email) VALUES (?, ?, ?, ?)",
                                  (agent_id, agent_name, agent_team, f"{agent_id}@company.com"))

                    execute_query("""INSERT INTO calls (id, agent_id, date, duration, audio_file, transcription, qa_score, grammar_score, status, profanity_detected)
                                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                  (call_uid, agent_id, str(datetime.now()), "N/A", audio_path, transcript_text, final_score, 0, status, profanity_flag))

                    execute_query("""INSERT INTO reports (call_id, language, summary, violations, grammar_feedback, manager_notes)
                                     VALUES (?, ?, ?, ?, ?, ?)""",
                                  (call_uid, result.get("language"), result.get("audit_summary"), json.dumps(all_violations), json.dumps(grammar_errs), ""))

                    go_to("call", call_id=call_uid)

                except Exception as e:
                    st.error(f"Core system error: {e}")

# ==========================================
# 14. SETTINGS (compliance word lists)
# ==========================================
def render_settings():
    st.markdown('<div class="page-eyebrow">CONFIGURATION</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-title">Settings</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Manage the compliance word lists used during audits.</div>', unsafe_allow_html=True)

    data = load_banned_words()

    col_en, col_es = st.columns(2)
    with col_en:
        st.markdown("**English**")
        en_banned = st.text_area("Banned phrases", value="\n".join(data.get("english_banned", [])), height=140, key="en_banned")
        en_offensive = st.text_area("Offensive words", value="\n".join(data.get("english_offensive", [])), height=140, key="en_offensive")
    with col_es:
        st.markdown("**Spanish**")
        es_banned = st.text_area("Banned phrases ", value="\n".join(data.get("spanish_banned", [])), height=140, key="es_banned")
        es_offensive = st.text_area("Offensive words ", value="\n".join(data.get("spanish_offensive", [])), height=140, key="es_offensive")

    st.caption("One entry per line. Changes apply to audits run after saving \u2014 past reports aren't recalculated.")

    if st.button("Save changes", type="primary", key="save_settings"):
        new_data = {
            "english_banned": [w.strip() for w in en_banned.split("\n") if w.strip()],
            "english_offensive": [w.strip() for w in en_offensive.split("\n") if w.strip()],
            "spanish_banned": [w.strip() for w in es_banned.split("\n") if w.strip()],
            "spanish_offensive": [w.strip() for w in es_offensive.split("\n") if w.strip()],
        }
        save_banned_words(new_data)
        st.success("Settings saved.")

# ==========================================
# 15. MAIN
# ==========================================
if not check_password():
    st.stop()

st.markdown(APP_CSS, unsafe_allow_html=True)

_params = st.query_params
current_page = _params.get("page", "dashboard")
current_agent_id = _params.get("agent_id")
current_call_id = _params.get("call_id")

render_sidebar(current_page)

if current_page == "dashboard":
    render_dashboard()
elif current_page == "agents":
    render_agents()
elif current_page == "agent" and current_agent_id:
    render_agent_detail(current_agent_id)
elif current_page == "call" and current_call_id:
    render_call_report(current_call_id)
elif current_page == "auditor":
    render_auditor()
elif current_page == "settings":
    render_settings()
else:
    render_dashboard()
    
