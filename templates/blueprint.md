# Automation Blueprint — [Project Name]

> Fill this out completely before writing any code.
> Claude will grill you until every section is answered.

---

## 1. Trigger
**What starts this automation?**
- [ ] Webhook (HTTP POST from external service)
- [ ] Schedule (cron — every X minutes/hours/days)
- [ ] Manual (you run it yourself)
- [ ] Event (email received, file uploaded, etc.)

Details: _________________________

---

## 2. Input Data
**What data does the automation receive at the start?**

Paste a sample JSON or describe the fields:
```json
{

}
```

---

## 3. What It Does (Step by Step)

List the logical steps in plain English:
1.
2.
3.

---

## 4. Output / Deliverable
**What does the automation produce or do at the end?**

Examples: sends email, writes to Google Sheet, posts to Slack, returns JSON, creates PDF...

Output: _________________________

---

## 5. External Services / APIs
List every external service this automation touches:

| Service | Purpose | Free Tier? | Auth Method |
|---------|---------|------------|-------------|
|         |         |            |             |

---

## 6. Logic Branches (If/Then)
List every decision point:

- If [condition] → then [action]
- If [condition] → then [action]

---

## 7. Error Handling
**What happens when something fails?**

| Failure | Response |
|---------|----------|
| API timeout | Retry N times, then notify via ___ |
| Bad input data | ___ |
| Rate limit hit | ___ |

---

## 8. Success Metric
**How do we programmatically verify this worked?**

Example: "Row appears in Google Sheet with status='complete'"

Metric: _________________________

---

## 9. Chunks (Build Plan)
Break the work into testable pieces:

- [ ] Chunk 1: [name] — [one sentence description]
- [ ] Chunk 2: [name] — [one sentence description]
- [ ] Chunk 3: [name] — [one sentence description]

---

## Status
- [ ] Blueprint approved by Brighton
- [ ] All chunks built and tested
- [ ] Delivered to client
