# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository is a fresh start for a football (soccer) analytics project covering the 2026 season. It currently contains only a placeholder `main.py` (empty) — there is no established architecture, dependencies, or conventions yet. When adding the first real code, use your judgment to set up sensible structure (e.g. a package layout, dependency manifest such as `requirements.txt` or `pyproject.toml`, and tests) rather than assuming any pre-existing pattern.

## Environment

- Python 3.13 (see `venv/pyvenv.cfg`).
- A virtual environment already exists at `venv/`. Activate it before installing packages or running scripts:
  - PowerShell: `venv\Scripts\Activate.ps1`
  - Bash: `source venv/Scripts/activate`
- No packages are installed yet beyond `pip`. No dependency manifest exists — create one (e.g. `requirements.txt`) as soon as the project takes on dependencies.
