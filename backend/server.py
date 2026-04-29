"""Aradhya Agentic Coding Assistant - FastAPI Backend."""
import os
import re
import shutil
import subprocess
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from loguru import logger
import httpx
from bs4 import BeautifulSoup

try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
except ImportError:
    LlmChat = None
    UserMessage = None

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE_PATH = os.environ.get("ARADHYA_WORKSPACE_PATH", str(REPO_ROOT))
DEFAULT_MODEL_PROVIDER = os.environ.get("ARADHYA_MODEL_PROVIDER", "ollama")
DEFAULT_MODEL_NAME = os.environ.get("ARADHYA_MODEL_NAME", "gemma4:e4b")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "aradhya")
LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")

app = FastAPI(title="Aradhya Agentic Assistant")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=500) if MONGO_URL else None
db = client[DB_NAME] if client is not None else None
MEMORY_SETTINGS: dict[str, dict[str, Any]] = {}
MEMORY_MESSAGES: list[dict[str, Any]] = []
MEMORY_TEMPLATES: list[dict[str, Any]] = []

# ============================================================
# MODELS
# ============================================================
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    mode: str = "chat"
    workspace_path: Optional[str] = None

class CommandRequest(BaseModel):
    description: str
    platform: str = "linux"
    level: str = "user"

class SearchRequest(BaseModel):
    query: str
    security_filter: bool = True

class SettingsUpdate(BaseModel):
    voice_preset: Optional[str] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    security_filter: Optional[bool] = None
    sandbox_mode: Optional[bool] = None
    theme: Optional[str] = None
    assistant_name: Optional[str] = None
    workspace_path: Optional[str] = None

class ShellRequest(BaseModel):
    command: str
    cwd: Optional[str] = None

class FileReadRequest(BaseModel):
    path: str

class FileWriteRequest(BaseModel):
    path: str
    content: str

class GitRequest(BaseModel):
    action: str
    args: Optional[dict] = None
    cwd: Optional[str] = None

class TemplateCreate(BaseModel):
    title: str
    description: str
    prompt: str
    platform: str = "linux"
    level: str = "user"

class DiffRequest(BaseModel):
    path: str
    new_content: str

# ============================================================
# SYSTEM PROMPTS
# ============================================================
AGENTIC_SYSTEM_PROMPT = """You are {assistant_name}, an agentic Operating Intelligence (OI) running locally on the user's machine. You are NOT a chatbot. You are a system-level AI that understands intent, gathers context, and operates the machine.

Core capabilities:
1. COMMAND GENERATION: Craft complex shell commands (Bash, PowerShell, CMD). Always use code blocks with language tags.
2. FILE OPERATIONS: Read, analyze, suggest edits. Output unified diffs when modifying files.
3. GIT WORKFLOWS: Branching, committing, rebasing, conflict resolution.
4. SYSTEM CONTROL: Open apps, change system settings, manage processes, automation.
5. MULTI-STEP WORKFLOWS: For complex tasks (deploy AI, fill forms, multi-app workflows), create a step-by-step plan. Execute each step and WAIT for user confirmation before proceeding to the next step that requires user interaction.
6. PREFERENCES VIA CHAT: Users can change settings by telling you (e.g. "change to dark mode", "rename yourself to Jarvis", "switch to gemma model"). Acknowledge the change.

Rules:
- NEVER hardcode app names, model names, or paths. Use variables/config.
- When generating commands, explain what each part does.
- For dangerous operations, ALWAYS warn with [WARN] prefix.
- For multi-step workflows, present the plan first, then execute step by step.
- If a step requires user review (like form submission), STOP and ask user to review.
- Be concise. Use terminal-style [OK] [WARN] [ERR] [INFO] prefixes.
- When user asks to open apps, control the machine, search files - generate the appropriate commands.

{workspace_context}"""

COMMAND_SYSTEM_PROMPT = """You are {assistant_name}'s Command Engine. Generate system commands from natural language descriptions.
Output ONLY properly formatted code blocks. Add inline comments. Specify if admin/elevated privileges needed.
Platform target: {platform}. Access level: {level}."""

