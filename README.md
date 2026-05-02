<div align="center">
  <h1>🚀 Vera AI Engagement Engine</h1>
  <p><strong>A deterministic, rule-based merchant engagement system built for the magicpin AI Challenge.</strong></p>

  [![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
  [![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
</div>

---

## 📌 Overview

**Vera AI** is a highly generalizable, LLM-free backend engine designed to ingest merchant, customer, and trigger data to generate **actionable, personalized engagement messages**.

Moving away from unpredictable LLM inference, this engine guarantees **100% deterministic outputs** using a highly structured **FACT + IMPACT + ACTION** templating system. It passes the strictest idempotency, auto-reply, and hostile handling tests required by the magicpin LLM Judge Simulator.

## ✨ Key Features

- **🛡️ Deterministic Decision Engine**: Zero hallucinations. Every output is grounded safely in the ingested JSON payload using robust fallback templates.
- **🔄 Strict Idempotency**: Safe `/v1/context` ingestion. Duplicate contexts are ignored without throwing HTTP 409 conflicts, ensuring stability in retry loops.
- **💬 Smart Reply Handler**: Built-in 3-step escalation for auto-replies (`Send -> Wait -> End`) and immediate conversation closure on hostile inputs.
- **⚡ High Performance**: Written in **FastAPI** with `pydantic` validation. Handles hundreds of simulated requests per second.
- **🎯 Dynamic Personalization**: Messages automatically adapt based on time elapsed since the last visit, current active offers, available booking slots, and localized performance metrics.

---

## 🏗️ Architecture

1. **Context Store**: In-memory storage for categories, merchants, customers, and triggers with strict versioning logic.
2. **Validator**: Pre-flight checks on all incoming contexts.
3. **Trigger Dispatcher**: Prioritizes triggers based on ROI/urgency scores.
4. **Message Generator**: Synthesizes the exact text body and applies the `FACT + IMPACT + ACTION` rule.
5. **CTA Engine**: Maps trigger categories to optimal interactive UI elements (Binary Yes/No, Multi-Choice, Open-ended).

---

## 🚀 Local Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/AyushPrakash414/Vera-ai.git
   cd Vera-ai
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the server:**
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
   ```

4. **Health Check:**
   Navigate to `http://localhost:8080/v1/healthz` to verify the system is running.

---

## 🌍 Deployment (Render)

This application is fully prepared for zero-config deployment on **Render** Web Services.

- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

---

## 📡 API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/v1/healthz` | System health and loaded context count. |
| `GET` | `/v1/metadata` | Engine details and supported model capabilities. |
| `POST` | `/v1/context` | Idempotent upsert of Categories, Merchants, Customers, and Triggers. |
| `POST` | `/v1/tick` | Evaluates triggers and returns the highest priority action for a merchant. |
| `POST` | `/v1/reply` | Handles merchant/customer responses and executes the next conversational step. |

---

<div align="center">
  <p>Built for the <strong>magicpin Vera AI Challenge</strong>.</p>
</div>
