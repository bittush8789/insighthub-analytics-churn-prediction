"""Google Gemini Generative AI Assistant Page."""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st

from app.components.ui_helpers import apply_custom_theme, render_empty_state
from src.config.settings import get_settings
from src.database.connection import check_db_connection
from src.llm.orchestrator import GeminiOrchestrator

st.set_page_config(page_title="Gemini AI Assistant | InsightHub", page_icon="🤖", layout="wide")
apply_custom_theme()

st.title("🤖 Google Gemini Retail Analytics & Churn Assistant")
st.markdown(
    "Ask strategic business questions in natural language. Powered by the official Google GenAI SDK, "
    "Gemini invokes authorized, read-only analytics tools to calculate metrics and guarantee grounded answers without data fabrication."
)

settings = get_settings()
api_configured = bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "your_gemini_api_key_here")

if not api_configured:
    st.warning(
        "⚠️ **Google Gemini API Key is missing.**\n\n"
        "To enable GenAI conversational analytics, please add your `GEMINI_API_KEY` to the `.env` file.\n\n"
        "Configured model: `" + settings.GEMINI_MODEL + "`."
    )

if not check_db_connection():
    render_empty_state("Database Offline", "PostgreSQL database is currently disconnected.")
    st.stop()

# Initialize Chat Session State
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Hello! I am your Retail Intelligence Assistant. I can help you analyze revenue trends, "
                "top-selling products, customer retention, and predicted churn risk.\n\n"
                "Try asking me a question or click one of the suggested prompts below!"
            ),
            "tool_called": None,
            "tool_output": None,
        }
    ]

# Suggested Query Quick Buttons
st.markdown("##### 💡 Suggested Questions")
col_q1, col_q2, col_q3 = st.columns(3)
col_q4, col_q5, col_q6 = st.columns(3)

prompt_to_send = None

if col_q1.button("🌍 Highest Revenue Country?"):
    prompt_to_send = "Which country generated the highest revenue, and what were its sales numbers?"
if col_q2.button("📉 Why did revenue decline?"):
    prompt_to_send = "Why did revenue decline during the selected period? Please examine the monthly trend."
if col_q3.button("🏆 Top Revenue Products?"):
    prompt_to_send = "Which products generated the most revenue across all transactions?"
if col_q4.button("⚠️ High-Value Churn Targets?"):
    prompt_to_send = "Which high-value customers have the highest predicted churn risk?"
if col_q5.button("🔄 Frequency vs Churn Risk?"):
    prompt_to_send = "How does customer purchase frequency relate to churn risk according to our customer metrics?"
if col_q6.button("📊 Summarize Business Performance"):
    prompt_to_send = "Summarize the current overall business performance including gross sales, returns, and repeat rates."

# Display Previous Chat Messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("tool_called"):
            st.caption(f"🔧 *Grounded using tool:* `{msg['tool_called']}`")
        if msg.get("tool_output"):
            with st.expander("🔍 View Supporting Data from Tool", expanded=False):
                out = msg["tool_output"]
                if isinstance(out, list) and out and isinstance(out[0], dict):
                    st.dataframe(pd.DataFrame(out), use_container_width=True)
                elif isinstance(out, dict):
                    st.json(out)
                else:
                    st.write(out)

# Handle Chat Input
user_input = st.chat_input("Ask a question about sales, products, customers, or churn...")
active_prompt = prompt_to_send or user_input

if active_prompt:
    # Add user message to UI
    st.session_state.messages.append({
        "role": "user",
        "content": active_prompt,
        "tool_called": None,
        "tool_output": None,
    })
    with st.chat_message("user"):
        st.markdown(active_prompt)

    # Invoke Gemini Orchestrator
    with st.chat_message("assistant"):
        with st.spinner("Analyzing data and generating grounded response..."):
            orchestrator = GeminiOrchestrator()
            result = orchestrator.process_query(active_prompt)

            answer = result["answer"]
            tool_called = result.get("tool_called")
            tool_output = result.get("tool_output")

            st.markdown(answer)
            if tool_called:
                st.caption(f"🔧 *Grounded using tool:* `{tool_called}`")
            if tool_output:
                with st.expander("🔍 View Supporting Data from Tool", expanded=False):
                    if isinstance(tool_output, list) and tool_output and isinstance(tool_output[0], dict):
                        st.dataframe(pd.DataFrame(tool_output), use_container_width=True)
                    elif isinstance(tool_output, dict):
                        st.json(tool_output)
                    else:
                        st.write(tool_output)

            st.session_state.messages.append({
                "role": "assistant",
                "content": answer,
                "tool_called": tool_called,
                "tool_output": tool_output,
            })
