# Project Guidance & Agent Instructions

## Core Tech Stack
* **Language/Runtime:** Python 3.10+
* **Frameworks:** Flask, Pytest, Docker Compose
* **Trading/Quant Domain:** cTrader OpenAPI, Smart Money Concepts (FVG, Order Blocks, Liquidity Sweeps)

## Workflow & Development Rules
1. **Test-Driven Modifications:** 
   * Always run `pytest` before and after making code changes.
   * Ensure tests pass before making git commits.
2. **Atomic Commits:** 
   * Issue concise, focused git commits after each passing subsystem test using Conventional Commit format (e.g., `fix: ...`, `feat: ...`, `refactor: ...`).
3. **Import Safety:** 
   * Avoid circular dependencies between `src/app.py`, `src/views`, and `src/api/routes`.
   * Use package-safe relative or absolute imports (`from src... import ...`).
4. **Environment & Dependencies:**
   * Do not commit secrets, `.env` files, or API credentials.
   * Verify system dependencies (such as `pkg-config` and `libssl-dev`) when dealing with Rust or C extensions.

## Standard Commands
* **Run Tests:** `pytest -v`
* **Single Test File:** `pytest tests/test_gateway_routes.py`
* **Check Syntax/Imports:** `python -m compileall src`
* **Run Local Server:** `flask run --port=5000`
