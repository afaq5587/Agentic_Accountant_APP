"""Gemini-powered agent using OpenAI Agents SDK.

This module uses the OpenAI Agents SDK with Google's Gemini models via
the OpenAI-compatible API endpoint.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

try:
    from agents import (
        Agent,
        OpenAIChatCompletionsModel,
        Runner,
        function_tool,
        Tool,
        set_default_openai_client,
        set_tracing_disabled,
    )
    from openai import AsyncOpenAI
except ImportError as e:
    raise ImportError(
        "openai-agents and openai packages are required. Install with: pip install openai-agents openai>=1.0.0"
    ) from e

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
# OpenAI Agents SDK Integration
# ---------------------------------------------------------------------------


class GeminiAgentWrapper:
    """Wrapper around OpenAI Agents SDK Agent to maintain backward compatibility."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.0-flash",
        tool_registry: Optional[ToolRegistry] = None,
        resource_registry: Optional[ResourceRegistry] = None,
        tracer: Optional[ToolTracer] = None,
        instructions: Optional[str] = None,
    ) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set. Please ensure it is defined in your .env file.")

        # Reference: https://ai.google.dev/gemini-api/docs/openai
        self._external_client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )

        self._model = OpenAIChatCompletionsModel(
            model=model_name,
            openai_client=self._external_client,
        )

        # Set default client and disable tracing
        set_default_openai_client(self._external_client)
        set_tracing_disabled(True)

        self._tool_registry = tool_registry
        self._resource_registry = resource_registry
        self._tracer = tracer

        self._instructions = instructions or (
            "You are SHAHENSHA GROUP' ACCOUNTANT, an operations assistant focused on "
            "member payments. Always respect role permissions and use tools when "
            "state changes are requested. Only admins can modify data. Normal users "
            "can only read data through list_members."
        )

        # Create a context storage for the current request
        # This will be set per request in handle_request
        self._current_context: Optional[ToolContext] = None

        # Convert tools from registry to agents SDK format
        agent_tools = self._convert_tools_to_agent_tools()

        # Create the agent with tools
        self._agent = Agent(
            name="SHAHENSHA_ACCOUNTANT",
            model=self._model,
            tools=agent_tools,
            instructions=self._instructions,
        )

        # Memory storage for backward compatibility
        self._memory: List[Dict[str, Any]] = []

    def _convert_tools_to_agent_tools(self) -> List[Any]:
        """Convert ToolRegistry tools to agents SDK function tools."""
        agent_tools = []

        if not self._tool_registry:
            return agent_tools

        for tool_name, tool in self._tool_registry.tools.items():
            # Get the tool schema and ensure it's strict-compliant
            tool_schema = self._make_schema_strict(tool.schema.copy())
            properties = tool_schema.get("properties", {})
            required = tool_schema.get("required", [])
            
            # Create a function with explicit parameters based on the schema
            # We'll use exec to create a function with the correct signature
            param_names = list(properties.keys())
            param_annotations = {}
            
            for param_name in param_names:
                param_schema = properties[param_name]
                param_type = param_schema.get("type", "string")
                
                # Determine Python type
                if param_type == "string":
                    param_annotations[param_name] = str
                elif param_type == "integer":
                    param_annotations[param_name] = int
                elif param_type == "number":
                    param_annotations[param_name] = float
                elif param_type == "boolean":
                    param_annotations[param_name] = bool
                else:
                    param_annotations[param_name] = Any
                
                # Make optional if not required
                if param_name not in required:
                    param_annotations[param_name] = Optional[param_annotations[param_name]]
            
            # Create function with explicit parameters using exec
            # This avoids **kwargs which causes additionalProperties issues
            try:
                # Build function signature string
                sig_parts = []
                for pname in param_names:
                    ptype = param_annotations.get(pname, Any)
                    
                    # Handle type string generation
                    if hasattr(ptype, '__origin__') and hasattr(ptype, '__args__'):
                        # It's a generic like Optional
                        origin = ptype.__origin__
                        args = ptype.__args__
                        if origin is Optional or (hasattr(origin, '__name__') and 'Optional' in str(origin)):
                            inner_type = args[0] if args else Any
                            inner_str = inner_type.__name__ if hasattr(inner_type, '__name__') else str(inner_type)
                            ptype_str = f"Optional[{inner_str}]"
                        else:
                            ptype_str = str(ptype)
                    elif hasattr(ptype, '__name__'):
                        ptype_str = ptype.__name__
                    else:
                        ptype_str = str(ptype)
                    
                    if pname in required:
                        sig_parts.append(f"{pname}: {ptype_str}")
                    else:
                        # Get default value from schema
                        p_schema = properties.get(pname, {})
                        default_val = p_schema.get("default")
                        if default_val is not None:
                            sig_parts.append(f"{pname}: {ptype_str} = {repr(default_val)}")
                        else:
                            # Use Optional if not already Optional
                            if "Optional" not in ptype_str:
                                inner = ptype_str
                                ptype_str = f"Optional[{inner}]"
                            sig_parts.append(f"{pname}: {ptype_str} = None")
                
                sig_str = ", ".join(sig_parts) if sig_parts else ""
                
                # Build function body - collect all params into a dict
                param_collect = ", ".join([f"'{p}': {p}" for p in param_names]) if param_names else ""
                param_dict = f"{{{param_collect}}}" if param_collect else "{}"
                
                # Create function code
                func_body = f"""
async def {tool_name}({sig_str}) -> str:
    \"\"\"{tool.description.replace('"', '\\"')}\"\"\"
    _self = _captured_self
    _tool_obj = _captured_tool
    _tool_name = '{tool_name}'
    _required = {required}
    
    if not _self._current_context:
        raise ToolExecutionError("No context available for tool execution")
    try:
        # Build kwargs from parameters
        kwargs = {param_dict}
        # Filter None values for optional params
        filtered = {{k: v for k, v in kwargs.items() if v is not None or k in _required}}
        # Validate required
        for p in _required:
            if p not in filtered:
                raise ToolExecutionError(f"Required parameter '{{p}}' is missing")
        result = _tool_obj.handler(_self._current_context, **filtered)
        if _self._tracer:
            _self._tracer.record(_tool_name, filtered, result)
        response = {{
            "status": result.status,
            "message": result.message,
            "data": result.data,
        }}
        return json.dumps(response, ensure_ascii=False)
    except ToolExecutionError as e:
        return json.dumps({{"status": "error", "message": str(e)}}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({{"status": "error", "message": f"Unexpected error: {{str(e)}}"}}, ensure_ascii=False)
"""
                
                # Execute in namespace with captured variables
                exec_namespace = {
                    "_captured_self": self,
                    "_captured_tool": tool,
                    "ToolExecutionError": ToolExecutionError,
                    "json": json,
                    "Optional": Optional,
                    "str": str,
                    "int": int,
                    "float": float,
                    "bool": bool,
                    "Any": Any,
                }
                
                exec(func_body, exec_namespace)
                handler_func = exec_namespace[tool_name]
                
                # Set annotations properly
                handler_func.__annotations__ = param_annotations.copy()
                handler_func.__annotations__["return"] = str
                
                # Create the function tool
                tool_wrapper = function_tool(handler_func)
                agent_tools.append(tool_wrapper)
                
            except Exception as e:
                print(f"Error creating tool {tool_name}: {e}")
                import traceback
                traceback.print_exc()
                continue

        return agent_tools
    
    def _make_schema_strict(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Make a schema strict-compliant by removing additionalProperties and ensuring proper structure."""
        import copy
        
        strict_schema = copy.deepcopy(schema)
        
        # Remove additionalProperties at root level
        strict_schema.pop("additionalProperties", None)
        
        # Ensure type is set
        if "type" not in strict_schema:
            strict_schema["type"] = "object"
        
        # Clean properties recursively
        if "properties" in strict_schema:
            cleaned_props = {}
            for prop_name, prop_schema in strict_schema["properties"].items():
                if isinstance(prop_schema, dict):
                    # Remove additionalProperties
                    prop_schema = prop_schema.copy()
                    prop_schema.pop("additionalProperties", None)
                    
                    # Ensure type is set
                    if "type" not in prop_schema:
                        # Try to infer from description or use string as default
                        prop_schema["type"] = "string"
                    
                    cleaned_props[prop_name] = prop_schema
                else:
                    cleaned_props[prop_name] = prop_schema
            
            strict_schema["properties"] = cleaned_props
        
        return strict_schema

    @property
    def tracer(self) -> Optional[ToolTracer]:
        return self._tracer

    @property
    def memory(self) -> Any:
        """Return a memory-like object for backward compatibility."""
        return type("Memory", (), {
            "serialize": lambda: self._memory
        })()

    async def handle_request(
        self,
        message: str,
        requester_role: str,
        admin_id: Optional[str] = None,
        admin_password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle a request and return a response in the expected format."""
        # Create context for this request
        context = ToolContext(
            requester_role=requester_role,
            admin_id=admin_id,
            admin_password=admin_password,
        )
        self._current_context = context

        # Add context information to the message
        context_message = message
        if requester_role == "Admin" and admin_id:
            context_message = f"[Role: {requester_role}, Admin ID: {admin_id}] {message}"
        else:
            context_message = f"[Role: {requester_role}] {message}"

        # Add resource snapshot if available
        if self._resource_registry:
            resources = self._resource_registry.snapshot()
            if resources:
                context_message += f"\n\nCurrent state: {json.dumps(resources, ensure_ascii=False, indent=2)}"

        # Store in memory
        self._memory.append({
            "role": "user",
            "content": message,
            "metadata": {"role": requester_role},
        })

        try:
            # Run the agent using Runner
            result = await Runner.run(
                starting_agent=self._agent,
                input=context_message,
            )

            # Extract the response text
            response_text = ""
            tool_results = []

            # Get the final output from the result
            if hasattr(result, "final_output"):
                response_text = str(result.final_output)
            elif hasattr(result, "messages") and result.messages:
                # Get the last assistant message
                for msg in reversed(result.messages):
                    if hasattr(msg, "role") and getattr(msg, "role", None) == "assistant":
                        if hasattr(msg, "content"):
                            response_text = str(msg.content)
                        break
            elif hasattr(result, "content"):
                response_text = str(result.content)

            # Collect tool calls if any (from tracer)
            if self._tracer:
                recent_entries = self._tracer.entries[-10:]  # Get last 10 entries
                for entry in recent_entries:
                    if entry.get("tool"):
                        tool_results.append({
                            "name": entry.get("tool", "unknown"),
                            "status": entry.get("response", {}).get("status", "success"),
                            "message": entry.get("response", {}).get("message", "Tool executed"),
                            "data": entry.get("response", {}).get("data", {}),
                        })

            # Store response in memory
            self._memory.append({
                "role": "assistant",
                "content": response_text,
            })

            return {
                "status": "success",
                "message": response_text or "I processed your request.",
                "tool_results": tool_results,
                "memory": self._memory,
            }

        except Exception as e:
            print(f"Agent Error: {e}") # Add logging
            import traceback
            traceback.print_exc() # Print stack trace to logs
            error_msg = f"Error processing request: {str(e)}"
            self._memory.append({
                "role": "assistant",
                "content": error_msg,
                "metadata": {"error": True},
            })
            return {
                "status": "error",
                "message": error_msg,
                "tool_results": [],
                "memory": self._memory,
            }
        finally:
            self._current_context = None


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def create_agent() -> Dict[str, Any]:
    """Create the agent and supporting services using OpenAI Agents SDK."""

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    api_key = os.getenv("GEMINI_API_KEY", "")
    # Determine default DB path based on environment
    if os.environ.get("VERCEL"):
        default_db_path = "/tmp/members.db"
    else:
        default_db_path = os.path.join("data", "members.db")
        # Check if we can write to the data directory
        try:
            os.makedirs("data", exist_ok=True)
            # Test write permissions
            test_file = os.path.join("data", ".write_test")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
        except (OSError, IOError):
            default_db_path = "/tmp/members.db"
        
    storage_path = os.getenv("SGA_DB_PATH", default_db_path)

    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set. Please ensure it is defined in your .env file.")

    tooling = build_tooling(storage_path)

    agent = GeminiAgentWrapper(
        api_key=api_key,
        model_name=model_name,
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
