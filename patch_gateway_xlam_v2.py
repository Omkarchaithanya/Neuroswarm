#!/usr/bin/env python3
import sys

gateway_path = "/home/tejaswini2482_gmail_com/neuroswarm-arm/neuroswarm_arm/gateway.py"

with open(gateway_path, "r") as f:
    content = f.read()

# Remove any previous partial patches
if "def _enrich_for_xlam" in content:
    print("Previous patch detected. Restoring from backup...")
    import shutil
    shutil.copy(gateway_path + ".bak", gateway_path)
    with open(gateway_path, "r") as f:
        content = f.read()

# 1. Inject _enrich_for_xlam BEFORE handle_chat
enrich = '''
    def _enrich_for_xlam(self, req):
        """Inject xLAM native tool format. xLAM outputs RAW JSON array, not wrapped in tool_calls."""
        import json, os
        if os.getenv("NSA_XLAM_NATIVE_FORMAT", "1") != "1":
            return req
        tools = getattr(req, "tools", None) or getattr(req, "tool_schemas", None)
        if not tools:
            return req
        
        xlam_tools = []
        for tool in tools:
            if isinstance(tool, dict) and "function" in tool:
                fn = tool["function"]
                xlam_tools.append({
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "parameters": {k: v for k, v in fn.get("parameters", {}).get("properties", {}).items()}
                })
        
        task_instruction = (
            "You are an expert in composing functions. You are given a question and a set of possible functions. "
            "Based on the question, you will need to make one or more function/tool calls to achieve the purpose. "
            "If none of the functions can be used, point it out. If the question lacks required parameters, point it out."
        )
        # CRITICAL: xLAM outputs RAW array: [{"name":"...","arguments":{...}}]
        # NOT wrapped in {"tool_calls": [...]}
        format_instruction = (
            "The output MUST strictly be a JSON array, and NO other text MUST be included.\\n"
            "Example: [{\\"name\\": \\"func_name\\", \\"arguments\\": {\\"arg1\\": \\"val1\\"}}]\\n"
            "If no function call is needed, output an empty array: []"
        )
        
        query = req.messages[-1].get("content", "") if req.messages else ""
        prompt = f"[BEGIN OF TASK INSTRUCTION]\\n{task_instruction}\\n[END OF TASK INSTRUCTION]\\n\\n"
        prompt += f"[BEGIN OF AVAILABLE TOOLS]\\n{json.dumps(xlam_tools)}\\n[END OF AVAILABLE TOOLS]\\n\\n"
        prompt += f"[BEGIN OF FORMAT INSTRUCTION]\\n{format_instruction}\\n[END OF FORMAT INSTRUCTION]\\n\\n"
        prompt += f"[BEGIN OF QUERY]\\n{query}\\n[END OF QUERY]\\n"
        
        req.messages = [{"role": "user", "content": prompt}]
        return req

'''

content = content.replace(
    "    def handle_chat(self, req: ChatRequest) -> ChatResponse:",
    enrich + "    def handle_chat(self, req: ChatRequest) -> ChatResponse:"
)

# 2. Inject enrichment before cascade.generate
content = content.replace(
    "        response = self.cascade.generate(req)",
    "        req = self._enrich_for_xlam(req)\n        response = self.cascade.generate(req)"
)

# 3. Fix _extract_tool_call to parse xLAM RAW ARRAY format
old_extract = '''    def _extract_tool_call(self, response: ChatResponse) -> dict | None:
        if response.tool_calls:
            return response.tool_calls[0]
        content = response.content or ""
        # Try to find a tool call in the content'''

new_extract = '''    def _extract_tool_call(self, response: ChatResponse) -> dict | None:
        if response.tool_calls:
            return response.tool_calls[0]
        content = response.content or ""
        # xLAM native format: RAW JSON array [{"name":"...","arguments":{...}}]
        stripped = content.strip()
        if stripped.startswith("["):
            try:
                import json
                arr = json.loads(stripped)
                if isinstance(arr, list) and arr:
                    call = arr[0]
                    return {
                        "tool_name": call.get("name", ""),
                        "arguments": call.get("arguments", {}),
                    }
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        # Try to find a tool call in the content'''

content = content.replace(old_extract, new_extract)

with open(gateway_path, "w") as f:
    f.write(content)

print("SUCCESS: gateway.py patched for xLAM v2 (raw array format).")