# ============================================================
# LLM HELPERS
# ============================================================
async def get_config():
    defaults = {
        "key": "global",
        "voice_preset": "default-female",
        "model_provider": DEFAULT_MODEL_PROVIDER,
        "model_name": DEFAULT_MODEL_NAME,
        "security_filter": True,
        "sandbox_mode": True,
        "theme": "dark",
        "assistant_name": "Aradhya",
        "workspace_path": DEFAULT_WORKSPACE_PATH,
    }
    settings = await _find_one("settings", {"key": "global"})
    if not settings:
        await _insert_one("settings", dict(defaults))
        return dict(defaults)
    merged = {**defaults, **settings}
    return merged

async def get_llm_response(message: str, session_id: str, system_prompt: str = None) -> str:
    config = await get_config()
    name = config.get("assistant_name", "Aradhya")
    provider = config.get("model_provider", DEFAULT_MODEL_PROVIDER)
    model_name = config.get("model_name", DEFAULT_MODEL_NAME)
    final_prompt = (system_prompt or AGENTIC_SYSTEM_PROMPT).replace("{assistant_name}", name).replace("{workspace_context}", "")

    if provider == "ollama":
        return await _generate_with_ollama(message, final_prompt, model_name)

    if LlmChat is None or UserMessage is None:
        logger.warning("Cloud LLM integration package unavailable; attempting Ollama fallback.")
        return await _generate_with_ollama(message, final_prompt, DEFAULT_MODEL_NAME)

    if not LLM_KEY:
        logger.warning("Cloud model selected without EMERGENT_LLM_KEY; attempting Ollama fallback.")
        return await _generate_with_ollama(message, final_prompt, DEFAULT_MODEL_NAME)

    try:
        chat = LlmChat(api_key=LLM_KEY, session_id=session_id, system_message=final_prompt)
        chat.with_model(provider, model_name)
        response = await chat.send_message(UserMessage(text=message))
        return response
    except Exception as e:
        logger.error(f"LLM error: {e}")
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")

async def generate_command(description: str, platform: str, level: str) -> str:
    config = await get_config()
    name = config.get("assistant_name", "Aradhya")
    prompt_sys = COMMAND_SYSTEM_PROMPT.replace("{assistant_name}", name).replace("{platform}", platform).replace("{level}", level)
    prompt = f"Generate a command/script for: {description}"
    return await get_llm_response(prompt, f"cmd-{uuid.uuid4().hex[:8]}", prompt_sys)


def _memory_collection(name: str):
    return {
        "settings": MEMORY_SETTINGS,
        "messages": MEMORY_MESSAGES,
        "templates": MEMORY_TEMPLATES,
    }[name]


async def _find_one(collection: str, query: dict[str, Any]) -> dict[str, Any] | None:
    if db is not None:
        try:
            return await getattr(db, collection).find_one(query, {"_id": 0})
        except Exception as exc:
            logger.warning(f"Falling back to in-memory {collection}: {exc}")

    store = _memory_collection(collection)
    if collection == "settings":
        key = query.get("key")
        doc = store.get(key)
        return deepcopy(doc) if doc else None

    for item in store:
        if all(item.get(k) == v for k, v in query.items()):
            return deepcopy(item)
    return None


async def _insert_one(collection: str, payload: dict[str, Any]) -> None:
    if db is not None:
        try:
            await getattr(db, collection).insert_one(dict(payload))
            return
        except Exception as exc:
            logger.warning(f"Falling back to in-memory {collection}: {exc}")

    if collection == "settings":
        MEMORY_SETTINGS[payload["key"]] = deepcopy(payload)
        return

    _memory_collection(collection).append(deepcopy(payload))


async def _update_one(collection: str, query: dict[str, Any], update_fields: dict[str, Any], upsert: bool = False) -> None:
    if db is not None:
        try:
            await getattr(db, collection).update_one(query, {"$set": update_fields}, upsert=upsert)
            return
        except Exception as exc:
            logger.warning(f"Falling back to in-memory {collection}: {exc}")

    if collection == "settings":
        key = query.get("key")
        current = deepcopy(MEMORY_SETTINGS.get(key, {}))
        current.update(query)
        current.update(update_fields)
        MEMORY_SETTINGS[key] = current
        return

    store = _memory_collection(collection)
    for item in store:
        if all(item.get(k) == v for k, v in query.items()):
            item.update(update_fields)
            return
    if upsert:
        doc = deepcopy(query)
        doc.update(update_fields)
        store.append(doc)


