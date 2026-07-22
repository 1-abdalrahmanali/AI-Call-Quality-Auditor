import json
import os
import streamlit as st
from openai import OpenAI

SERVER_GROQ_KEY = "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"

st.set_page_config(
    page_title="AI Call QA Auditor | Abdalrahman Ali", 
    page_icon="🎙️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔐 Secure Login")
        st.markdown("Please enter your password to access **AI Call QA Auditor**.")
        
        password_input = st.text_input("Password:", type="password")
        
        if st.button("Login 🚀", use_container_width=True):
            if password_input == "Abdalrahman2026": 
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("😕 Incorrect password. Please try again.")
    return False

if not check_password():
    st.stop()

# --- بعد تسجيل الدخول بنجاح ---

st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
    }
    [data-testid="stMetric"] {
        background-color: #1e293b !important;
        border: 1px solid #334155 !important;
        padding: 15px !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }
    [data-testid="stMetricLabel"] {
        color: #94a3b8 !important;
        font-size: 14px !important;
    }
    [data-testid="stMetricValue"] {
        color: #f8fafc !important;
        font-size: 24px !important;
    }
    </style>
""", unsafe_allow_html=True)

# Sidebar Configuration
with st.sidebar:
    st.title("QA Control Center")
    st.markdown("Automated Call Quality Assurance.")
    
    st.markdown("---")
    st.markdown("👨‍💻 **Developer & System Owner:**")
    st.markdown("### **Abdalrahman Ali**")
    st.markdown("---")
    
    st.subheader("📂 Upload Call Audio")
    uploaded_file = st.file_uploader("Upload customer service audio record", type=["mp3", "wav", "m4a"])
    
    st.divider()
    if st.button("Log out 🔒", use_container_width=True):
        st.session_state["password_correct"] = False
        st.rerun()

st.title("🎙️ AI Call Quality Assurance Auditor")
st.markdown("Automated speech-to-text transcription, policy compliance checking, profanity screening, and grammar analysis powered by advanced LLMs.")

if uploaded_file is not None:
    audio_path = "temp_call_audio.mp3"
    with open(audio_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    col_audio, col_info = st.columns([2, 1])
    with col_audio:
        st.subheader("🔊 Audio Player Review")
        st.audio(audio_path, format="audio/mp3")
    with col_info:
        st.subheader("📌 File Metadata")
        st.info(f"**Filename:** {uploaded_file.name}\n**Size:** {round(uploaded_file.size / 1024, 2)} KB")

    if st.button("🚀 Run Quality Audit", type="primary", use_container_width=True):
        if not SERVER_GROQ_KEY or "حط_المفتاح" in SERVER_GROQ_KEY:
            st.error("⚠️ Please insert your Groq API key inside the SERVER_GROQ_KEY variable in the code.")
        else:
            with st.spinner("🔄 Processing speech transcription and evaluating compliance rules..."):
                try:
                    client = OpenAI(
                        api_key=SERVER_GROQ_KEY,
                        base_url="https://api.groq.com/openai/v1"
                    )
                    
                    if os.path.exists("banned_words.json"):
                        with open("banned_words.json", "r", encoding="utf-8") as file:
                            banned_rules = json.load(file)
                    else:
                        banned_rules = {
                            "english_banned": ["not my problem", "I don't care", "whatever"],
                            "spanish_banned": [],
                            "english_offensive": ["idiot", "stupid"],
                            "spanish_offensive": []
                        }
                    
                    with open(audio_path, "rb") as audio_file:
                        transcript_response = client.audio.transcriptions.create(
                            model="whisper-large-v3",
                            file=audio_file
                        )
                    transcript_text = transcript_response.text
                    
                    # الـ Prompt الصارم المحدث (يمنع التدخل في الأساليب والجمل السليمة ويترك الدرجة للحساب الآلي)
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
                    2. Check if the agent used ANY exact phrase from the Banned lists provided above. List them in `banned_words_found`. Set `has_profanity` to true if offensive words are found.
                    3. Check if the agent used ANY exact word from the Offensive lists provided above. List them in `offensive_words_found`.
                    4. Check for GRAMMAR ERRORS ONLY. 
                       - STRICT RULE: Do NOT flag sentences just because they lack politeness, or because you want a "better phrasing" (e.g., "Sorry for bothering" or "When did you leave?" are grammatically correct and MUST NOT be flagged). 
                       - Only flag undeniable grammar, tense, or syntax structural breakages (e.g., "He go" instead of "He goes"). 
                       - If a sentence is grammatically correct, leave it alone. If there are no true grammar errors, return an empty list [].
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
                        messages=[{"role": "user", "content": prompt}]
                    )
                    
                    result = json.loads(response.choices[0].message.content)
                    
                    # --- معادلة الحساب الآلي الدقيقة (خصم 0.25 لكل خطأ نحوي حقيقي) ---
                    base_score = 10.0
                    
                    # خصم الكلمات المسيئة (2 درجة لكل كلمة)
                    offensive_count = len(result.get("offensive_words_found", []))
                    base_score -= (offensive_count * 2.0)
                    
                    # خصم العبارات المحظورة (1 درجة لكل عبارة)
                    banned_count = len(result.get("banned_words_found", []))
                    base_score -= (banned_count * 1.0)
                    
                    # خصم الأخطاء النحوية (0.25 لكل خطأ، بحد أقصى درجتين إجمالاً)
                    grammar_errors_count = len(result.get("grammar_errors", []))
                    grammar_penalty = min(grammar_errors_count * 0.25, 2.0)
                    base_score -= grammar_penalty
                    
                    # ضبط الدرجة النهائية بين 0 و 10 وتقريبها لرقمين عشريين
                    final_score = max(0.0, min(10.0, base_score))
                    final_score = round(final_score, 2)
                    
                    result["score"] = final_score
                    
                    st.success("✅ Audit analysis completed successfully!")
                    
                    with st.expander("📄 View Full Speech Transcription", expanded=True):
                        st.write(transcript_text)
                    
                    st.divider()
                    
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Detected Language", result.get("language", "N/A"))
                    m2.metric("Final Score", f"{result.get('score', 0)} / 10")
                    m3.metric("Profanity Status", "Flagged ⚠️" if result.get("has_profanity") else "Clean ✅")
                    
                    st.divider()
                    
                    if "audit_summary" in result:
                        st.subheader("📋 Executive Audit Summary")
                        st.info(result.get("audit_summary"))
                    
                    col_off, col_ban = st.columns(2)
                    with col_off:
                        st.subheader("🚨 Offensive Words Detected")
                        off_found = result.get("offensive_words_found", [])
                        if off_found:
                            for word in off_found:
                                st.error(f"• {word}")
                        else:
                            st.success("No offensive language detected.")
                            
                    with col_ban:
                        st.subheader("⚠️ Banned Phrases Flagged")
                        ban_found = result.get("banned_words_found", [])
                        if ban_found:
                            for phrase in ban_found:
                                st.warning(f"• {phrase}")
                        else:
                            st.success("No banned phrases used.")
                            
                    st.divider()
                    
                    st.subheader("✍️ Grammar Corrections & Coaching Notes")
                    errors = result.get("grammar_errors", [])
                    if errors:
                        for idx, err in enumerate(errors, 1):
                            with st.container():
                                st.markdown(f"**Issue #{idx}**")
                                c_err, c_cor = st.columns(2)
                                c_err.error(f"**Spoken:** {err.get('error')}")
                                c_cor.success(f"**Corrected:** {err.get('correction')}")
                                st.caption(f"**Reasoning:** {err.get('reason')}")
                                st.markdown("---")
                    else:
                        st.info("No grammar errors detected in the call transcript.")
                        
                except Exception as e:
                    st.error(f"❌ An error occurred during processing: {e}")
else:
    st.info("👈 Please upload an audio record from the sidebar to initiate the audit.")
