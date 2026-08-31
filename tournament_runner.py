#!/usr/bin/env python3
"""tournament_runner.py — Pattern test for Daytona + ORAK 2048 + OpenRouter.

Creates ONE Daytona sandbox, runs ONE model playing 2048, collects the score.
This is a one-shot test, not the full tournament.
"""

import os
import re
import sys
import textwrap
import time

from daytona import Daytona, DaytonaConfig, CreateSandboxBaseParams

# ── Hardcoded test credentials (one-shot test) ──────────────────────────
OPENROUTER_API_KEY = "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"
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
MODEL_NAME = "nvidia/nemotron-3-ultra-550b-a55b:free"

# ── Sandbox configuration ───────────────────────────────────────────────
SANDBOX_NAME = f"hackorak-test-{int(time.time())}"
SANDBOX_LANGUAGE = "python"
DOMAIN_ALLOW_LIST = "openrouter.ai,github.com,pypi.org,files.pythonhosted.org,openaipublic.blob.core.windows.net"
AUTO_STOP_INTERVAL = 3600  # seconds

# ── ORAK game configuration ─────────────────────────────────────────────
MAX_STEPS = 10
GAME = "TwentyFourtyEight"
INPUT_MODALITY = "text"

TEST_CONFIG_YAML = textwrap.dedent(f"""\
    env_name: "{GAME}"
    log_path: "logs"
    runner:
      max_steps: {MAX_STEPS}
    env:
      task: "Merge Tiles to Reach the Target"
      show_graphic: false
      target_tile: 2048
      input_modality: "{INPUT_MODALITY}"

    agent:
      llm_name: "{MODEL_NAME}"
      api_key: "{OPENROUTER_API_KEY}"
      api_base_url: "{OPENROUTER_API_BASE}"
      temperature: 0.0
      repetition_penalty: 1.0
      agent_type: zeroshot_agent
      prompt_path: mcp_agent_servers.twenty_fourty_eight.prompts.text.zeroshot_agent

    game_server: "src/mcp_game_servers/twenty_fourty_eight/server.py"
    agent_server: "src/mcp_agent_servers/twenty_fourty_eight/server.py"
""")


