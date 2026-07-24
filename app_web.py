"""
QA Operations Console
----------------------------------------------------------------------
Workflow-first dashboard for QA managers and team leads: find an agent,
open their calls, review AI-generated audit reports. No analytics/chart
widgets by design — the job of this page is navigation, not reporting.

Routing note: Streamlit has no built-in path-based routing (no real
/agent/{id} URLs). This app approximates it with query-string state
(?view=AgentDetails&agent_id=...), which is bookmarkable/shareable in
a browser, but will show as localhost:8501/?view=... rather than a
clean /agent/... path. True path routing would need Streamlit's
multipage-app file structure or a third-party router package.
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from openai import OpenAI

# ==========================================
# 1. CONFIGURATION & SETUP
# ==========================================
try:
    SERVER_GROQ_KEY = st.secrets.get("GROQ_API_KEY", "")
except Exception:
    SERVER_GROQ_KEY = ""
SERVER_GROQ_KEY = SERVER_GROQ_KEY or os.environ.get("GROQ_API_KEY", "")

DB_FILE = "enterprise_qa.db"
BANNED_WORDS_FILE = "banned_words.json"

st.set_page_config(
    page_title="QA Operations Console",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==========================================
# 2. DATABASE HELPERS
# ==========================================
def get_conn():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY, name TEXT, team TEXT, email TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS calls (
                    id TEXT PRIMARY KEY, agent_id TEXT, date TEXT, duration TEXT,
                    audio_file TEXT, transcription TEXT, qa_score REAL, grammar_score REAL,
                    status TEXT, profanity_detected INTEGER,
                    FOREIGN KEY(agent_id) REFERENCES agents(id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS reports (
                    call_id TEXT PRIMARY KEY, language TEXT, summary TEXT,
                    violations TEXT, grammar_feedback TEXT, manager_notes TEXT,
                    FOREIGN KEY(call_id) REFERENCES calls(id))""")
    conn.commit()
    conn.close()


init_db()


def run_query(query, params=()):
    conn = get_conn()
    try:
        return pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()


def execute_query(query, params=()):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(query, params)
        conn.commit()
    finally:
        conn.close()


def load_banned_rules():
    if os.path.exists(BANNED_WORDS_FILE):
        with open(BANNED_WORDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "english_banned": ["not my problem", "I don't care", "whatever"],
        "spanish_banned": [],
        "english_offensive": ["idiot", "stupid"],
        "spanish_offensive": [],
    }


def save_banned_rules(rules):
    with open(BANNED_WORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2, ensure_ascii=False)


