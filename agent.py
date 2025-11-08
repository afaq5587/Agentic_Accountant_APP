"""Gemini-powered agent orchestrator for SHAHENSHA GROUP' ACCOUNTANT.

This module mirrors the OpenAI Agents SDK shape (agent + tool/resource system)
while delegating language reasoning to Google's Gemini models.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import google.generativeai as genai

from tools import (
    ToolContext,
    ToolExecutionError,
    ToolRegistry,
    ToolResult,
    build_tooling,
    ResourceRegistry,
    ToolTracer,
)


# ---------------------------------------------------------------------------
# Memory & Conversation Tracking
# ---------------------------------------------------------------------------


@dataclass
class MemoryEntry:
    role: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentMemory:
    def __init__(self, max_turns: int = 20) -> None:
        self._turns: List[MemoryEntry] = []
        self._max_turns = max_turns

    def add(self, role: str, content: str, **metadata: Any) -> None:
        if len(self._turns) >= self._max_turns:
            self._turns.pop(0)
        self._turns.append(MemoryEntry(role=role, content=content, metadata=dict(metadata)))

    def formatted_history(self) -> str:
        lines: List[str] = []
        for entry in self._turns:
            label = entry.role.upper()
            lines.append(f"[{label}] {entry.content}")
        return "\n".join(lines)

    def serialize(self) -> List[Dict[str, Any]]:
        return [
            {
                "role": entry.role,
                "content": entry.content,
                "metadata": entry.metadata,
            }
            for entry in self._turns
        ]


# ---------------------------------------------------------------------------
# Gemini Agent Implementation
# ---------------------------------------------------------------------------


class GeminiAgent:
    def __init__(
        self,
        model_name: str,
        api_key: str,
        tool_registry: ToolRegistry,
        resource_registry: ResourceRegistry,
        tracer: ToolTracer,
        instructions: Optional[str] = None,
        max_iterations: int = 4,
        temperature: float = 0.2,
    ) -> None:
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is required to run the agent")

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model_name)
        self._tool_registry = tool_registry
        self._resource_registry = resource_registry
        self._tracer = tracer
        self._instructions = instructions or (
            "You are SHAHENSHA GROUP' ACCOUNTANT, an operations assistant focused on "
            "member payments. Always respect role permissions and use tools when "
            "state changes are requested."
        )
        self._max_iterations = max_iterations
        self._temperature = temperature
        self._memory = AgentMemory()

    @property
    def tracer(self) -> ToolTracer:
        return self._tracer

    @property
    def memory(self) -> AgentMemory:
        return self._memory

    # ------------------------------------------------------------------
    # Core inference loop
    # ------------------------------------------------------------------

    def handle_request(
        self,
        message: str,
        requester_role: str,
        admin_id: Optional[str] = None,
        admin_password: Optional[str] = None,
    ) -> Dict[str, Any]:
        context = ToolContext(
            requester_role=requester_role,
            admin_id=admin_id,
            admin_password=admin_password,
        )

        self._memory.add("user", message, role=requester_role)
        tool_results: List[ToolResult] = []

        for iteration in range(self._max_iterations):
            planning_response = self._plan(message, requester_role, context)

            if planning_response.get("action") == "call_tool":
                tool_name = planning_response.get("tool")
                arguments = planning_response.get("arguments", {})
                if not tool_name:
                    return self._finalize_error("Tool name missing in plan")

                try:
                    tool_result = self._execute_tool(tool_name, context, arguments)
                    tool_results.append(tool_result)
                    self._memory.add(
                        "tool",
                        json.dumps(
                            {
                                "tool": tool_name,
                                "result": tool_result.message,
                                "status": tool_result.status,
                                "data": tool_result.data,
                            },
                            ensure_ascii=False,
                        ),
                        tool=tool_name,
                    )
                    message = planning_response.get(
                        "follow_up", "Provide a summary of the recent tool results."
                    )
                    continue
                except ToolExecutionError as exc:
                    error_message = f"Tool execution failed: {exc}"
                    self._memory.add("assistant", error_message, error="tool_failure")
                    message = error_message
                    continue
                except Exception as exc:  # pragma: no cover - defensive
                    error_message = f"Unexpected tool error: {exc}"  # noqa: PERF203
                    self._memory.add("assistant", error_message, error="tool_failure")
                    message = error_message
                    continue

            elif planning_response.get("action") == "clarify":
                clarification = planning_response.get(
                    "response", "I need additional details to continue."
                )
                self._memory.add("assistant", clarification, type="clarification")
                return {
                    "status": "clarification",
                    "message": clarification,
                    "tool_results": [self._serialize_tool_result(r) for r in tool_results],
                    "memory": self._memory.serialize(),
                }
            else:
                final_text = planning_response.get(
                    "response",
                    "I could not construct a proper response. Please try again.",
                )
                self._memory.add("assistant", final_text)
                return {
                    "status": "success",
                    "message": final_text,
                    "tool_results": [self._serialize_tool_result(r) for r in tool_results],
                    "memory": self._memory.serialize(),
                }

        # If the loop completes without a final answer
        fallback = "I reached the iteration limit. Please refine your request."
        self._memory.add("assistant", fallback, error="iteration_limit")
        return self._finalize_error(fallback)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _plan(
        self, message: str, requester_role: str, context: ToolContext
    ) -> Dict[str, Any]:
        prompt = self._compose_prompt(message, requester_role, context)
        response = self._model.generate_content(
            prompt,
            generation_config={
                "temperature": self._temperature,
                "candidate_count": 1,
                "top_p": 0.9,
            },
        )
        text = self._extract_text(response)
        return self._parse_plan(text)

    def _compose_prompt(
        self, message: str, requester_role: str, context: ToolContext
    ) -> str:
        tools_block = []
        for tool in self._tool_registry.tools.values():
            tools_block.append(
                f"- {tool.name}: {tool.description}\n  Parameters: {json.dumps(tool.schema, indent=2)}"
            )

        resources_snapshot = json.dumps(
            self._resource_registry.snapshot(), indent=2, ensure_ascii=False
        )

        instructions = f"""
{self._instructions}