def main() -> None:
    # ── Step 1: Create sandbox ──────────────────────────────────────────
    print("Creating Daytona sandbox...")
    d = Daytona(DaytonaConfig(target="eu"))
    params = CreateSandboxBaseParams(
        name=SANDBOX_NAME,
        language=SANDBOX_LANGUAGE,
        domain_allow_list=DOMAIN_ALLOW_LIST,
        auto_stop_interval=AUTO_STOP_INTERVAL,
        ephemeral=True,
    )
    sb = d.create(params, timeout=120)
    print(f"Sandbox created: {sb.id}")

    # Sandbox writable home directory (not /workspace which is read-only)
    home = sb.get_user_home_dir()
    wsp = f"{home}/workspace"

    try:
        # ── Step 2: Clone repo & install deps ───────────────────────────
        print(f"Cloning HackORAK repo (release branch) into {wsp}...")
        sb.git.clone(
            "https://github.com/nemani/HackORAK.git",
            wsp,
            branch="fm/tournament-runner",
        )

        print("Installing uv...")
        r = sb.process.exec(
            f"cd {wsp} && pip install uv 2>&1 | tail -3",
            timeout=60,
        )
        print(r.artifacts.stdout)

        print("Running uv sync...")
        r = sb.process.exec(
            f"cd {wsp} && uv sync 2>&1 | tail -10",
            timeout=300,
        )
        print(r.artifacts.stdout)

        # The lockfile may be platform-specific; install missing deps
        # The ORAK codebase imports many packages at module level;
        # install everything the 2048 text path needs.
        print("Installing core Python deps...")
        r = sb.process.exec(
            f"cd {wsp} && uv pip install omegaconf Pillow gymnasium openai "
            f"tiktoken anthropic transformers google-genai google-auth "
            f"termcolor langchain-openai langchain-chroma 2>&1 | tail -12",
            timeout=300,
        )
        print(r.artifacts.stdout)

        # Try pygame separately — may fail on Python 3.14+ (no wheels, no
        # SDL headers) but the game code now handles that gracefully.
        print("Installing pygame (optional, may fail)...")
        r = sb.process.exec(
            f"cd {wsp} && uv pip install pygame 2>&1 | tail -5",
            timeout=120,
        )
        print(r.artifacts.stdout)

        # ── Step 3: Write config and run the model ──────────────────────
        print("Writing game config...")
        sb.process.exec(f"mkdir -p {wsp}/configs", timeout=10)
        sb.fs.upload_file(TEST_CONFIG_YAML.encode(), f"{wsp}/configs/test.yaml")

        # Create key file required by memory.py module-level setup_openai()
        print("Creating API key file for memory module...")
        sb.process.exec(
            f"mkdir -p {wsp}/src/mcp_agent_servers/keys/openai-key",
            timeout=10,
        )
        sb.fs.upload_file(
            f"{OPENROUTER_API_KEY}\n".encode(),
            f"{wsp}/src/mcp_agent_servers/keys/openai-key/key.env",
        )

        # Verify the config was written
        r = sb.process.exec(f"cat {wsp}/configs/test.yaml", timeout=10)
        print("Config written:")
        print(r.artifacts.stdout)

        print("Starting ORAK 2048 game (background)...")
        logfile = "/tmp/game-run.log"
        sb.process.exec(
            f"nohup uv run python scripts/mcp_play_game.py"
            f" --config configs/test.yaml"
            f" > {logfile} 2>&1 &",
            cwd=wsp,
            timeout=15,
        )

        # Poll for completion: tail the log, look for Score: or
        # final_score.json.  Timeout after 30 min total.
        import time as _time
        deadline = _time.time() + 1800
        score = None
        _last_tail = None
        while _time.time() < deadline:
            _time.sleep(30)
            try:
                r = sb.process.exec(
                    f"tail -40 {logfile} 2>/dev/null || echo '<no log yet>'",
                    timeout=10,
                )
                tail = r.artifacts.stdout
                # Print only new content
                if tail.strip() and tail.strip() != "<no log yet>" and tail != _last_tail:
                    print(f"[{_time.strftime('%H:%M:%S')}] tail:\n{tail}")
                    _last_tail = tail
                # Detect crash: stop polling early
                if "Traceback (most recent call last)" in tail or \
                   "ModuleNotFoundError" in tail:
                    print("Game crashed — see traceback above.")
                    break
                # Check for score in log
                score_match = re.search(r"Score:\s*(-?\d+)", tail)
                if score_match:
                    score = int(score_match.group(1))
                    print("Game completed!")
                    break
                # Also check if final_score.json exists AND is non-empty
                r2 = sb.process.exec(
                    f"find logs -name final_score.json -newer {logfile}"
                    f" -size +4c 2>/dev/null | head -1",
                    timeout=10,
                )
                found = r2.artifacts.stdout.strip()
                if found:
                    r3 = sb.process.exec(f"cat {found}", timeout=10)
                    print(f"Score file: {r3.artifacts.stdout}")
                    import json as _json
                    try:
                        data = _json.loads(r3.artifacts.stdout)
                        score = data.get("score", 0)
                    except Exception:
                        pass
                    break
            except Exception as exc:
                print(f"(poll error: {exc})", file=sys.stderr)
        else:
            # Timed out — grab whatever we have
            print("Timed out waiting for game. Last log tail:")
            try:
                r = sb.process.exec(f"tail -60 {logfile}", timeout=10)
                print(r.artifacts.stdout)
            except Exception:
                pass

        if score is None:
            print("WARNING: No score found; defaulting to 0", file=sys.stderr)
            score = 0

        # ── Step 5: Print result ────────────────────────────────────────
        print(f"SCORE: {MODEL_NAME} = {score}")

    finally:
        # ── Cleanup ─────────────────────────────────────────────────────
        print("Cleaning up sandbox...")
        try:
            sb.delete()
        except Exception as exc:
            print(f"(sandbox delete failed: {exc}; ephemeral sandbox may "
                  f"auto-cleanup)", file=sys.stderr)
        print("Done.")


if __name__ == "__main__":
    main()