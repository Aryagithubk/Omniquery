# 📂 OmniQuery Codebase: A Beginner's Guide

Welcome to the OmniQuery codebase! This document explains the folder structure, the purpose of important files, and how the core Agents work in simple, easy-to-understand words.

---

## 🏗️ Folder Structure Overview

Your project is built in Python and divided into logical modules. Everything important lives inside the `src/` (source) folder.

```text
company-rag/
├── config.yaml          # ⚙️ The master settings file (API keys, turning agents on/off)
├── main.py              # 🚀 The front door. Starts the web server and the Orchestrator.
└── src/                 # 📂 All the Python code lives here
    ├── agents/          # 🤖 The actual "Bots" that do specific jobs
    ├── api/             # 🌐 Web routing and data shapes (Schemas)
    ├── config/          # ⚙️ Python code to read the config.yaml file
    ├── core/            # 🧠 The Orchestrator (LangGraph graph, router, nodes)
    ├── ingestion/       # 📥 Code to read your Pdfs/Txt files and turn them into numbers
    ├── llm/             # 🗣️ Code that talks to local AI models (Ollama, vLLM, etc.)
    ├── retrieval/       # 🔎 Code to search for text inside documents
    ├── utils/           # 🛠️ Helper code (like formatting log messages nicely)
    └── vector_db/       # 🗄️ Code that connects to the database storing your PDFs (ChromaDB)
```

---

## 🤖 The `src/agents/` Folder

Think of **Agents** as specialized workers. You have a manager (the Orchestrator) who decides which worker gets the user's question.

### The Foundation
- **`base_agent.py`**: The blueprint. It says *"Every agent MUST have a way to calculate their confidence (`can_handle`) and a way to do their job (`execute`)."*
- **`agent_registry.py`**: The phonebook. When the server starts, all agents put their names in this registry so the Orchestrator knows they exist and are healthy.

### The Specialized Workers

#### 1. `doc_agent/agent.py` (The Document Reader)
- **What it does:** Reads through company PDFs, HR policies, and wikis to answer questions.
- **Important Methods:**
  - `initialize()`: Connects to the local database where your documents are stored.
  - `can_handle(query)`: Listens for words like *"policy"*, *"document"*, or *"procedure"*. If it hears them, it shouts: *"I am 90% confident I can answer this!"*
  - `execute(query)`: Uses AI to search the database, grabs the top 3 most relevant pages, and summarizes an answer.

#### 2. `db_agent/agent.py` (The Data Analyst)
- **What it does:** Looks at rows and columns in an SQL Database to answer math or data questions.
- **Important Methods:**
  - `initialize()`: Looks at your database and memorizes the names of all the columns (like *Name, Salary, Department*).
  - `can_handle(query)`: Listens for words like *"how many"*, *"average"*, or *"salary"*.
  - `execute(query)`: **(Step 1)** Translates English into SQL code. **(Step 2)** Runs the SQL code securely. **(Step 3)** Translates the numbers back into a friendly English sentence.

#### 3. `web_agent/agent.py` (The Googler)
- **What it does:** If the question is about the outside world (like "What is the weather?"), it searches the internet.

#### 4. `confluence_agent/agent.py` (The Wiki Reader)
- **What it does:** Specifically connects to Atlassian Confluence APIs to read internal company blog posts.

---

## 🧠 The `src/core/orchestrator/` Folder

This folder is the **Manager**. It takes the user's question, decides who to give it to, and pieces together the final answer.

- **`graph.py`**: The workflow map. It defines the exact path a question takes. *(E.g., Start -> Classify -> Execute -> Synthesize -> Finish)*.
- **`state.py`**: The clipboard. As the question moves through the workflow, the Orchestrator writes notes on this clipboard (e.g., *"WebAgent failed, trying DocAgent next"*).
- **`router.py`**: The interviewer. It asks all the agents: *"Who is most confident they can answer this question?"* and sorts them from highest to lowest score.

### The Nodes (Steps in the workflow)
Inside `core/orchestrator/nodes/`:
- **`preprocess.py`**: Cleans up bad grammar or spaces in the question.
- **`classify.py`**: Tags the question *(e.g. "Ah, this is a math question")* and calls the `router` to formulate a plan.
- **`execute.py`**: Hands the question to the highest-scoring Agent.
- **`synthesize.py`**: If multiple agents answered the question, it uses AI to combine their answers into one beautifully written paragraph.
- **`fallback.py`**: The safety net. If all agents fail or crash, this step catches the error and asks the LLM to just do its best guessing based on general knowledge.

---

## 🗣️ The `src/llm/` Folder

Everything in OmniQuery relies on a Large Language Model (LLM) to think. 
- **`provider_factory.py`**: A switchboard. It lets you easily swap between OpenAI, Anthropic, or a Local LLM (like Ollama or vLLM) just by changing one line in your `config.yaml`.
- **`base.py`**: The blueprint that ensures no matter what AI provider you use, the code to "Ask Question -> Get Answer" remains exactly the same.

---

## 🌐 The API and `main.py`

- **`src/api/schemas/query_schema.py`**: The bouncer. It checks the data coming into the server to make sure it's shaped correctly (e.g., *"You must provide a string, and it cannot be more than 10,000 characters."*). If it fails, it rejects the person before they even reach the Orchestrator.
- **`main.py`**: The startup sequence. When you boot the app, this file:
  1. Reads the `config.yaml`.
  2. Wakes up the AI model.
  3. Wakes up all the agents.
  4. Builds the Orchestrator.
  5. Opens the Web Server so the front-end (UI) can start sending messages to `/api/v1/query`.
