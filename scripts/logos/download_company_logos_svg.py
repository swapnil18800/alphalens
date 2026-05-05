import os
import requests


import sys
sys.stdout.reconfigure(encoding='utf-8')

OUTPUT_DIR = "assets/stack_logos_svg"
os.makedirs(OUTPUT_DIR, exist_ok=True)

STACK_LOGOS = {
    # =========================
    # 🟢 COMPANIES (SVG via geticon)
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
    # ⚡ SIMPLE ICONS (SVG)
    # =========================
    "fastapi": {"simple": "fastapi"},
    "react": {"simple": "react"},
    "vite": {"simple": "vite"},
    "typescript": {"simple": "typescript"},
    "tailwind": {"simple": "tailwindcss"},
    "langchain": {"simple": "langchain"},

    # 🧠 alias
    "langgraph": {"simple": "langchain"},
    "langsmith": {"simple": "langchain"},
}

NO_LOGO = [
    "asyncpg",
    "pgvector",
    "bm25",
    "minilm",
    "tinybert",
    "qwen"
]


def download_logo(name, config):
    filepath = os.path.join(OUTPUT_DIR, f"{name}.svg")

    try:
        # COMPANY → geticon (SVG)
        if "domain" in config:
            url = f"https://geticon.dev/api/icon?domain={config['domain']}&format=svg"

        # SIMPLE ICONS → SVG CDN
        elif "simple" in config:
            url = f"https://cdn.simpleicons.org/{config['simple']}"

        else:
            print(f"⚠️ No source: {name}")
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


# download all
for name, config in STACK_LOGOS.items():
    download_logo(name, config)

# no-logo items
for name in NO_LOGO:
    print(f"⚠️ No official logo: {name}")

print("\nDone 🚀")