"""Function-calling orchestration, tool execution, and response grounding."""

import json
import logging
from typing import Any, Dict, List, Optional
from google.genai import types

from src.llm.gemini_client import GeminiClientManager
from src.llm.prompts import SYSTEM_INSTRUCTION
from src.llm.tools import ALL_APPROVED_TOOL_FUNCTIONS, APPROVED_TOOLS_MAP
from src.utils.exceptions import ConfigurationError, GeminiAssistantError, SecurityViolationError

logger = logging.getLogger(__name__)


class GeminiOrchestrator:
    """Manages multi-turn or tool-calling conversations with Google Gemini."""

    def __init__(self, client_manager: Optional[GeminiClientManager] = None):
        self.client_manager = client_manager or GeminiClientManager()

    def process_query(self, user_prompt: str) -> Dict[str, Any]:
        """Process user's natural language question with tool-grounded execution.

        Returns:
            Dictionary containing:
            - 'answer': Final generated response text
            - 'tool_called': Name of analytical tool invoked (if any)
            - 'tool_arguments': Arguments passed to tool
            - 'tool_output': Structured output returned by tool (for Streamlit charts/tables)
            - 'error': Optional error description
        """
        prompt_clean = user_prompt.strip()
        if not prompt_clean:
            return {
                "answer": "Please ask a question about sales revenue, top products, customers, or churn risk.",
                "tool_called": None,
                "tool_arguments": None,
                "tool_output": None,
                "error": None,
            }

        try:
            client = self.client_manager.get_client()
        except ConfigurationError as ce:
            logger.warning("Gemini Assistant not configured: %s", ce)
            return {
                "answer": (
                    "**Google Gemini API Key Not Configured**\n\n"
                    "To enable the AI Assistant, please set your `GEMINI_API_KEY` in the `.env` file or environment variables."
                ),
                "tool_called": None,
                "tool_arguments": None,
                "tool_output": None,
                "error": str(ce),
            }

        try:
            logger.info("Sending query to Gemini: '%s'", prompt_clean[:100])

            # Initial generation with tool declarations
            response = client.models.generate_content(
                model=self.client_manager.model_name,
                contents=prompt_clean,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    tools=ALL_APPROVED_TOOL_FUNCTIONS,
                    temperature=0.2,
                ),
            )

            # Check if Gemini requested function call(s)
            function_calls = getattr(response, "function_calls", None)
            if not function_calls and hasattr(response, "candidates") and response.candidates:
                # Inspect parts in first candidate
                first_part = response.candidates[0].content.parts[0]
                if hasattr(first_part, "function_call") and first_part.function_call:
                    function_calls = [first_part.function_call]

            if not function_calls:
                # Direct answer without tool
                answer_text = response.text or "I was unable to determine a conclusive answer from the available data."
                return {
                    "answer": answer_text,
                    "tool_called": None,
                    "tool_arguments": None,
                    "tool_output": None,
                    "error": None,
                }

            # Execute the first authorized tool call
            fc = function_calls[0]
            tool_name = fc.name
            raw_args = dict(fc.args) if fc.args else {}

            logger.info("Gemini invoked tool '%s' with args %s", tool_name, raw_args)

            if tool_name not in APPROVED_TOOLS_MAP:
                raise SecurityViolationError(f"Attempted execution of unauthorized tool: '{tool_name}'")

            tool_func = APPROVED_TOOLS_MAP[tool_name]
            tool_result = tool_func(**raw_args)

            # Follow-up turn providing tool output to Gemini for final grounded synthesis
            follow_up_contents = [
                prompt_clean,
                response.candidates[0].content,
                types.Content(
                    role="tool",
                    parts=[
                        types.Part.from_function_response(
                            name=tool_name,
                            response={"result": tool_result},
                        )
                    ],
                ),
            ]

            second_response = client.models.generate_content(
                model=self.client_manager.model_name,
                contents=follow_up_contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.2,
                ),
            )

            final_text = second_response.text or "Grounding completed."

            return {
                "answer": final_text,
                "tool_called": tool_name,
                "tool_arguments": raw_args,
                "tool_output": tool_result,
                "error": None,
            }

        except SecurityViolationError as sve:
            logger.warning("Security policy violation during GenAI tool call: %s", sve)
            return {
                "answer": f"**Security Violation Blocked**: {sve}",
                "tool_called": None,
                "tool_arguments": None,
                "tool_output": None,
                "error": str(sve),
            }
        except Exception as exc:
            logger.error("Error in Gemini Assistant execution: %s", exc, exc_info=True)
            return {
                "answer": (
                    f"**Assistant Error**: An unexpected error occurred while processing your request with Gemini.\n\n"
                    f"*Details*: `{exc}`"
                ),
                "tool_called": None,
                "tool_arguments": None,
                "tool_output": None,
                "error": str(exc),
            }
