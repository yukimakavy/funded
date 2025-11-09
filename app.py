import streamlit as st
import os
from openai import OpenAI
from dotenv import load_dotenv
from pitch_engine import (
    get_default_pitch_data,
    get_completion_stats,
    ingest,
    evaluate,
    FIELD_INFO
)

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Page config
st.set_page_config(
    page_title="Startup Pitch Bot",
    page_icon="🚀",
    layout="wide"
)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "So, what problem are you working on solving?"}
    ]

if "pitch_data" not in st.session_state:
    st.session_state.pitch_data = get_default_pitch_data()

if "mode" not in st.session_state:
    st.session_state.mode = "ingest"  # ingest or evaluate

if "evaluation_result" not in st.session_state:
    st.session_state.evaluation_result = None

# Sidebar - Progress Tracker
with st.sidebar:
    st.header("Pitch Progress")

    stats = get_completion_stats(st.session_state.pitch_data)

    # Progress bar
    st.progress(stats["percentage"] / 100)
    st.caption(f"{stats['complete']}/{stats['total']} fields complete")

    # Field status
    st.subheader("Field Status")
    for field_key, field_data in st.session_state.pitch_data.items():
        field_name = FIELD_INFO[field_key]["name"]
        state = field_data["state"]

        if state == "complete":
            st.markdown(f"🟢 **{field_name}**")
        elif state == "partial":
            st.markdown(f"🟡 **{field_name}**")
        else:
            st.markdown(f"⚪ {field_name}")

    # Reset button
    if st.button("Reset Pitch"):
        st.session_state.pitch_data = get_default_pitch_data()
        st.session_state.messages = [
            {"role": "assistant", "content": "So, what problem are you working on solving?"}
        ]
        st.session_state.mode = "ingest"
        st.session_state.evaluation_result = None
        st.rerun()

# Title
st.title("🚀 Startup Pitch Bot")

if st.session_state.mode == "ingest":
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # Regular chat input
    if prompt := st.chat_input("Share your pitch details..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Get AI response via ingest function
        with st.spinner("Thinking..."):
            try:
                result = ingest(
                    client=client,
                    conversation_history=st.session_state.messages,
                    pitch_data=st.session_state.pitch_data
                )

                # Update pitch data
                st.session_state.pitch_data = result["pitch_data"]

                # Add response
                st.session_state.messages.append({"role": "assistant", "content": result["response"]})

                # Check if ready for evaluation
                if result["ready_for_evaluation"]:
                    st.session_state.mode = "evaluate"
            except Exception as e:
                st.error(f"Error: {str(e)}")
                st.exception(e)

        st.rerun()

elif st.session_state.mode == "evaluate":
    # Show pitch summary first
    st.success("🎉 All fields complete! Here's your pitch summary:")
    st.markdown("---")

    for field_key, field_data in st.session_state.pitch_data.items():
        field_name = FIELD_INFO[field_key]["name"]
        value = field_data.get("value", "")

        st.subheader(f"🟢 {field_name}")
        if value:
            st.write(value)
        else:
            st.warning("No data captured for this field")
        st.markdown("")

    # Buttons for submit or go back
    st.markdown("---")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📝 Go Back to Edit", use_container_width=True):
            st.session_state.mode = "ingest"
            st.rerun()

    with col2:
        if st.button("🚀 Submit for Evaluation", type="primary", use_container_width=True):
            st.session_state.mode = "evaluation_result"
            st.rerun()

    with col3:
        if st.button("🔄 Start Over", use_container_width=True):
            st.session_state.pitch_data = get_default_pitch_data()
            st.session_state.messages = [
                {"role": "assistant", "content": "So, what problem are you working on solving?"}
            ]
            st.session_state.mode = "ingest"
            st.session_state.evaluation_result = None
            st.rerun()

elif st.session_state.mode == "evaluation_result":
    # Run evaluation
    if st.session_state.evaluation_result is None:
        with st.spinner("Evaluating your pitch from an investor perspective..."):
            st.session_state.evaluation_result = evaluate(
                client=client,
                pitch_data=st.session_state.pitch_data
            )

    # Display evaluation
    st.header("📊 Investor Evaluation")

    eval_data = st.session_state.evaluation_result["evaluation"]

    # Overall Verdict (at the top)
    verdict = eval_data.get("overall_verdict", {})
    decision = verdict.get("decision", "N/A")
    if "FUNDABLE" in decision and "NOT" not in decision:
        st.success(f"### ✅ Verdict: {decision}")
    else:
        st.error(f"### ❌ Verdict: {decision}")
    st.write(verdict.get("reasoning", "N/A"))

    st.markdown("---")

    # Problem Clarity
    st.subheader("🎯 Problem Clarity")
    problem_clarity = eval_data.get("problem_clarity", {})
    col1, col2 = st.columns([1, 4])
    with col1:
        st.metric("Score", f"{problem_clarity.get('score', 0)}/10")
    with col2:
        st.write(problem_clarity.get("assessment", "N/A"))

    st.markdown("---")

    # Severity
    st.subheader("🔥 Problem Severity")
    severity = eval_data.get("severity", {})
    col1, col2 = st.columns([1, 4])
    with col1:
        st.metric("Score", f"{severity.get('score', 0)}/10")
    with col2:
        st.write(severity.get("assessment", "N/A"))

    st.markdown("---")

    # Competitive Analysis
    st.subheader("⚔️ Competitive Analysis")
    comp_analysis = eval_data.get("competitive_analysis", {})
    st.write("**Market Landscape:**")
    st.write(comp_analysis.get("summary", "N/A"))
    st.write("**Competitive Advantage Assessment:**")
    st.write(comp_analysis.get("competitive_advantage", "N/A"))

    st.markdown("---")

    # GTM Challenges
    st.subheader("📈 Go-to-Market Analysis")
    gtm = eval_data.get("gtm_challenges", {})

    # Overall GTM Score
    overall_gtm = gtm.get("overall_gtm_score", 0)
    st.metric("Overall GTM Viability", f"{overall_gtm}/10")

    # Organic/Viral Potential
    st.write("**Organic/Viral Growth Potential:**")
    organic = gtm.get("organic_viral_potential", {})
    st.info(f"**Feasibility:** {organic.get('feasibility', 'N/A')}")
    st.write(organic.get("reasoning", "N/A"))
    if organic.get("competitor_examples"):
        st.write(f"*Competitor Examples:* {organic.get('competitor_examples')}")

    st.write("")

    # Paid Acquisition
    st.write("**Paid Acquisition Economics:**")
    paid = gtm.get("paid_acquisition", {})
    st.info(f"**Market Competitiveness:** {paid.get('competitiveness', 'N/A')}")
    st.write(f"*Unit Economics:* {paid.get('unit_economics', 'N/A')}")
    st.write(f"*Channels:* {paid.get('channels', 'N/A')}")

    st.write("")

    # Retention & Monetization
    st.write("**Retention & Monetization:**")
    retention = gtm.get("retention_monetization", {})
    st.write(retention.get("assessment", "N/A"))

    # Options to continue
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📝 Refine Pitch", type="primary", use_container_width=True):
            st.session_state.mode = "ingest"
            st.session_state.evaluation_result = None
            st.rerun()
    with col2:
        if st.button("🔄 Start Over", use_container_width=True):
            st.session_state.pitch_data = get_default_pitch_data()
            st.session_state.messages = [
                {"role": "assistant", "content": "So, what problem are you working on solving?"}
            ]
            st.session_state.mode = "ingest"
            st.session_state.evaluation_result = None
            st.rerun()
