# OpsPilot — Job Failure Analysis Assistant

## Features
- Upload `.log` or `.txt` files, or paste log text.
- Paste an email notification to extract job, schedule, incident ID and timestamp.
- Scan for common failure patterns: missing file, database connectivity, permissions, timeout, storage, data format, memory/resource and generic application errors.
- Show all matching lines and context around the primary match.
- Explain a likely failure category and suggest checks and safe retry guardrails.
- Generate and download a structured escalation email draft.
- Download a text analysis report.

## Run locally
Python 3.10+ recommended.

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

## Demo
1. Start the app.
2. Click **Load sample email + log** in the sidebar.
3. Click **Analyze failure**.
4. Show the likely category, matched lines, suggested checks and guardrail.
5. Open **Email draft**, fill in confirmed business impact, and download the draft.

## Safety and limitations
This is a rule-based prototype. It does not connect to OpCon, Outlook, PuTTY/SSH, or ServiceNow; it does not send emails, change incident states, or restart jobs. Use fictional or client-approved sanitized logs only. A matched signature is a clue, not a confirmed root cause.

## Production scaling
Prefer an approved centralized logging API where available. Otherwise, only after written client/security approval, use SSH/SFTP to retrieve specific approved log files. Use an allowlisted host, dedicated read-only identity, verified host keys, a secrets manager, output-size limits, redaction, audit logs and retention controls. Keep restarts and incident state changes in separately approved workflows with human review.
