"""UI layout helpers, custom styling, empty states, and alert banners."""

import streamlit as st


def apply_custom_theme() -> None:
    """Inject polished styling and CSS variables for a modern dashboard experience."""
    st.markdown(
        """
        <style>
            /* Main Dashboard Font and Colors */
            .main {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }
            /* KPI Card Styling */
            .kpi-container {
                background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.01) 100%);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 12px;
                padding: 18px 22px;
                margin-bottom: 14px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            }
            .kpi-label {
                font-size: 0.85rem;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: #8fa0b5;
                margin-bottom: 6px;
                font-weight: 600;
            }
            .kpi-value {
                font-size: 1.85rem;
                font-weight: 700;
                color: #ffffff;
                margin-bottom: 4px;
            }
            .kpi-subtitle {
                font-size: 0.78rem;
                color: #5c6b7d;
            }
            /* Risk Badges */
            .badge-high {
                background-color: rgba(239, 68, 68, 0.2);
                color: #f87171;
                border: 1px solid rgba(239, 68, 68, 0.4);
                padding: 3px 8px;
                border-radius: 6px;
                font-weight: 600;
            }
            .badge-medium {
                background-color: rgba(245, 158, 11, 0.2);
                color: #fbbf24;
                border: 1px solid rgba(245, 158, 11, 0.4);
                padding: 3px 8px;
                border-radius: 6px;
                font-weight: 600;
            }
            .badge-low {
                background-color: rgba(16, 185, 129, 0.2);
                color: #34d399;
                border: 1px solid rgba(16, 185, 129, 0.4);
                padding: 3px 8px;
                border-radius: 6px;
                font-weight: 600;
            }
            /* Table Header */
            thead tr th:first-child {display:none}
            tbody th {display:none}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(title: str, description: str, action_suggestion: str = "") -> None:
    """Render an informative empty state card when database has no data."""
    st.info(
        f"**{title}**\n\n"
        f"{description}\n\n"
        f"*{action_suggestion}*"
    )


def render_error_banner(error_message: str) -> None:
    """Render a styled warning banner when a query fails."""
    st.error(f"⚠️ **Error Loading Data**: {error_message}")
