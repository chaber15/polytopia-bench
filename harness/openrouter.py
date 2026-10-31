"""Driver for models reached directly through OpenRouter's API (no agent CLI around the model).

One session = one tool loop: the rules go in the system message, the turn prompt in the user message, the game's
tools come from the same MCP server the other drivers use (mcp_poly.py, so calls.jsonl, plans and end_turn behave
identically). The loop stops when the model calls end_turn, answers without a tool call, or runs out of time.
Reasoning is kept between calls (`reasoning_details`, which Gemini needs for its thought signatures).

Key: OPENROUTER_API_KEY, or a file named by OPENROUTER_API_KEY_FILE. Out of credits (HTTP 402) is reported as
an error containing "out of credits", so the turn is left open for --resume and the bench scripts stop.
"""
import asyncio
import json
import os
import time
from pathlib import Path

import requests

URL = os.environ.get("OPENROUTER_URL", "https://openrouter.ai/api/v1") + "/chat/completions"


class OutOfCredits(Exception):
    pass


def api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key and os.environ.get("OPENROUTER_API_KEY_FILE"):
        key = Path(os.environ["OPENROUTER_API_KEY_FILE"]).read_text(encoding="utf-8").strip()
    if not key:
        raise SystemExit("set OPENROUTER_API_KEY (or OPENROUTER_API_KEY_FILE) for --driver openrouter")
    return key


def post(body, deadline, transcript):
    """One chat completion, retrying rate limits and server errors until the deadline."""
    wait = 5
    while True:
        try:
            r = requests.post(URL, json=body, timeout=max(10, min(600, deadline - time.time())),
                              headers={"Authorization": f"Bearer {api_key()}", "X-Title": "Polytopia Bench"})
            data = r.json() if r.content else {}
        except (requests.RequestException, ValueError) as e:
            r, data = None, {"error": {"message": str(e)}}
        transcript.write(json.dumps({"response": data, "status": getattr(r, "status_code", None)}) + "\n")
        transcript.flush()
        status = getattr(r, "status_code", 0)
        if status == 402:
            raise OutOfCredits(f"OpenRouter 402, out of credits: {json.dumps(data.get('error'))[:200]}")
        if status == 200 and data.get("choices"):
            return data
        if status and status not in (408, 429) and status < 500 and status != 200:
            raise RuntimeError(f"OpenRouter {status}: {json.dumps(data.get('error'))[:300]}")
        if time.time() + wait > deadline:
            raise TimeoutError(f"OpenRouter kept failing until the turn timed out: {json.dumps(data.get('error'))[:200]}")
        time.sleep(wait)
        wait = min(wait * 2, 60)


async def _session(system, prompt, args, mcp, timeout, transcript_path, acc):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    deadline = time.time() + timeout
    usage = acc["usage"]
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    body = {"model": args.model, "reasoning": {"effort": args.effort}, "usage": {"include": True},
            "provider": {"require_parameters": True}}   # only providers that support tools and reasoning

    async def run(tools_api=None):
        tools = []
        if tools_api:
            listed = await tools_api.list_tools()
            tools = [{"type": "function", "function": {"name": t.name, "description": t.description or "",
                                                       "parameters": t.inputSchema}} for t in listed.tools]
        with open(transcript_path, "w", encoding="utf-8") as tr:
            tr.write(json.dumps({"request": {**body, "tools": tools, "messages": messages}}) + "\n")
            ended = False
            while not ended:
                data = await asyncio.to_thread(post, {**body, "messages": messages, **({"tools": tools} if tools else {})},
                                               deadline, tr)
                acc["num_turns"] += 1
                u = data.get("usage") or {}
                cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
                written = (u.get("prompt_tokens_details") or {}).get("cache_write_tokens", 0) or 0
                usage["input_tokens"] += u.get("prompt_tokens", 0) - cached - written
                usage["cache_read_input_tokens"] += cached
                usage["cache_creation_input_tokens"] += written
                usage["output_tokens"] += u.get("completion_tokens", 0)
                acc["total_cost_usd"] += u.get("cost", 0) or 0
                msg = data["choices"][0]["message"]
                acc["result"] = msg.get("content") or acc["result"]
                keep = {k: msg[k] for k in ("content", "tool_calls", "reasoning", "reasoning_details") if msg.get(k)}
                messages.append({"role": "assistant", "content": "", **keep})
                calls = msg.get("tool_calls") or []
                if not calls or not tools_api:
                    break
                for c in calls:
                    name = c["function"]["name"]
                    try:
                        arguments = json.loads(c["function"].get("arguments") or "{}")
                        res = await tools_api.call_tool(name, arguments)
                        out = "\n".join(getattr(x, "text", "") for x in res.content)
                    except (ValueError, TypeError) as e:
                        out = f"error: bad arguments for {name}: {e}"
                    messages.append({"role": "tool", "tool_call_id": c["id"], "content": out})
                    tr.write(json.dumps({"tool": name, "result": out[:2000]}) + "\n")
                    ended = ended or name == "end_turn"
                if time.time() > deadline:
                    raise TimeoutError(f"openrouter session timed out after {timeout}s")

    if mcp is None:
        await run()
    else:
        params = StdioServerParameters(command=mcp["command"], args=mcp["args"], env={**os.environ, **mcp["env"]})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                await run(s)


def session(system, prompt, args, mcp, timeout, transcript_path):
    """Returns (Claude-shaped result, error or None)."""
    started = time.time()
    data = {"result": "", "total_cost_usd": 0.0, "num_turns": 0,   # filled as it goes: a failed session still counts
            "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}
    err = None
    try:
        asyncio.run(asyncio.wait_for(_session(system, prompt, args, mcp, timeout, transcript_path, data), timeout + 30))
    except (OutOfCredits, RuntimeError, TimeoutError, asyncio.TimeoutError, requests.RequestException) as e:
        err = str(e) or type(e).__name__
    except BaseExceptionGroup as eg:   # errors raised inside the MCP client's task groups (nested)
        e = eg
        while isinstance(e, BaseExceptionGroup):
            e = e.exceptions[0]
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise e
        err = str(e) or type(e).__name__
    data["duration_ms"] = int((time.time() - started) * 1000)
    return data, err
