# Receipts demo video script (2:35)

## 0:00–0:15 — Hook

Show a large AI-generated PR diff, then say: “The reviewer does not need another opinion about this diff. They need the receipts: what the agent changed, what it ran, and what it never executed.”

## 0:15–0:35 — Zero-setup proof

In a fresh terminal, run:

```bash
python -m pip install .
receipts demo
```

Point out: no API key, no server, no login, no network requirement for the demo.

## 0:35–1:05 — Trust Card

Show the printed card. Read the three lines quickly:

- `src/auth/login.py` is directly verified by its mapped pytest file.
- `src/auth/session.py` is only indirectly exercised.
- `src/billing/invoice.py` is red: it changed after the final test, so it was never executed.

Point to the scope-drift and sensitive-path flags, then the SHA-256 integrity receipt.

## 1:05–1:35 — Replay

Open the printed replay path in a browser. Scroll the dark timeline and show timestamped file changes beside test runs. Say: “This is static HTML with the manifest embedded—safe to attach to a PR or host on Pages. Our optional AWS launch serves this same curated artifact through private S3 and a public CloudFront HTTPS link.”

## 1:35–1:58 — Review tour

Show the offline sample tour. Say: “With no key, this is clearly marked sample output generated with GPT-5.6. With a key, `receipts tour` asks GPT-5.6 for the same risk-ranked review tour. The recorder never depends on the API.”

## 1:58–2:20 — Real integration

Show:

```bash
receipts run --task "fix the login bug" -- codex "fix the login bug"
receipts card
```

Then show [`examples/receipts-pr.yml`](examples/receipts-pr.yml) and explain that the composite Action posts one sticky Trust Card comment, updating it on later commits.

## 2:20–2:35 — Close

“Receipts is agent-agnostic evidence over vibes. Before merging an AI change, know what it wrote, what it ran, and what it never executed.”
