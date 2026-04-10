import streamlit as st
import requests
import json
import plotly.graph_objects as go
from PIL import Image
import io

# --- Page Config ---
st.set_page_config(
    page_title="ResumeAnalyzer | Executive Intelligence",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom Styling ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Main Background */
    .stApp {
        background: radial-gradient(circle at top right, #1a1a2e, #16213e, #0f3460);
        color: #e9ecef;
    }
    
    /* Heading Sizes */
    h1 { font-size: 3.5rem !important; font-weight: 800 !important; margin-bottom: 0.5rem !important; }
    h2 { font-size: 2.2rem !important; font-weight: 700 !important; color: #00d2ff !important; margin-top: 2rem !important; }
    h3 { font-size: 1.5rem !important; font-weight: 600 !important; color: #3a7bd5 !important; }
    
    /* Premium Glassmorphism Cards */
    .glass-card {
        background: rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(15px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 20px;
        padding: 2rem;
        margin-bottom: 1.5rem;
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    
    .glass-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
        border-color: rgba(0, 210, 255, 0.3);
    }

    /* Section Icons & Headers */
    .section-header {
        display: flex;
        align-items: center;
        gap: 15px;
        margin-bottom: 1rem;
    }
    
    .section-icon {
        background: linear-gradient(135deg, #00d2ff, #3a7bd5);
        width: 45px;
        height: 45px;
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.5rem;
        box-shadow: 0 4px 15px rgba(0, 210, 255, 0.3);
    }

    /* Status Badges */
    .badge {
        display: inline-block;
        padding: 6px 16px;
        border-radius: 30px;
        font-size: 0.85rem;
        font-weight: 600;
        margin: 4px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .badge-match { background: rgba(46, 204, 113, 0.2); color: #2ecc71; border: 1px solid rgba(46, 204, 113, 0.3); }
    .badge-missing { background: rgba(231, 76, 60, 0.2); color: #e74c3c; border: 1px solid rgba(231, 76, 60, 0.3); }
    
    /* Custom Sidebar */
    [data-testid="stSidebar"] {
        background-color: rgba(15, 52, 96, 0.95) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    /* Clean text for content */
    .content-text {
        line-height: 1.6;
        color: #ced4da;
        font-size: 1.05rem;
        white-space: pre-wrap;
    }

    /* Gradients */
    .text-gradient {
        background: linear-gradient(90deg, #00d2ff, #3a7bd5, #00d2ff);
        background-size: 200% auto;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        animation: shine 3s linear infinite;
    }
    
    @keyframes shine {
        to { background-position: 200% center; }
    }
    
    /* Remove Streamlit Header Anchor Links (the chain link icon) */
    .stMarkdown a {
        text-decoration: none !important;
    }
    .stMarkdown a svg {
        display: none !important;
    }
    /* Fallback for native anchor elements */
    a.header-anchor, a[href^="#"] svg {
        display: none !important;
    }
    </style>
""", unsafe_allow_html=True)

import os

# --- Utility Functions ---
def call_analyze_api(file, job_skills=""):
    base_url = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
    url = f"{base_url}/analyze"
    files = {"file": (file.name, file.getvalue(), file.type)}
    data = {"job_skills": job_skills}
    
    try:
        response = requests.post(url, files=files, data=data)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error connecting to backend: {e}")
        return None

def create_radar_chart(detected, requested):
    if not requested:
        return None
    
    all_skills = list(set(detected + requested))
    detected_vals = [1 if s in detected else 0 for s in all_skills]
    requested_vals = [1 if s in requested else 0 for s in all_skills]
    
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=detected_vals,
        theta=all_skills,
        fill='toself',
        name='Current Profile',
        line_color='#00d2ff',
        hovertemplate="<b>%{theta}</b><br>Status: %{r|Matched;Missing}<extra></extra>"
    ))
    fig.add_trace(go.Scatterpolar(
        r=requested_vals,
        theta=all_skills,
        fill='toself',
        name='Industry Target',
        line_color='#e74c3c',
        hovertemplate="<b>%{theta}</b><br>Required<extra></extra>"
    ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=False, range=[0, 1]),
            angularaxis=dict(gridcolor="rgba(255,255,255,0.1)", linecolor="rgba(255,255,255,0.1)"),
            bgcolor="rgba(0,0,0,0)"
        ),
        showlegend=True,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e9ecef", size=12),
        margin=dict(t=30, b=30, l=30, r=30)
    )
    return fig

# --- Main Layout ---
st.markdown('<h1 class="text-gradient">Resume Intelligence</h1>', unsafe_allow_html=True)
st.markdown("### Advanced Mathematical Skill Mapping & Analysis")

# --- Configuration Section ---
st.markdown("<br>", unsafe_allow_html=True)
st.markdown('#### ⚙️ Target Specialization')

predefined_roles = {
    "Frontend Developer": "javascript, react, html, css, ui/ux, git",
    "Backend Developer": "python, java, node.js, sql, django, flask, docker, aws",
    "AI/ML Engineer": "python, machine learning, nlp, tensorflow, pytorch, data analysis",
    "Data Scientist": "python, sql, machine learning, pandas, statistics",
    "Custom Role": ""
}

cfg_col1, cfg_col2 = st.columns([1, 1])

with cfg_col1:
    selected_role = st.selectbox("Select Role Profile", list(predefined_roles.keys()))

with cfg_col2:
    if selected_role == "Custom Role":
        custom_skills = st.text_input("Define Custom Skills", placeholder="e.g. Kotlin, Unity, C#...")
    else:
        custom_skills = predefined_roles[selected_role]

st.markdown("<br>", unsafe_allow_html=True)
st.markdown('#### 📄 Document Upload')
uploaded_file = st.file_uploader("", type=["pdf", "docx", "txt", "png", "jpg", "jpeg"])

if uploaded_file:
    if st.button("🚀 INITIATE ANALYSIS"):
        with st.spinner("Deconstructing document tokens..."):
            result = call_analyze_api(uploaded_file, custom_skills)
            if result:
                st.session_state['analysis_result'] = result
                st.balloons()

if 'analysis_result' in st.session_state:
    res = st.session_state['analysis_result']
    
    # ONLY show dashboard if we have actual skill data
    if res.get("detected_skills") or res.get("missing_skills"):
        st.markdown("## 📊 Executive Dashboard")
        col1, col2 = st.columns([1, 1])
        
        with col1:
            radar = create_radar_chart(res["detected_skills"], res["requested_skills"])
            if radar:
                st.markdown('<h3 style="color:#00d2ff; margin-top:0;">Profile Match Analysis</h3>', unsafe_allow_html=True)
                st.plotly_chart(radar, use_container_width=True, config={'displayModeBar': False})
            else:
                st.info("Set a target specialization to see the match visualization.")

        with col2:
            skills_html = "".join([f'<span class="badge badge-match">{s}</span>' for s in res["detected_skills"]]) if res["detected_skills"] else "<p style='color:#e74c3c;'>No core competencies identified from tokens.</p>"
            missing_html = "".join([f'<span class="badge badge-missing">{s}</span>' for s in res["missing_skills"]]) if res["missing_skills"] else "<p style='color:#2ecc71;'>Complete profile match detected!</p>"
            
            inventory_html = f"""
            <div class="glass-card" style="height: 100%;">
                <h3 style="margin-top:0;">Skill Inventory</h3>
                <h4 style="color:#ced4da; margin-bottom:10px; margin-top:20px;">✅ Detected Competencies</h4>
                <div>{skills_html}</div>
                <h4 style="color:#ced4da; margin-bottom:10px; margin-top:20px;">🛠️ Gaps to Bridge</h4>
                <div>{missing_html}</div>
            </div>
            """
            st.markdown(inventory_html, unsafe_allow_html=True)

    # Career Paths
    st.markdown("## 🛣️ Career Trajectories")
    if res["role_suggestions"]:
        sc1, sc2, sc3 = st.columns(3)
        cols = [sc1, sc2, sc3]
        for i, suggestion in enumerate(res["role_suggestions"]):
            with cols[i]:
                st.markdown(f"""
                <div class="glass-card">
                    <h3>{suggestion['role']}</h3>
                    <h2 style="margin-top:0;">{suggestion['match_percentage']}%</h2>
                    <p><b>Strategy:</b> Learn {", ".join(suggestion['missing_skills_to_learn'][:2])}...</p>
                </div>
                """, unsafe_allow_html=True)
    
    # Strategic Feedback
    st.markdown("## 🧠 Strategic Improvements")
    fb = res["feedback"]
    fc1, fc2 = st.columns(2)
    with fc1:
        for h in fb["highlights"]:
            st.success(f"💎 {h}")
    with fc2:
        for i in fb["improvements"]:
            st.warning(f"🚀 {i}")

else:
    # Landing Page State
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("""
    <div class="glass-card" style="text-align: center; border: 1px dashed rgba(255,255,255,0.2);">
        <h2 style="margin-top:0;">Ready for Deconstruction?</h2>
        <p style="font-size: 1.2rem; color: #ced4da;">Upload your credentials to receive a detailed mathematical breakdown of your profile match, 
        skill gaps, and high-probability career paths.</p>
    </div>
    """, unsafe_allow_html=True)