You must output a single JSON object with the following structure:
{{
  "action": "call_tool" | "final" | "clarify",
  "response": "assistant reply for the user",
  "tool": "name of tool to call (when action is call_tool)",
  "arguments": {{...}},
  "follow_up": "optional guidance for the next reasoning step"
}}

Always reason about role permissions. Only admins can modify data. Normal users
can only read data through list_members. Do not hallucinate tool names.
"""

        history = self._memory.formatted_history()
        snapshot = f"Requester role: {requester_role}."
        if context.admin_id:
            snapshot += f" Admin ID provided: {context.admin_id}."

        prompt = (
            f"{instructions}\n\n"
            f"Available tools:\n{os.linesep.join(tools_block)}\n\n"
            f"Resource snapshot:\n{resources_snapshot}\n\n"
            f"Conversation so far:\n{history}\n\n"
            f"Latest user request: {message}\n\n"
            f"Context: {snapshot}\n"
        )
        return prompt

    def _execute_tool(
        self, tool_name: str, context: ToolContext, arguments: Dict[str, Any]
    ) -> ToolResult:
        tool = self._tool_registry.get(tool_name)
        return tool.handler(context, **arguments)

    def _parse_plan(self, text: str) -> Dict[str, Any]:
        json_payload = self._extract_json(text)
        if not json_payload:
            return {"action": "final", "response": text.strip()}

        try:
            data = json.loads(json_payload)
            if not isinstance(data, dict):
                raise ValueError("Plan must be a JSON object")
        except json.JSONDecodeError:
            return {"action": "final", "response": text.strip()}
        return data

    def _extract_text(self, response: Any) -> str:
        if hasattr(response, "text") and response.text:
            return response.text
        if hasattr(response, "candidates") and response.candidates:
            parts = []
            for candidate in response.candidates:
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if part.text:
                            parts.append(part.text)
            return "\n".join(parts)
        return ""

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        if not text:
            return None
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group(0)
        return None

    def _serialize_tool_result(self, result: ToolResult) -> Dict[str, Any]:
        return {
            "name": result.name,
            "status": result.status,
            "message": result.message,
            "data": result.data,
        }

    def _finalize_error(self, message: str) -> Dict[str, Any]:
        return {
            "status": "error",
            "message": message,
            "tool_results": [],
            "memory": self._memory.serialize(),
        }


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def create_agent() -> Dict[str, Any]:
    """Create the agent and supporting services."""

    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash-latest")
    api_key = os.getenv("GEMINI_API_KEY", "")
    storage_path = os.getenv("SGA_DB_PATH", os.path.join("data", "members.db"))

    tooling = build_tooling(storage_path)

    agent = GeminiAgent(
        model_name=model_name,
        api_key=api_key,
        tool_registry=tooling["tools"],
        resource_registry=tooling["resources"],
        tracer=tooling["tracer"],
    )

    return {
        "agent": agent,
        "db": tooling["db"],
        "tools": tooling["tools"],
        "resources": tooling["resources"],
        "tracer": tooling["tracer"],
    }