# ==========================================
# 3. STYLING
# ==========================================
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; }
    .main { background-color: #0A0D12; }
    section[data-testid="stSidebar"] { background-color: #0D1117; border-right: 1px solid #1D232E; }
    h1, h2, h3, h4 { letter-spacing: -0.01em; }

    /* Identifier chips — the one visual motif used for every Call ID / Employee ID */
    .id-chip {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 12px;
        color: #9AA5B8;
        background: #171C25;
        border: 1px solid #262D3A;
        padding: 2px 8px;
        border-radius: 5px;
        letter-spacing: 0.02em;
        display: inline-block;
    }

    /* Status badges */
    .status-badge {
        display: inline-block;
        font-size: 12px;
        font-weight: 600;
        padding: 3px 10px;
        border-radius: 999px;
        letter-spacing: 0.01em;
        white-space: nowrap;
    }
    .badge-passed   { background: rgba(63, 182, 139, 0.15); color: #3FB68B; border: 1px solid rgba(63,182,139,0.35); }
    .badge-warning  { background: rgba(224, 167, 62, 0.15); color: #E0A73E; border: 1px solid rgba(224,167,62,0.35); }
    .badge-critical { background: rgba(229, 72, 77, 0.15);  color: #E5484D; border: 1px solid rgba(229,72,77,0.35); }

    .critical-alert-card {
        background: rgba(229, 72, 77, 0.06);
        border: 1px solid rgba(229, 72, 77, 0.35);
        border-left: 3px solid #E5484D;
        border-radius: 8px;
        padding: 14px 16px;
        margin-bottom: 8px;
    }

    .col-header { color: #8A94A6; font-size: 11px; font-weight: 600; letter-spacing: 0.04em; }
    .row-divider { margin: 4px 0 10px; border: none; border-top: 1px solid #1D232E; }

    .audit-row-ok, .audit-row-err {
        padding: 6px 10px; border-radius: 6px; font-size: 13px; margin-bottom: 4px;
    }
    .audit-row-ok { background: rgba(63,182,139,0.08); }
    .audit-row-err { background: rgba(229,72,77,0.08); color: #E5484D; }

    [data-testid="stMetric"] { background-color: #12161D; border: 1px solid #232935; padding: 14px 16px; border-radius: 10px; }
    [data-testid="stMetricLabel"] { color: #8A94A6; }
    [data-testid="stMetricValue"] { color: #EAEDF3; }

    div.stButton > button { border-radius: 7px; font-weight: 500; }
    </style>
""", unsafe_allow_html=True)


def status_badge(status):
    styles = {
        "Passed": ("badge-passed", "🟢"),
        "Warning": ("badge-warning", "🟡"),
        "Critical": ("badge-critical", "🔴"),
    }
    cls, emoji = styles.get(status, ("badge-warning", "⚪"))
    return f"<span class='status-badge {cls}'>{emoji} {status}</span>"


def id_chip(value):
    return f"<span class='id-chip'>{value}</span>"


# ==========================================
# 4. ROUTER / STATE MANAGEMENT
# ==========================================
def sync_query_params(params):
    """Best-effort URL sync. Safe no-op on Streamlit versions without st.query_params."""
    try:
        st.query_params.clear()
        st.query_params.update(params)
    except Exception:
        pass


def read_query_params():
    try:
        return dict(st.query_params)
    except Exception:
        return {}


_qp = read_query_params()
if "current_view" not in st.session_state:
    st.session_state.current_view = _qp.get("view", "Dashboard")
if "selected_agent" not in st.session_state:
    st.session_state.selected_agent = _qp.get("agent_id")
if "selected_call" not in st.session_state:
    st.session_state.selected_call = _qp.get("call_id")
if "previous_view" not in st.session_state:
    st.session_state.previous_view = None
if "last_audited_calls" not in st.session_state:
    st.session_state.last_audited_calls = None


def navigate_to(view, agent_id=None, call_id=None):
    if view == "CallReport":
        st.session_state.previous_view = st.session_state.current_view
    st.session_state.current_view = view
    if agent_id is not None:
        st.session_state.selected_agent = agent_id
    if call_id is not None:
        st.session_state.selected_call = call_id

    params = {"view": view}
    if view == "AgentDetails" and st.session_state.selected_agent:
        params["agent_id"] = st.session_state.selected_agent
    if view == "CallReport" and st.session_state.selected_call:
        params["call_id"] = st.session_state.selected_call
    sync_query_params(params)


def active_nav_key():
    cv = st.session_state.current_view
    if cv == "AgentDetails":
        return "Agents"
    if cv == "CallReport":
        prev = st.session_state.get("previous_view")
        return "Agents" if prev == "AgentDetails" else ("Auditor" if prev == "Auditor" else "Dashboard")
    return cv


# ==========================================
# 5. SIDEBAR NAVIGATION
# ==========================================
with st.sidebar:
    st.markdown("### 🛡️ QA Operations")
    st.caption("Enterprise Console")
    st.divider()

    nav_items = [
        ("Dashboard", "📊 Dashboard"),
        ("Agents", "👥 Agents"),
        ("Auditor", "🎙️ Run AI Audit"),
        ("Settings", "⚙️ Settings"),
    ]
    active_key = active_nav_key()
    for view_key, label in nav_items:
        if st.button(label, use_container_width=True,
                     type="primary" if active_key == view_key else "secondary",
                     key=f"nav_{view_key}"):
            navigate_to(view_key)
            st.rerun()

    st.divider()
    if st.button("🚪 Logout", use_container_width=True):
        for key in ("current_view", "selected_agent", "selected_call", "previous_view", "last_audited_calls"):
            st.session_state.pop(key, None)
        sync_query_params({})
        st.rerun()


# ==========================================
# 6. VIEW: DASHBOARD
# ==========================================
def view_dashboard():
    st.title(" QA Operations")
    st.caption("Find an agent, open their calls, and review AI-generated reports.")

    st.markdown("##### 🔎 Search")
    search_query = st.text_input(
        "Search", placeholder="Agent name, employee ID, or call ID",
        label_visibility="collapsed",
    )

    st.markdown("##### Filters")
    fc1, fc2, fc3, fc4, fc5 = st.columns([1.6, 2, 1, 1, 1])
    teams = ["All Teams"] + sorted(
        [t for t in run_query("SELECT DISTINCT team FROM agents")["team"].dropna().tolist() if t]
    )
    with fc1:
        team_filter = st.selectbox("Team", teams)
    with fc2:
        today = datetime.now().date()
        date_range = st.date_input("Date range", value=(today - timedelta(days=365), today))
    with fc3:
        critical_only = st.checkbox("🔴 Critical only")
    with fc4:
        show_passed = st.checkbox("🟢 Passed")
    with fc5:
        show_failed = st.checkbox("🟡 Failed")

    # "Failed" bundles Warning + Critical statuses; Critical-only overrides the rest.
    status_list = None
    if critical_only:
        status_list = ["Critical"]
    else:
        chosen = []
        if show_passed:
            chosen.append("Passed")
        if show_failed:
            chosen += ["Warning", "Critical"]
        if chosen:
            status_list = list(dict.fromkeys(chosen))

    start_date = end_date = None
    if isinstance(date_range, (list, tuple)):
        if len(date_range) == 2:
            start_date, end_date = date_range
        elif len(date_range) == 1:
            start_date = end_date = date_range[0]
    elif date_range:
        start_date = end_date = date_range

    query = """
        SELECT c.id as call_id, a.name as agent_name, a.id as employee_id,
               c.date, c.duration, c.qa_score, c.status
        FROM calls c JOIN agents a ON c.agent_id = a.id
        WHERE 1=1
    """
    params = []
    if search_query:
        like = f"%{search_query}%"
        query += " AND (a.name LIKE ? OR a.id LIKE ? OR c.id LIKE ?)"
        params += [like, like, like]
    if team_filter != "All Teams":
        query += " AND a.team = ?"
        params.append(team_filter)
    if status_list:
        query += f" AND c.status IN ({','.join(['?'] * len(status_list))})"
        params += status_list
    if start_date:
        query += " AND substr(c.date, 1, 10) >= ?"
        params.append(start_date.isoformat())
    if end_date:
        query += " AND substr(c.date, 1, 10) <= ?"
        params.append(end_date.isoformat())
    query += " ORDER BY c.date DESC LIMIT 25"
    df_calls = run_query(query, tuple(params))

    st.markdown("#### 📋 Calls")
    if df_calls.empty:
        st.info("No calls match your search and filters.")
    else:
        col_widths = [2.2, 1.5, 1.3, 1.0, 1.0, 1.3, 1.2]
        headers = ["Agent", "Call ID", "Date", "Duration", "Score", "Status", ""]
        header_cols = st.columns(col_widths)
        for col, label in zip(header_cols, headers):
            if label:
                col.markdown(f"<span class='col-header'>{label.upper()}</span>", unsafe_allow_html=True)

        for _, row in df_calls.iterrows():
            cols = st.columns(col_widths)
            cols[0].markdown(f"**{row['agent_name']}**<br>{id_chip(row['employee_id'])}", unsafe_allow_html=True)
            cols[1].markdown(id_chip(row['call_id']), unsafe_allow_html=True)
            cols[2].write(str(row['date'])[:16])
            cols[3].write(row['duration'] or "—")
            cols[4].write(f"{row['qa_score']}/10")
            cols[5].markdown(status_badge(row['status']), unsafe_allow_html=True)
            if cols[6].button("Open →", key=f"open_call_{row['call_id']}", use_container_width=True):
                navigate_to("CallReport", call_id=row['call_id'])
                st.rerun()
            st.markdown("<hr class='row-divider'>", unsafe_allow_html=True)

    st.markdown("#### 🚨 Critical Calls")
    crit_query = """
        SELECT c.id as call_id, a.name as agent_name, c.qa_score, r.summary
        FROM calls c
        JOIN agents a ON c.agent_id = a.id
        JOIN reports r ON c.id = r.call_id
        WHERE c.status = 'Critical'
    """
    crit_params = []
    if team_filter != "All Teams":
        crit_query += " AND a.team = ?"
        crit_params.append(team_filter)
    if start_date:
        crit_query += " AND substr(c.date, 1, 10) >= ?"
        crit_params.append(start_date.isoformat())
    if end_date:
        crit_query += " AND substr(c.date, 1, 10) <= ?"
        crit_params.append(end_date.isoformat())
    crit_query += " ORDER BY c.date DESC LIMIT 10"
    df_critical = run_query(crit_query, tuple(crit_params))

    if df_critical.empty:
        st.success("No critical calls right now.")
    else:
        for _, row in df_critical.iterrows():
            reason = (row['summary'] or "No summary available.").strip()
            if len(reason) > 160:
                reason = reason[:160].rstrip() + "…"
            st.markdown(f"""
                <div class="critical-alert-card">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
                        <div>
                            <div style="font-weight:600;color:#EAEDF3;">{row['agent_name']}</div>
                            <div style="color:#8A94A6;font-size:13px;margin-top:2px;">{reason}</div>
                        </div>
                        <div class="status-badge badge-critical">{row['qa_score']}/10</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            if st.button("Open Report →", key=f"crit_open_{row['call_id']}"):
                navigate_to("CallReport", call_id=row['call_id'])
                st.rerun()


# ==========================================
# 7. VIEW: AGENTS
# ==========================================
def view_agents():
    st.title("👥 Agents")
    st.caption("Find an agent, then open their calls.")

    search = st.text_input("Search agents", placeholder="Search by agent name or employee ID",
                            label_visibility="collapsed")

    query = """
        SELECT a.id, a.name, a.team,
               MAX(c.date) as last_call,
               SUM(CASE WHEN c.status = 'Critical' THEN 1 ELSE 0 END) as critical_count
        FROM agents a
        LEFT JOIN calls c ON a.id = c.agent_id
    """
    params = []
    if search:
        like = f"%{search}%"
        query += " WHERE a.name LIKE ? OR a.id LIKE ?"
        params = [like, like]
    query += " GROUP BY a.id ORDER BY a.name"
    df_agents = run_query(query, tuple(params))

    if df_agents.empty:
        st.info("No agents yet. Agents are added automatically the first time you run an AI audit for them.")
        return

    col_widths = [2.2, 1.6, 1.6, 1.6, 1.4, 1.3]
    headers = ["Agent Name", "Employee ID", "Team", "Last Call", "Critical Calls", ""]
    header_cols = st.columns(col_widths)
    for col, label in zip(header_cols, headers):
        if label:
            col.markdown(f"<span class='col-header'>{label.upper()}</span>", unsafe_allow_html=True)

    for _, ag in df_agents.iterrows():
        crit = int(ag['critical_count'] or 0)
        last_call = str(ag['last_call'])[:16] if ag['last_call'] else "No calls yet"
        crit_html = (f"<span class='status-badge badge-critical'>{crit}</span>" if crit > 0
                     else "<span class='status-badge badge-passed'>0</span>")

        cols = st.columns(col_widths)
        cols[0].markdown(f"**{ag['name']}**")
        cols[1].markdown(id_chip(ag['id']), unsafe_allow_html=True)
        cols[2].write(ag['team'] or "—")
        cols[3].write(last_call)
        cols[4].markdown(crit_html, unsafe_allow_html=True)
        if cols[5].button("Open Calls →", key=f"open_agent_{ag['id']}", use_container_width=True):
            navigate_to("AgentDetails", agent_id=ag['id'])
            st.rerun()
        st.markdown("<hr class='row-divider'>", unsafe_allow_html=True)


# ==========================================
# 8. VIEW: AGENT DETAILS
# ==========================================
def view_agent_details():
    agent_id = st.session_state.selected_agent
    if not agent_id:
        st.warning("No agent selected.")
        if st.button("← Back to Agents"):
            navigate_to("Agents")
            st.rerun()
        return

    agent_df = run_query("SELECT * FROM agents WHERE id = ?", (agent_id,))
    if agent_df.empty:
        st.error("This agent no longer exists.")
        if st.button("← Back to Agents"):
            navigate_to("Agents")
            st.rerun()
        return
    agent_info = agent_df.iloc[0]

    if st.button("← Back to Agents"):
        navigate_to("Agents")
        st.rerun()

    st.title(f"👤 {agent_info['name']}")
    st.markdown(id_chip(agent_info['id']), unsafe_allow_html=True)
    st.caption(f"Team: {agent_info['team'] or '—'}  ·  {agent_info['email'] or 'No email on file'}")

    st.markdown("#### 📞 Call History")
    df_calls = run_query(
        "SELECT id as call_id, date, duration, qa_score, status FROM calls WHERE agent_id = ? ORDER BY date DESC",
        (agent_id,),
    )

    if df_calls.empty:
        st.info("No calls recorded for this agent yet.")
        return

    col_widths = [1.8, 1.6, 1.1, 1.0, 1.3, 1.3]
    headers = ["Call ID", "Date", "Duration", "QA Score", "Status", ""]
    header_cols = st.columns(col_widths)
    for col, label in zip(header_cols, headers):
        if label:
            col.markdown(f"<span class='col-header'>{label.upper()}</span>", unsafe_allow_html=True)

    for _, call in df_calls.iterrows():
        cols = st.columns(col_widths)
        cols[0].markdown(id_chip(call['call_id']), unsafe_allow_html=True)
        cols[1].write(str(call['date'])[:16])
        cols[2].write(call['duration'] or "—")
        cols[3].write(f"{call['qa_score']}/10")
        cols[4].markdown(status_badge(call['status']), unsafe_allow_html=True)
        if cols[5].button("View Report →", key=f"view_call_{call['call_id']}", use_container_width=True):
            navigate_to("CallReport", call_id=call['call_id'])
            st.rerun()
        st.markdown("<hr class='row-divider'>", unsafe_allow_html=True)


# ==========================================
# 9. VIEW: CALL REPORT
# ==========================================
def view_call_report():
    call_id = st.session_state.selected_call
    back_target = st.session_state.get("previous_view") or "Dashboard"

    if not call_id:
        st.warning("No call selected.")
        if st.button("← Back"):
            navigate_to(back_target)
            st.rerun()
        return

    df = run_query("""
        SELECT c.*, a.name as agent_name, a.id as employee_id, a.team,
               r.language, r.summary, r.violations, r.grammar_feedback, r.manager_notes
        FROM calls c
        JOIN agents a ON c.agent_id = a.id
        JOIN reports r ON c.id = r.call_id
        WHERE c.id = ?
    """, (call_id,))

    if df.empty:
        st.error("This report could not be found.")
        if st.button("← Back"):
            navigate_to(back_target)
            st.rerun()
        return

    call_data = df.iloc[0]

    if st.button("← Back"):
        navigate_to(back_target)
        st.rerun()

    st.title("📄 Call Report")
    st.markdown(id_chip(call_id), unsafe_allow_html=True)
    st.caption(f"Agent: {call_data['agent_name']} ({call_data['employee_id']})  ·  Audited: {str(call_data['date'])[:16]}")

    hc1, hc2, hc3 = st.columns(3)
    hc1.metric("QA Score", f"{call_data['qa_score']}/10")
    with hc2:
        st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
        st.markdown(status_badge(call_data['status']), unsafe_allow_html=True)
    hc3.metric("Profanity", "Flagged ⚠️" if call_data['profanity_detected'] else "Clean ✅")

    st.divider()

    with st.expander("🔊 Audio Record Player", expanded=True):
        if call_data['audio_file'] and os.path.exists(str(call_data['audio_file'])):
            st.audio(call_data['audio_file'])
        else:
            st.info("Audio file archived or unavailable locally.")

    with st.expander("📝 Executive Summary", expanded=True):
        st.info(call_data['summary'] or "No summary available.")

    with st.expander("🗣️ Speech Transcription"):
        st.write(call_data['transcription'])

    with st.expander("🚨 Detected Violations & Compliance", expanded=True):
        try:
            violations = json.loads(call_data['violations'])
        except (TypeError, ValueError):
            violations = None
        if violations:
            for v in violations:
                st.error(f"• {v}")
        else:
            st.success("No compliance violations detected.")

    with st.expander("✍️ Grammar Analysis"):
        try:
            grammar = json.loads(call_data['grammar_feedback'])
        except (TypeError, ValueError):
            grammar = None
        if grammar:
            for err in grammar:
                st.warning(f"Spoken: {err.get('error')} ➔ Corrected: {err.get('correction')}")
                st.caption(f"Reason: {err.get('reason')}")
        else:
            st.success("Perfect grammar!")

    with st.expander("💡 Manager Notes"):
        st.markdown(f"**Notes:** {call_data['manager_notes'] or 'No manual notes added yet.'}")

    st.download_button(
        label="📥 Export Report Data (CSV)",
        data=pd.DataFrame([call_data]).to_csv(index=False),
        file_name=f"Report_{call_id}.csv",
        mime="text/csv",
    )


# ==========================================
# 10. VIEW: RUN AI AUDIT (multi-file)
# ==========================================
def view_auditor():
    st.title("🎙️ Run AI Audit")
    st.markdown("Upload one or more customer service recordings for immediate AI evaluation.")

    with st.form("audit_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            agent_id = st.text_input("🆔 Employee ID", placeholder="EMP001")
        with c2:
            agent_name = st.text_input("👨‍💼 Agent Name", placeholder="John Doe")
        with c3:
            agent_team = st.text_input("🏢 Team/Department", placeholder="Tech Support")

        uploaded_files = st.file_uploader(
            "📂 Upload Audio Records (multiple allowed)",
            type=["mp3", "wav", "m4a"],
            accept_multiple_files=True,
        )
        submit_btn = st.form_submit_button("🚀 Run AI Audit", type="primary")

    if submit_btn:
        if not agent_id or not agent_name or not uploaded_files:
            st.error("⚠️ Please fill in all agent details and upload at least one audio file.")
        elif not SERVER_GROQ_KEY:
            st.error("⚠️ No Groq API key configured. Add GROQ_API_KEY in Settings → Secrets (Streamlit Cloud) "
                      "or in .streamlit/secrets.toml locally.")
        else:
            client = OpenAI(api_key=SERVER_GROQ_KEY, base_url="https://api.groq.com/openai/v1")
            banned_rules = load_banned_rules()

            # Register the agent once — not once per file.
            execute_query(
                "INSERT OR IGNORE INTO agents (id, name, team, email) VALUES (?, ?, ?, ?)",
                (agent_id, agent_name, agent_team, f"{agent_id}@company.com"),
            )

            total_files = len(uploaded_files)
            progress_bar = st.progress(0.0)
            status_area = st.container()
            new_calls = []
            success_count = 0

            for index, uploaded_file in enumerate(uploaded_files):
                try:
                    call_uid = f"CALL_{datetime.now().strftime('%Y%m%d%H%M%S')}_{index}"
                    ext = os.path.splitext(uploaded_file.name)[1] or ".mp3"
                    audio_path = f"temp_{call_uid}{ext}"
                    with open(audio_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    with open(audio_path, "rb") as audio_file:
                        transcript_response = client.audio.transcriptions.create(
                            model="whisper-large-v3", file=audio_file
                        )
                    transcript_text = transcript_response.text

                    prompt = f"""
                    You are a strict Senior Quality Assurance Auditor. Your job is NOT to coach on politeness or style, but to find STRICT GRAMMATICAL ERRORS ONLY.

                    Transcript: "{transcript_text}"

                    Reference Lists:
                    - English Banned Phrases: {banned_rules.get('english_banned', [])}
                    - Spanish Banned Phrases: {banned_rules.get('spanish_banned', [])}
                    - English Offensive Words: {banned_rules.get('english_offensive', [])}
                    - Spanish Offensive Words: {banned_rules.get('spanish_offensive', [])}

                    Tasks to execute:
                    1. Detect primary spoken language (English or Spanish).
                    2. Check if the agent used ANY exact phrase from the Banned lists above. List them in `banned_words_found`. Set `has_profanity` to true if offensive words are found.
                    3. Check if the agent used ANY exact word from the Offensive lists above. List them in `offensive_words_found`.
                    4. Check for GRAMMAR ERRORS ONLY.
                       - STRICT RULE: Do NOT flag sentences just because they lack politeness, or because you want a "better phrasing" (e.g., "Sorry for bothering" or "When did you leave?" are grammatically correct and MUST NOT be flagged).
                       - Only flag undeniable grammar, tense, or syntax structural breakages (e.g., "He go" instead of "He goes").
                       - If there are no true grammar errors, return an empty list [].
                    5. Write a short executive audit summary paragraph.

                    Return ONLY a valid JSON object matching this structure precisely:
                    {{
                      "language": "English/Spanish",
                      "has_profanity": true/false,
                      "offensive_words_found": [],
                      "banned_words_found": [],
                      "grammar_errors": [
                        {{"error": "string", "correction": "string", "reason": "string"}}
                      ],
                      "audit_summary": "string summary paragraph"
                    }}
                    """

                    response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        response_format={"type": "json_object"},
                        messages=[{"role": "user", "content": prompt}],
                    )
                    result = json.loads(response.choices[0].message.content)

                    all_violations = result.get("offensive_words_found", []) + result.get("banned_words_found", [])
                    grammar_errs = result.get("grammar_errors", [])

                    base_score = 10.0
                    base_score -= (len(result.get("offensive_words_found", [])) * 2.0)
                    base_score -= (len(result.get("banned_words_found", [])) * 1.0)
                    base_score -= min(len(grammar_errs) * 0.25, 2.0)
                    final_score = round(max(0.0, min(10.0, base_score)), 2)

                    call_status = "Passed" if final_score >= 8 else ("Warning" if final_score >= 5 else "Critical")
                    profanity_flag = 1 if result.get("has_profanity") else 0

                    execute_query(
                        """INSERT INTO calls (id, agent_id, date, duration, audio_file, transcription,
                                               qa_score, grammar_score, status, profanity_detected)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (call_uid, agent_id, str(datetime.now()), "N/A", audio_path, transcript_text,
                         final_score, 0, call_status, profanity_flag),
                    )
                    execute_query(
                        """INSERT INTO reports (call_id, language, summary, violations, grammar_feedback, manager_notes)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (call_uid, result.get("language"), result.get("audit_summary"),
                         json.dumps(all_violations), json.dumps(grammar_errs), ""),
                    )

                    new_calls.append((call_uid, uploaded_file.name, final_score, call_status))
                    success_count += 1
                    status_area.markdown(
                        f"<div class='audit-row-ok'>✅ <b>{uploaded_file.name}</b> — {final_score}/10 "
                        f"{status_badge(call_status)}</div>",
                        unsafe_allow_html=True,
                    )
                except Exception as e:
                    status_area.markdown(
                        f"<div class='audit-row-err'>❌ <b>{uploaded_file.name}</b> — {e}</div>",
                        unsafe_allow_html=True,
                    )

                progress_bar.progress((index + 1) / total_files)

            st.success(f"🎉 Audited {success_count} of {total_files} call(s) for {agent_name}.")
            if new_calls:
                st.session_state.last_audited_calls = new_calls

    if st.session_state.get("last_audited_calls"):
        st.markdown("#### ✅ Just Audited")
        for call_uid, fname, score, call_status in st.session_state.last_audited_calls:
            rc = st.columns([3, 1.2, 1.3, 1.5])
            rc[0].write(fname)
            rc[1].write(f"{score}/10")
            rc[2].markdown(status_badge(call_status), unsafe_allow_html=True)
            if rc[3].button("View Report →", key=f"view_new_{call_uid}", use_container_width=True):
                navigate_to("CallReport", call_id=call_uid)
                st.session_state.last_audited_calls = None
                st.rerun()


# ==========================================
# 11. VIEW: SETTINGS
# ==========================================
def view_settings():
    st.title("⚙️ Settings")
    st.caption("Configure the words and phrases the AI auditor checks for.")

    rules = load_banned_rules()

    st.markdown("#### 🚫 Banned Phrases")
    st.caption("Exact phrases agents should never say (e.g. dismissive language). One per line.")
    banned_en = st.text_area("English banned phrases", value="\n".join(rules.get("english_banned", [])), height=140)
    banned_es = st.text_area("Spanish banned phrases", value="\n".join(rules.get("spanish_banned", [])), height=100)

    st.markdown("#### 🤬 Offensive Words")
    st.caption("Individual words that should always be flagged as profanity. One per line.")
    off_en = st.text_area("English offensive words", value="\n".join(rules.get("english_offensive", [])), height=100)
    off_es = st.text_area("Spanish offensive words", value="\n".join(rules.get("spanish_offensive", [])), height=100)

    if st.button("💾 Save Changes", type="primary"):
        save_banned_rules({
            "english_banned": [w.strip() for w in banned_en.splitlines() if w.strip()],
            "spanish_banned": [w.strip() for w in banned_es.splitlines() if w.strip()],
            "english_offensive": [w.strip() for w in off_en.splitlines() if w.strip()],
            "spanish_offensive": [w.strip() for w in off_es.splitlines() if w.strip()],
        })
        st.success("Saved. New rules apply to the next audit you run.")


# ==========================================
# 12. ROUTE TO THE ACTIVE VIEW
# ==========================================
VIEW_ROUTER = {
    "Dashboard": view_dashboard,
    "Agents": view_agents,
    "AgentDetails": view_agent_details,
    "CallReport": view_call_report,
    "Auditor": view_auditor,
    "Settings": view_settings,
}
VIEW_ROUTER.get(st.session_state.current_view, view_dashboard)()
