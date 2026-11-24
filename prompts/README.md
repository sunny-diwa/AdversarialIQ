# 📑 AdversarialIQ Prompt Registry (`prompts/`)

This directory houses **every LLM prompt and directive** utilized across the AdversarialIQ system—from complex multi-agent dialectical prosecution arguments to one-line system instructions.

All prompts are stored as plain text (`.txt`) files so they are **easy to inspect, audit, and modify directly**.

---

## 📂 Directory Layout

```
prompts/
├── chat/
│   ├── greeting_system.txt           # Agent greeting & capability overview
│   ├── news_synthesis_system.txt     # Breaking news & catalyst synthesis directive
│   ├── dossier_system.txt            # Main trader dossier, 19 tools definition & router
│   └── instructions_fallback.txt     # Fallback institutional persona prompt
├── tribunal/
│   ├── default_syndicate_system.txt  # Baseline syndicate agent system prompt
│   ├── bull_system.txt               # Agent Bull senior long prosecutor system directive
│   ├── bull_user.txt                 # Agent Bull market dossier input template
│   ├── bear_system.txt               # Agent Bear downside adversary system directive
│   ├── bear_user.txt                 # Agent Bear cross-examination input template
│   ├── judge_system.txt              # Chief Judge quantitative magistrate scoring directive
│   └── judge_user.txt                # Chief Judge trial transcript synthesis template
├── backtest/
│   ├── strategy_system.txt           # Quantitative engineer code generation system prompt
│   └── strategy_user.txt             # Strategy concept translation template
├── critic/
│   ├── critic_system.txt             # Quality Auditor & Senior Compliance Officer system prompt
│   └── critic_user.txt               # Audit feedback & self-correction directive
├── ecosystem/
│   └── gemini_grounding_user.txt     # Gemini supply chain graph extraction prompt
└── memory/
    └── reflection_block.txt          # Historical episodic post-mortem formatting template
```

---

## ⚡ How Prompts are Loaded

Prompts are dynamically resolved at runtime via `src.core.prompt_loader`:

```python
from src.core.prompt_loader import load_prompt

# 1. Simple loading
system_prompt = load_prompt("tribunal/bull_system.txt", symbol="NVDA", company_name="NVIDIA Corporation")

# 2. Template interpolation with safe bracket handling
# Variables inside curly braces like {symbol} or {price} are substituted safely.
# Unescaped JSON or code braces like {"tool": "name"} are preserved intact.
prompt = load_prompt("backtest/strategy_user.txt", symbol="NVDA", strategy_prompt="Buy when RSI < 30")
```

### 🔄 Live Reloading
Because prompts are loaded dynamically from disk during each request turn:
1. Any modification made to a file in `prompts/` **takes effect immediately**.
2. No backend server restart or recompilation is required.
3. Operators can tune phrasing, alter scoring thresholds, add tool guidelines, or adjust persona tone directly in these files.
