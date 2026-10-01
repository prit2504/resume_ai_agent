# Email MCP Server

This small MCP service is derived from the original `email_mcp_server` prototype and is intentionally limited to **email validation and approved single-email delivery**.

The main Resume AI Agent is responsible for:

- finding recruiter/HR contact details in the job posting;
- drafting the personalized email from the user's resume and job context;
- showing the draft to the user;
- requiring explicit human approval.

This MCP service only transports the already-approved email.

## Tools

### `validate_email`

Input:

~~~json
{"email":"hr@company.com"}
~~~

### `send_email`

Input:

~~~json
{
  "to_email": "hr@company.com",
  "subject": "Application for AI Engineer",
  "body": "Hello ...",
  "pdf_base64": "<base64 PDF>",
  "pdf_filename": "resume.pdf"
}
~~~

The attachment is sent as bytes instead of a local `pdf_path`. This allows the FastAPI app and MCP service to run in separate processes or containers without sharing a filesystem.

## Setup

~~~bash
cd email_mcp_server
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python server.py
~~~

By default the MCP endpoint is:

~~~text
http://127.0.0.1:9000/mcp
~~~

For Gmail, create an app password and set `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` in the local `.env`. Never commit the real password.

## Why the old agent.py is not included

The original prototype also contained a separate LangGraph agent that loaded HR contacts from CSV, drafted messages, and auto-sent them. That logic is now handled inside Resume AI Agent with actual resume/job context and a human approval gate, so duplicating that agent would create two conflicting workflows.
