import os
import requests


import sys
sys.stdout.reconfigure(encoding='utf-8')

API_KEY = "pk_ZArpNUcoSkmzcAADT-LmMQ"  # 🔑 add this

OUTPUT_DIR = "assets/stack_logos"
os.makedirs(OUTPUT_DIR, exist_ok=True)

STACK_LOGOS = {
    # =========================
    # 🟢 COMPANY LOGOS (Logo.dev)
    # =========================
    "openai": {"domain": "openai.com"},
    "cerebras": {"domain": "cerebras.ai"},
    "deepseek": {"domain": "deepseek.com"},
    "clerk": {"domain": "clerk.com"},
    "supabase": {"domain": "supabase.com"},
    "postgresql": {"domain": "postgresql.org"},
    "railway": {"domain": "railway.app"},
    "tavily": {"domain": "tavily.com"},

    # =========================
    # ⚡ SIMPLE ICONS (CDN)
    # =========================
    "fastapi": {"simple": "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/fastapi.svg"},
    "react": {"simple": "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/react.svg"},
    "vite": {"simple": "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/vite.svg"},
    "typescript": {"simple": "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/typescript.svg"},
    "tailwind": {"simple": "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/tailwindcss.svg"},

    # =========================
    # 🧠 LANGCHAIN ECOSYSTEM
    # =========================
    "langgraph": {"simple": "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/langchain.svg"},
    "langsmith": {"simple": "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/langchain.svg"},
    "langchain": {"simple": "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/langchain.svg"},
}

# =========================
# ❌ NO LOGO ITEMS (fallback)
# =========================
NO_LOGO = [
    "asyncpg",
    "pgvector",
    "bm25",
    "minilm",
    "tinybert",
    "qwen"
]


def download_logo(name, config):
    filepath = os.path.join(OUTPUT_DIR, f"{name}.png")

    try:
        if "domain" in config:
            url = f"https://img.logo.dev/{config['domain']}?token={API_KEY}&size=200&format=png"

        elif "simple" in config:
            url = config["simple"]

        else:
            print(f"⚠️ No source for {name}")
            return

        res = requests.get(url, timeout=10)

        if res.status_code == 200 and res.content:
            with open(filepath, "wb") as f:
                f.write(res.content)
            print(f"✅ {name}")
        else:
            print(f"❌ {name} ({res.status_code})")

    except Exception as e:
        print(f"⚠️ {name}: {e}")


# =========================
# 🚀 RUN DOWNLOADS
# =========================
for name, config in STACK_LOGOS.items():
    download_logo(name, config)


# =========================
# 🟡 HANDLE NO-LOGO ITEMS
# =========================
for name in NO_LOGO:
    print(f"⚠️ Skipped (no official logo): {name}")

print("\nDone 🚀")