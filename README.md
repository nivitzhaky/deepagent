# DeepAgent

An autonomous code generation agent that writes code, tests it, and iterates until all tests pass.

## Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your API key
```

## Run

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Open http://localhost:8000 in your browser.

## How It Works

1. Enter an assignment describing what you want the code to do
2. Choose language (Python or JavaScript), model provider, and max iterations
3. Click **Run Agent**
4. The agent:
   - Generates implementation code + tests
   - Executes the tests
   - If tests fail, analyzes errors and fixes the code
   - Repeats until all tests pass or max iterations reached
5. Watch real-time logs, view generated code, and see test output live

## Project Structure

```
deepagent/
├── backend/
│   ├── main.py          # FastAPI app + WebSocket
│   ├── agent.py         # DeepAgent loop
│   ├── tools.py         # Code execution utilities
│   └── requirements.txt
├── frontend/
│   └── index.html       # Single-page UI
└── workspace/           # Generated code files (per session)
```
