---
title: "DeepSeek Harness Integration Plan"
version: "1.0.0"
status: "READY_FOR_EXECUTION"
target_repo: "yabigdd-9/WEBSITE-AUDITOR"
branch: "integration/deepseek-harness"
objective: >
  Establish a parallel agentic reasoning layer (DeepSeek Harness) alongside 
  the deterministic Hermes/mm core. Phase A focuses on Shadow Mode validation 
  with zero external side effects and strict security boundaries.
author: "AI Architect Assistant"
date: "2026-09-19"
---

# DeepSeek Harness Integration Plan

## 1. Executive Summary
This plan outlines the safe introduction of **DeepSeek Harness** into the existing `WEBSITE-AUDITOR` ecosystem. The goal is to leverage LLM capabilities for nuanced UX/Audit analysis and self-correction without compromising the stability of the Python-based deterministic pipeline (`./mm`). 

**Core Principles:**
1. **Deterministic Core Remains King:** `./mm` handles data extraction, scoring, and storage. Harness handles interpretation and critique.
2. **Zero Trust Execution:** Harness runs in isolation. No direct DB writes. No email sending. No secret access.
3. **Cost Control:** Local inference only (Ollama/Llama.cpp). Paid APIs are forbidden.
4. **Human-in-the-Loop:** All outputs require human ratification before entering the main outreach queue.

## 2. Architecture Overview

```mermaid
graph TD
    subgraph "Control Plane (Hermes)"
        Scheduler[Scheduler & Orchestrator]
        MM_CLI[./mm Deterministic CLI]
        DB[(SQLite Master DB)]
    end

    subgraph "Parallel Layer (DeepSeek Harness)"
        AgentTeam[Agent Team: Auditor/Critic/Judge]
        Wrapper[Safe mm Tool Bridge]
        Browser[Playwright MCP Lane]
        LocalLLM[Local Inference Engine]
    end

    Scheduler -->|Trigger Job| AgentTeam
    AgentTeam -->|Call Tools| Wrapper
    Wrapper -->|Read-Only Exec| MM_CLI
    Wrapper -->|Query| DB
    AgentTeam -->|Inspect Site| Browser
    AgentTeam -->|Reasoning| LocalLLM
    AgentTeam -->|Output Drafts| Outputs[/outputs/shadow/]
    Outputs -->|Review Queue| HumanGate{Human Approval}
    HumanGate -->|Approved| Scheduler
