"""
Prompt Loader & Manager for AdversarialIQ
Centralizes dynamic loading, safe interpolation, listing, and editing of all prompts
located in the project-root `prompts/` folder.
"""

from datetime import datetime
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("PromptLoader")

# Root directory for all prompt files
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"


def _safe_interpolate(template_str: str, **kwargs) -> str:
    """
    Safely substitutes {key} placeholders in a prompt template with kwargs values.
    Unlike str.format(), this never raises KeyError or ValueError on unescaped JSON/code braces.
    """
    if not kwargs:
        return template_str
    
    result = template_str
    for key, val in kwargs.items():
        placeholder = "{" + str(key) + "}"
        if placeholder in result:
            result = result.replace(placeholder, str(val))
    return result


def load_prompt(prompt_rel_path: str, default: Optional[str] = None, **kwargs) -> str:
    """
    Loads a prompt file from the `prompts/` directory and performs safe variable substitution.
    
    Args:
        prompt_rel_path: Relative path inside prompts/ (e.g., 'tribunal/bull_system.txt')
        default: Fallback text if file does not exist on disk
        **kwargs: Key-value pairs to substitute for {key} in the prompt template
    
    Returns:
        Formatted prompt string ready for LLM generation.
    """
    file_path = PROMPTS_DIR / prompt_rel_path
    content = ""
    
    try:
        if file_path.is_file():
            content = file_path.read_text(encoding="utf-8")
        elif default is not None:
            content = default
        else:
            logger.warning(f"Prompt file not found and no default provided: {file_path}")
            content = f"[PROMPT FILE MISSING: {prompt_rel_path}]"
    except Exception as e:
        logger.error(f"Error reading prompt file {file_path}: {e}")
        content = default or f"[ERROR LOADING PROMPT: {e}]"

    return _safe_interpolate(content, **kwargs)


def read_prompt_raw(prompt_rel_path: str) -> str:
    """Reads raw un-interpolated prompt template from disk."""
    file_path = PROMPTS_DIR / prompt_rel_path
    if not file_path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {prompt_rel_path}")
    return file_path.read_text(encoding="utf-8")


def save_prompt_raw(prompt_rel_path: str, content: str) -> bool:
    """Saves updated prompt template text to disk."""
    # Prevent directory traversal
    clean_path = Path(prompt_rel_path)
    if ".." in clean_path.parts:
        raise ValueError("Invalid relative path containing '..'")
    
    target_file = PROMPTS_DIR / clean_path
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(content, encoding="utf-8")
    logger.info(f"Updated prompt file: {target_file}")
    return True


def list_prompts() -> List[Dict[str, Any]]:
    """
    Lists all available prompt files in prompts/ with metadata.
    """
    if not PROMPTS_DIR.exists():
        return []

    items = []
    for root, _, files in os.walk(PROMPTS_DIR):
        for f in sorted(files):
            if f.startswith(".") or f.lower() == "readme.md":
                continue
            full_path = Path(root) / f
            rel_path = full_path.relative_to(PROMPTS_DIR).as_posix()
            parts = rel_path.split("/")
            category = parts[0] if len(parts) > 1 else "general"
            
            try:
                stat = full_path.stat()
                content = full_path.read_text(encoding="utf-8", errors="replace")
                # Extract first non-empty line as brief summary
                lines = [l.strip() for l in content.splitlines() if l.strip()]
                preview = lines[0][:90] if lines else ""
                
                # Extract variables like {symbol}, {price}
                vars_found = sorted(list(set(re.findall(r"\{([a-zA-Z0-9_]+)\}", content))))

                items.append({
                    "name": rel_path,
                    "filename": f,
                    "category": category,
                    "size_bytes": stat.st_size,
                    "char_count": len(content),
                    "preview": preview,
                    "variables": vars_found,
                    "last_modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })
            except Exception as e:
                logger.debug(f"Error inspecting prompt file {full_path}: {e}")

    return sorted(items, key=lambda x: (x["category"], x["name"]))
