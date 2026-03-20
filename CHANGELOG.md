# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-03-20

### Added

- **Remote execution bridge** — UDP multicast discovery + TCP command channel to the UE 5.7 Python Editor Script Plugin (`ue_eyes/remote_exec.py`)
- **Screenshot capture** — `ue-eyes snap` CLI command captures viewport frames from a running UE editor session and saves them to disk (`ue_eyes/capture.py`)
- **Camera enumeration** — `ue-eyes cameras` CLI command lists all camera actors present in the active level (`ue_eyes/cameras.py`)
- **Connectivity check** — `ue-eyes ping` CLI command verifies the editor is reachable and returns latency
- **Image scoring** — Pixel-level and perceptual comparison metrics (SSIM, MSE, histogram) between reference and captured images (`ue_eyes/scoring/metrics.py`, `compare.py`)
- **Rubric system** — Declarative pass/fail criteria applied to scoring results (`ue_eyes/scoring/rubric.py`)
- **Research experiment loop** — Structured parameter sweep runner with result tracking for systematic visual QA (`ue_eyes/experiment/`)
- **Configuration** — TOML-based project configuration with sane defaults (`ue_eyes/config.py`, `ue-eyes.example.toml`)
- **Optional C++ plugin** — UE 5.7 plugin (`plugin/UEEyes/`) providing additional editor-side utilities
- **Claude Code skills** — Agent skill definitions under `skills/` for use with Claude Code
- **Full test suite** — 204 pytest unit tests covering all modules; all tests mock the UE connection so no editor is required (`tests/`)
- **CI/CD** — GitHub Actions workflows for automated testing on push/PR and PyPI release on tag

[Unreleased]: https://github.com/Ancient23/ue-eyes/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Ancient23/ue-eyes/releases/tag/v0.1.0
