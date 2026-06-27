# Employed Pitch

Employed is a trust-centric hiring platform for Mozambique and Mexico: more than a job board, less than a heavy ATS.

## Why now

Localized hiring markets need simple job posting, trust signals, and exportable candidate/application data without the complexity or lock-in of full ATS platforms.

## What it does

1. Companies create verified organizations and memberships.
2. Recruiters post localized jobs and manage applications.
3. Candidates browse by market and apply through tracked or direct channels.
4. Admins moderate listings and verification state.
5. Integrations consume webhooks and `/export/v1` standard schemas.

## Current traction surface

The product is live at `joinemployed.com`. Frontend hosting is Vercel; API hosting is AWS EC2/RDS behind Cloudflare Tunnel. Stripe is in test mode, mobile money is simulator-mode, AWS SES sends transactional email, and production observability wiring remains an operational follow-up.

## Demo

- Frontend: `https://joinemployed.com`
- API health: `https://api.joinemployed.com/health`
