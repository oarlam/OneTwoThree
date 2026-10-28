# ADR 0006: LLM Meeting Agenda Parsing via Amazon Bedrock

- **Status**: Accepted
- **Date**: 2026-10-28
- **Context**: Meetings Application (Spry) — Lab 6

## Context

Users frequently schedule meetings based on unstructured text received via emails, Slack/Teams messages, or quick meeting notes. Manually copying meeting titles, start times, durations, topics, speakers, and action items into separate form fields is tedious and error-prone. We want to provide a "Paste an agenda" feature where users can paste raw unstructured text and have an LLM extract and structure the agenda automatically into a form that the user can verify, adjust, and save.

### Key Constraints & Requirements:
1. **Zero-Idle-Cost Serverless Architecture**: The core backend API runs inside a private VPC with Aurora Serverless v2 PostgreSQL. There is no NAT Gateway (which would cost ~$32/month) and no VPC peering.
2. **Security & Trust Boundary**: Pasted text originates from external, untrusted sources and could contain prompt injection attempts or hallucinated data. The LLM must never write directly to the database or bypass business validation.
3. **Structured Contract**: The output must conform strictly to a validated schema (`ParsedAgenda`), not arbitrary conversational text.
4. **Resilience**: If the AI service fails or throttles, the core application must remain fully functional with zero interruption.

---

## Decision

We separate the AI parsing path entirely from the data persistence path: **"The model suggests, and the person decides."**

```
Browser (React) ──[ 1. Raw Text + Token ]──> Parser Lambda (No VPC) ──> Amazon Bedrock (Claude)
       │                                              │
       │                                     Returns Structured JSON
       ▼                                              │
Pre-filled Form with "suggested" badges <─────────────┘
       │
[ 2. User reviews / edits & clicks Save ]
       │
       ▼
Main API Lambda (In VPC) ──> Aurora PostgreSQL (Saves Meeting + ai_suggestion)
```

1. **Parser Lambda outside the VPC**:
   - Reuses the backend container image with entry point `app.ai.agenda_lambda.handler`.
   - Runs outside the VPC, accessing Amazon Bedrock over the public internet with zero NAT Gateway and zero VPC interface endpoints ($0 fixed monthly cost when idle).
   - Exposed via a Lambda Function URL with CORS configured for our CloudFront frontend.
   - Authenticated using Cognito ID-tokens verified against Cognito's JWKS.
   - Strictly rate-limited and bounds-checked: rejects payloads over 10,000 characters with HTTP 413.

2. **Model Selection & Schema Enforcement**:
   - Primary model: Anthropic Claude via Bedrock (`PARSER_MODEL=us.anthropic.claude-haiku-4-5-20251001-v1:0` or `anthropic.claude-opus-5-5`), configurable via environment variables.
   - The model is instructed to respond strictly by calling a single tool: `record_agenda`.
   - The tool parameters conform to the `ParsedAgenda` Pydantic model (`AgendaItem`, `ActionItem`, `starts_at`, `duration_minutes`, `language`).
   - If validation fails, the function feeds the validation error back to the model for one automatic retry before failing cleanly with `AgendaParseError` (HTTP 422).

3. **Human-in-the-Loop & Quality Signals**:
   - The parser returns suggested agenda fields to the frontend.
   - The frontend pre-fills the form and highlights every AI-populated field with a distinct `suggested` badge until the user touches or edits it.
   - When the user clicks "Save", the request goes through the normal, trusted `/api/meetings` endpoint in the VPC. The model never writes anything.
   - Along with the final meeting details, the frontend sends the original AI suggestion (`ai_suggestion`), which the API stores in a JSON column for continuous quality evaluation and prompt improvement.

---

## Alternatives Considered

### 1. Invoking Bedrock directly from the main API Lambda inside the VPC
- **How it works**: The main API Lambda in the private subnets calls `bedrock-runtime` via an AWS PrivateLink VPC Interface Endpoint.
- **Why it lost**: An interface endpoint costs ~$7.20/month per Availability Zone (~$14.40/month for 2 AZs), regardless of usage. This violates the course's zero-idle-cost requirement.

### 2. Calling the Anthropic Messages API directly over public internet
- **How it works**: Use Anthropic's public SaaS API (`api.anthropic.com`) instead of AWS Bedrock.
- **Why it lost**: Requires managing external API keys and billing outside AWS, lacks IAM role-based temporary credential authorization, and cannot leverage AWS Bedrock inference profiles or unified CloudWatch governance.

### 3. Regular Expressions / Heuristic Natural Language Processing
- **How it works**: Rule-based text parsing using regex for dates, times, and lists.
- **Why it lost**: Extremely brittle. It fails on multilingual input (e.g. Ukrainian vs English), relative dates ("next Tuesday after lunch"), conversational greetings/signatures, and extracting task owners and action items.

---

## Consequences

- **Cost**: Pure pay-per-token pricing with $0 idle cost. Claude Haiku costs ~$0.0016 per parse (~1,200 input tokens, ~160 output tokens).
- **Observability**: Every parse emits a structured JSON log line in CloudWatch with `user`, `model`, `prompt_version`, `input_tokens`, `output_tokens`, `latency_ms`, and calculated `cost_usd`.
- **Fault Tolerance**: If Amazon Bedrock is throttled (HTTP 429) or unavailable, the UI displays an actionable message, and the user can type the agenda manually. All other features (calendar, authentication, reports) remain completely unaffected.

