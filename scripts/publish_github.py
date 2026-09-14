"""Create this project's repository using Git Credential Manager. Never print or persist credentials.

Usage: python scripts/publish_github.py --check
       python scripts/publish_github.py --create
The script never pushes code. Review files, then use normal git push.
"""
import argparse
import os
import subprocess

import httpx

OWNER = "Pormer"
REPO = "review-lens"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--create", action="store_true")
    args = parser.parse_args()
    if not (args.check or args.create):
        parser.error("Choose --check or --create")
    credential = subprocess.run(
        ["git", "credential", "fill"],
        input=f"protocol=https\nhost=github.com\nusername={OWNER}\n\n",
        text=True, capture_output=True, timeout=30,
        env=os.environ | {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"},
    )
    fields = dict(line.split("=", 1) for line in credential.stdout.splitlines() if "=" in line)
    if credential.returncode or not fields.get("password"):
        raise SystemExit("GitHub sign-in is required in Git Credential Manager.")
    with httpx.Client(base_url="https://api.github.com", timeout=20,
                      headers={"Authorization": f"Bearer {fields['password']}", "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28"}) as client:
        user = client.get("/user")
        if user.status_code != 200 or user.json().get("login", "").casefold() != OWNER.casefold():
            raise SystemExit("Authenticated GitHub account does not match Pormer, or authentication failed.")
        print(f"Authenticated account: {OWNER}")
        existing = client.get(f"/repos/{OWNER}/{REPO}")
        if args.check:
            print(f"Repository status: {existing.status_code}")
            return
        if existing.status_code == 200:
            raise SystemExit("Repository already exists. Inspect it before attaching a remote or pushing.")
        if existing.status_code != 404:
            raise SystemExit(f"Repository check failed: HTTP {existing.status_code}")
        result = client.post("/user/repos", json={"name": REPO, "private": False,
                            "description": "리뷰렌즈: 근거 기반 상품 리뷰 분석 Agent · FastAPI + OpenAI Responses API",
                            "auto_init": False})
        if result.status_code != 201:
            raise SystemExit(f"Repository creation failed: HTTP {result.status_code}")
        print(result.json()["html_url"])


if __name__ == "__main__":
    main()