async def _find_many(collection: str, query: dict[str, Any] | None = None, sort_key: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    query = query or {}
    if db is not None:
        try:
            cursor = getattr(db, collection).find(query, {"_id": 0})
            if sort_key:
                cursor = cursor.sort(sort_key, 1)
            return await cursor.to_list(limit)
        except Exception as exc:
            logger.warning(f"Falling back to in-memory {collection}: {exc}")

    items = [deepcopy(item) for item in _memory_collection(collection) if all(item.get(k) == v for k, v in query.items())]
    if sort_key:
        items.sort(key=lambda item: item.get(sort_key, ""))
    return items[:limit]


async def _delete_one(collection: str, query: dict[str, Any]) -> int:
    if db is not None:
        try:
            result = await getattr(db, collection).delete_one(query)
            return result.deleted_count
        except Exception as exc:
            logger.warning(f"Falling back to in-memory {collection}: {exc}")

    store = _memory_collection(collection)
    if isinstance(store, list):
        for index, item in enumerate(store):
            if all(item.get(k) == v for k, v in query.items()):
                del store[index]
                return 1
    return 0


async def _generate_with_ollama(message: str, system_prompt: str, model_name: str) -> str:
    payload = {
        "model": model_name,
        "prompt": message,
        "system": system_prompt,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=180.0) as http_client:
            response = await http_client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.error(f"Ollama error: {exc}")
        raise HTTPException(
            status_code=503,
            detail=(
                "No working LLM is configured. Start Ollama with a local model or "
                "set EMERGENT_LLM_KEY for cloud providers."
            ),
        ) from exc

    return data.get("response", "").strip()

# ============================================================
# SECURITY FILTER
# ============================================================
MALICIOUS_PATTERNS = [
    r"<script\b[^>]*>.*?</script>", r"javascript:", r"on\w+\s*=", r"eval\s*\(",
    r"document\.cookie", r"window\.location", r"\.exe\s*$", r"data:text/html",
    r"vbscript:", r"powershell\s+-enc", r"wget\s+.*\|.*sh", r"curl\s+.*\|.*bash",
]

def sanitize_search_result(text: str) -> str:
    cleaned = text
    for pattern in MALICIOUS_PATTERNS:
        cleaned = re.sub(pattern, "[FILTERED]", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r'<[^>]+>', '', cleaned).strip()

async def web_search(query: str, security_filter: bool = True) -> list:
    results = []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as http_client:
            response = await http_client.get(f"https://html.duckduckgo.com/html/?q={query}", headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                for result in soup.select(".result, .web-result")[:8]:
                    title_elem = result.select_one(".result__title a, .result__a, a")
                    snippet_elem = result.select_one(".result__snippet, .snippet")
                    title = title_elem.get_text(strip=True) if title_elem else ""
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    link = title_elem.get("href", "") if title_elem else ""
                    if security_filter:
                        title = sanitize_search_result(title)
                        snippet = sanitize_search_result(snippet)
                        if "[FILTERED]" in title or "[FILTERED]" in snippet:
                            continue
                    if title:
                        results.append({"title": title, "snippet": snippet, "url": link})
    except Exception as e:
        logger.warning(f"Search failed: {e}")
    return results

# ============================================================
# BUILT-IN TEMPLATES
# ============================================================
BUILTIN_TEMPLATES = [
    {"id": "screen-on-download", "title": "Keep screen on during download, then shutdown", "description": "Monitors downloads, keeps display awake, shuts down when complete", "platform": "linux", "level": "user", "prompt": "Keep my laptop screen on and prevent sleep until all downloads complete, then shutdown gracefully", "builtin": True},
    {"id": "cleanup-temp", "title": "Clean temporary files", "description": "Remove temp files and reclaim disk space", "platform": "linux", "level": "user", "prompt": "Clean all temporary files and caches safely", "builtin": True},
    {"id": "system-info", "title": "Full system diagnostics", "description": "CPU, RAM, disk, network info", "platform": "linux", "level": "user", "prompt": "Generate a comprehensive system diagnostic report", "builtin": True},
    {"id": "kill-process", "title": "Kill unresponsive process", "description": "Find and kill a hung process", "platform": "linux", "level": "user", "prompt": "List processes sorted by memory, then kill a specified one", "builtin": True},
    {"id": "batch-rename", "title": "Batch rename files", "description": "Rename files with pattern", "platform": "linux", "level": "user", "prompt": "Batch rename files in a folder with sequential numbering", "builtin": True},
    {"id": "git-cleanup", "title": "Git branch cleanup", "description": "Remove merged local branches", "platform": "linux", "level": "user", "prompt": "Delete all local git branches that have been merged into main", "builtin": True},
]

VOICE_PRESETS = [
    {"id": "default-female", "name": "Aria (Female)", "description": "Clear, professional female voice", "settings": {"lang": "en-US", "rate": 1.0, "pitch": 1.1, "voiceURI": "female"}},
    {"id": "baby-female", "name": "Luna (Baby)", "description": "Soft, gentle baby-like female voice", "settings": {"lang": "en-US", "rate": 0.85, "pitch": 1.5, "voiceURI": "female"}},
    {"id": "default-male", "name": "Atlas (Male)", "description": "Deep, authoritative male voice", "settings": {"lang": "en-US", "rate": 0.95, "pitch": 0.85, "voiceURI": "male"}},
    {"id": "neutral", "name": "System Default", "description": "Browser default voice", "settings": {"lang": "en-US", "rate": 1.0, "pitch": 1.0, "voiceURI": ""}},
]

# ============================================================
# ROUTES: HEALTH & CHAT
# ============================================================
@app.get("/api/health")
async def health_check():
    config = await get_config()
    return {
        "status": "healthy",
        "service": config.get("assistant_name", "Aradhya"),
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "storage": "mongodb" if db is not None else "memory",
        "workspace_path": config.get("workspace_path", DEFAULT_WORKSPACE_PATH),
        "model_provider": config.get("model_provider", DEFAULT_MODEL_PROVIDER),
    }

@app.post("/api/chat")
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    config = await get_config()
    
    await _insert_one("messages", {"session_id": session_id, "role": "user", "content": req.message, "mode": req.mode, "created_at": datetime.now(timezone.utc).isoformat()})

    workspace_context = ""
    ws_path = req.workspace_path or config.get("workspace_path", "")
    if ws_path and os.path.isdir(ws_path):
        workspace_context = f"Current workspace: {ws_path}"

    if req.mode == "command":
        response_text = await generate_command(req.message, "linux", "user")
    elif req.mode == "search":
        search_results = await web_search(req.message, config.get("security_filter", True))
        if search_results:
            context = "\n".join([f"- {r['title']}: {r['snippet']}" for r in search_results])
            prompt = f"User asked: {req.message}\nWeb results:\n{context}\nSummarize and answer."
            response_text = await get_llm_response(prompt, session_id)
        else:
            response_text = await get_llm_response(f"Answer this question from knowledge: {req.message}", session_id)
    else:
        sys_prompt = AGENTIC_SYSTEM_PROMPT.replace("{workspace_context}", workspace_context)
        response_text = await get_llm_response(req.message, session_id, sys_prompt)

    await _insert_one("messages", {"session_id": session_id, "role": "assistant", "content": response_text, "mode": req.mode, "created_at": datetime.now(timezone.utc).isoformat()})
    return {"session_id": session_id, "response": response_text, "mode": req.mode}

@app.get("/api/chat/history")
async def get_chat_history(session_id: str):
    messages = await _find_many("messages", {"session_id": session_id}, sort_key="created_at", limit=200)
    return {"session_id": session_id, "messages": messages}

# ============================================================
# ROUTES: WORKSPACE / FILE SYSTEM
# ============================================================
@app.post("/api/workspace/tree")
async def workspace_tree(req: FileReadRequest):
    target = Path(req.path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")
    
    def build_tree(p: Path, depth=0, max_depth=3, max_items=200):
        items = []
        if depth > max_depth:
            return items
        try:
            entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            for i, entry in enumerate(entries):
                if i >= max_items:
                    items.append({"name": f"... ({len(list(p.iterdir())) - max_items} more)", "type": "truncated", "path": ""})
                    break
                if entry.name.startswith('.') and entry.name not in ('.env', '.gitignore'):
                    continue
                if entry.name in ('node_modules', '__pycache__', 'venv', '.git', 'dist', 'build'):
                    items.append({"name": entry.name, "type": "dir_collapsed", "path": str(entry)})
                    continue
                node = {"name": entry.name, "type": "dir" if entry.is_dir() else "file", "path": str(entry)}
                if entry.is_dir():
                    node["children"] = build_tree(entry, depth + 1, max_depth, max_items)
                else:
                    try:
                        node["size"] = entry.stat().st_size
                    except OSError:
                        node["size"] = 0
                items.append(node)
        except PermissionError:
            items.append({"name": "[Permission Denied]", "type": "error", "path": ""})
        return items
    
    tree = build_tree(target)
    return {"path": str(target), "tree": tree}

@app.post("/api/workspace/read")
async def workspace_read(req: FileReadRequest):
    target = Path(req.path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"path": str(target), "content": content, "size": target.stat().st_size, "name": target.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/workspace/write")
async def workspace_write(req: FileWriteRequest):
    config = await get_config()
    if config.get("sandbox_mode", True):
        raise HTTPException(status_code=403, detail="Sandbox mode is ON. Disable it in settings to write files.")
    target = Path(req.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.content, encoding="utf-8")
    return {"path": str(target), "status": "written", "size": len(req.content)}

@app.post("/api/workspace/diff")
async def workspace_diff(req: DiffRequest):
    target = Path(req.path)
    old_content = ""
    if target.exists():
        old_content = target.read_text(encoding="utf-8", errors="replace")
    
    import difflib
    diff = list(difflib.unified_diff(
        old_content.splitlines(keepends=True),
        req.new_content.splitlines(keepends=True),
        fromfile=f"a/{target.name}",
        tofile=f"b/{target.name}",
    ))
    return {"path": str(target), "old_content": old_content, "new_content": req.new_content, "diff": "".join(diff), "has_changes": len(diff) > 0}

# ============================================================
# ROUTES: SHELL EXECUTION
# ============================================================
@app.post("/api/shell/execute")
async def shell_execute(req: ShellRequest):
    config = await get_config()
    if config.get("sandbox_mode", True):
        raise HTTPException(status_code=403, detail="Sandbox mode is ON. Disable it in settings to run shell commands.")
    
    cwd = req.cwd or config.get("workspace_path", DEFAULT_WORKSPACE_PATH)
    try:
        result = subprocess.run(
            req.command, shell=True, capture_output=True, text=True,
            timeout=30, cwd=cwd
        )
        return {
            "command": req.command,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"command": req.command, "stdout": "", "stderr": "Command timed out after 30s", "exit_code": -1, "success": False}
    except Exception as e:
        return {"command": req.command, "stdout": "", "stderr": str(e), "exit_code": -1, "success": False}

@app.post("/api/shell/draft")
async def shell_draft(req: CommandRequest):
    response_text = await generate_command(req.description, req.platform, req.level)
    return {"command": response_text, "platform": req.platform, "level": req.level}

# ============================================================
# ROUTES: GIT INTEGRATION
# ============================================================
def run_git(args: list, cwd: str) -> dict:
    try:
        result = subprocess.run(["git"] + args, capture_output=True, text=True, timeout=15, cwd=cwd)
        return {"stdout": result.stdout.strip(), "stderr": result.stderr.strip(), "exit_code": result.returncode, "success": result.returncode == 0}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1, "success": False}

@app.post("/api/git")
async def git_action(req: GitRequest):
    config = await get_config()
    cwd = req.cwd or config.get("workspace_path", DEFAULT_WORKSPACE_PATH)
    args = req.args or {}

    if req.action == "status":
        return run_git(["status", "--porcelain"], cwd)
    elif req.action == "branch":
        return run_git(["branch", "-a"], cwd)
    elif req.action == "current_branch":
        return run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    elif req.action == "log":
        return run_git(["log", "--oneline", "-20"], cwd)
    elif req.action == "diff":
        file_path = args.get("file", "")
        cmd = ["diff"] + ([file_path] if file_path else [])
        return run_git(cmd, cwd)
    elif req.action == "diff_staged":
        return run_git(["diff", "--staged"], cwd)
    elif req.action == "checkout":
        branch = args.get("branch", "")
        if not branch:
            raise HTTPException(status_code=400, detail="Branch name required")
        return run_git(["checkout", branch], cwd)
    elif req.action == "create_branch":
        branch = args.get("branch", "")
        if not branch:
            raise HTTPException(status_code=400, detail="Branch name required")
        return run_git(["checkout", "-b", branch], cwd)
    elif req.action == "stage":
        files = args.get("files", ["."])
        return run_git(["add"] + files, cwd)
    elif req.action == "commit":
        message = args.get("message", "")
        if not message:
            raise HTTPException(status_code=400, detail="Commit message required")
        return run_git(["commit", "-m", message], cwd)
    elif req.action == "push":
        remote = args.get("remote", "origin")
        branch = args.get("branch", "")
        cmd = ["push", remote] + ([branch] if branch else [])
        return run_git(cmd, cwd)
    elif req.action == "auto_commit_message":
        diff_result = run_git(["diff", "--staged"], cwd)
        if not diff_result["stdout"]:
            diff_result = run_git(["diff"], cwd)
        if diff_result["stdout"]:
            prompt = f"Generate a concise, conventional git commit message for these changes. Return ONLY the commit message, no explanation:\n\n{diff_result['stdout'][:3000]}"
            msg = await get_llm_response(prompt, f"git-{uuid.uuid4().hex[:8]}")
            return {"stdout": msg.strip().strip('"').strip("'"), "success": True}
        return {"stdout": "No changes detected", "success": False}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown git action: {req.action}")

# ============================================================
# ROUTES: MODELS (OLLAMA)
# ============================================================
@app.get("/api/models/list")
async def list_models():
    models = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            response = await http_client.get("http://127.0.0.1:11434/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = [{"name": m.get("name", ""), "size": m.get("size", 0), "modified": m.get("modified_at", "")} for m in data.get("models", [])]
    except Exception:
        pass
    
    cloud_models = [
        {"name": "gpt-4.1", "provider": "openai", "type": "cloud"},
        {"name": "gpt-4.1-mini", "provider": "openai", "type": "cloud"},
        {"name": "gpt-5.2", "provider": "openai", "type": "cloud"},
        {"name": "claude-4-sonnet-20250514", "provider": "anthropic", "type": "cloud"},
    ]
    return {"ollama_available": len(models) > 0, "local_models": models, "cloud_models": cloud_models}

@app.post("/api/models/select")
async def select_model(data: dict):
    model_name = data.get("model_name")
    provider = data.get("provider", "openai")
    if not model_name:
        raise HTTPException(status_code=400, detail="model_name required")
    await _update_one("settings", {"key": "global"}, {"model_name": model_name, "model_provider": provider}, upsert=True)
    return {"status": "ok", "model_name": model_name, "provider": provider}

# ============================================================
# ROUTES: TEMPLATES
# ============================================================
@app.get("/api/command/templates")
async def get_command_templates():
    custom = await _find_many("templates", limit=100)
    return {"templates": BUILTIN_TEMPLATES + custom}

@app.post("/api/command/templates")
async def create_template(req: TemplateCreate):
    template = {
        "id": f"custom-{uuid.uuid4().hex[:8]}",
        "title": req.title,
        "description": req.description,
        "prompt": req.prompt,
        "platform": req.platform,
        "level": req.level,
        "builtin": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await _insert_one("templates", template)
    return template

@app.delete("/api/command/templates/{template_id}")
async def delete_template(template_id: str):
    deleted_count = await _delete_one("templates", {"id": template_id})
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found or is built-in")
    return {"status": "deleted"}

# ============================================================
# ROUTES: VOICE, SEARCH, SETTINGS
# ============================================================
@app.post("/api/command/generate")
async def generate_command_endpoint(req: CommandRequest):
    response_text = await generate_command(req.description, req.platform, req.level)
    return {"command": response_text, "platform": req.platform, "level": req.level}

@app.post("/api/search")
async def search(req: SearchRequest):
    results = await web_search(req.query, req.security_filter)
    return {"query": req.query, "results": results, "security_filter": req.security_filter, "count": len(results)}

@app.get("/api/voice/presets")
async def get_voice_presets():
    return {"presets": VOICE_PRESETS}

@app.get("/api/settings")
async def get_settings():
    config = await get_config()
    config.pop("_id", None)
    return config

@app.put("/api/settings")
async def update_settings(req: SettingsUpdate):
    update_data = {k: v for k, v in req.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    await _update_one("settings", {"key": "global"}, update_data, upsert=True)
    settings = await _find_one("settings", {"key": "global"})
    return settings
