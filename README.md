# MailMind — Local AI Email Management Agent

MailMind is a lightweight, **local** email assistant. It reads your Gmail, uses a
locally-hosted **Llama 3.1 (8B)** model via [Ollama](https://ollama.com) to classify
and summarize messages, extracts dates/locations/events, and writes them to Google
Calendar — all while keeping email content on your own machine.

---

## Key Features

- **Gmail integration** — secure OAuth 2.0 login; read INBOX / TRASH, mark spam, move to trash.
- **AI analysis (local)** — classify emails (Social / Promotions / Important / Personal / Spam / Other),
  generate summaries, and extract key dates, start/end times, locations and events.
- **Agent workflow** — one click runs a full pipeline per email:
  **read → task recognition → dynamic tool selection → result validation → state saving**.
  The agent routes each email by category (e.g. spam → trash, important → summarize + add to calendar).
- **Google Calendar** — write extracted events to your calendar; view a 30-day to-do list.
- **Structured local persistence** — classification basis, time, location, event and processing
  status are stored as JSON (`email_classifications.json`) so results are reused across restarts.
- **Robustness** — output validation, field completion (e.g. auto-filling a missing end time),
  and graceful fallback when the model returns bad output or the local API is unreachable.
- **Desktop GUI** — Tkinter interface supporting batch processing and schedule management.

---

## Architecture

```
main.py            Entry point: authenticates Gmail and launches the GUI.
email_analyzer.py  Tkinter GUI and user interactions.
agent.py           Agent workflow: read → recognize → call tools → validate → save state.
gmail_api.py       Gmail + Google Calendar operations wrapped as callable tools.
llama_api.py       Local Llama 3.1 calls (classification & summarization) with validation/fallback.
test.py            Standalone experiment/prototype (read-only Gmail).
```

### Agent workflow (per email)

| Stage | Where | What happens |
|-------|-------|--------------|
| 1. Read | `gmail_api.get_gmail_messages` | Fetch sender, date, subject, body |
| 2. Recognize | `llama_api.send_to_llama_for_analysis` | Classify + record reasoning |
| 3. Tool call | `agent.process_email` | Route by category: trash / summarize / calendar |
| 4. Validate | `agent._is_valid_event`, `llama_api._complete_summary_fields` | Check required fields, complete missing ones |
| 5. Save state | `email_analyzer._save_classifications_to_file` | Persist structured JSON (reused on next launch) |

---

## Requirements

- **Python 3.8+**
- **[Ollama](https://ollama.com)** with the Llama 3.1 model pulled:
  ```bash
  ollama pull llama3.1
  ```
  The app calls Ollama at `http://localhost:11434`.
- **Google API credentials** — a `credentials.json` OAuth client with the Gmail and
  Calendar APIs enabled (see Setup). This file is **not** included in the repo.

Install Python dependencies:
```bash
pip install -r requirements.txt
```

---

## Setup

1. In the [Google Cloud Console](https://console.cloud.google.com/), create an OAuth 2.0
   client (Desktop app) and enable the **Gmail API** and **Google Calendar API**.
2. Download the client secret and save it as `app/credentials.json`.
3. Start Ollama and ensure `llama3.1` is available (`ollama list`).

The scopes requested are `gmail.modify` and `calendar`. On first run a browser window
opens for consent; the resulting token is cached in `app/token.json`.

---

## Usage

```bash
cd app
python main.py
```

In the GUI:

- **Categorize All** — batch-classify the loaded emails.
- **Summarize Selected** — extract subject, dates, times, locations and events.
- **Delete** — move selected emails to TRASH.
- **Add to Calendar** — create a calendar event from a summarized email.
- **Auto (Agent)** — run the full agent workflow on selected emails (classify → act → persist).

The right-hand panel shows to-do items (upcoming calendar events for the next 30 days).

---

## Data Format

Persisted record per message (`email_classifications.json`):

```json
{
  "<gmail_message_id>": {
    "category": "Important",
    "reasoning": "Contains a specific date and event information",
    "summary": {
      "Subject": "Partnership Meeting",
      "KeyDates": ["2024-11-30"],
      "StartTime": "2024-11-30T10:00:00",
      "EndTime": "2024-11-30T13:00:00",
      "KeyLocations": ["Conference Room A"],
      "KeyEvents": ["Confirmation for a meeting scheduled on 2024-11-30."]
    },
    "status": "event_created"
  }
}
```

`status` values: `classified`, `summarized`, `event_created`, `moved_to_trash`,
`calendar_failed`, `calendar_unavailable`.

---

## Security & Privacy

- Email analysis runs **locally** through Ollama; message content is not sent to any cloud LLM.
- **Never commit secrets.** `credentials.json`, `token.json` and any account/password files
  are listed in `.gitignore`. Keep your own copies locally only.

---

## Roadmap

- Support for mail providers beyond Gmail.
- Richer extraction of complex event information.
- More flexible, user-configurable UI.
