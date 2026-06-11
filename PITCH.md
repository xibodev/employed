<!-- last_verified: 2026-06-11T02:02:49Z | verified_by: doc-drift audit, quality run 2026-06-10_120309 -->

# Employed — Job board for Mozambique & Mexico

Mozambique has no dedicated job board, so job seekers rely on Facebook groups, WhatsApp chains, and word of mouth. Mexico has established global platforms like Indeed and LinkedIn, but SMB employers often find them expensive, generic, and English-first. Across both markets, there is room for a local-first, mobile-friendly job board built around regional needs and regional payment rails.

Employed is a localized job board where companies post jobs, candidates browse opportunities, and admins moderate listings for quality. From day one it is designed for both Mozambique and Mexico, with local payment support through M-Pesa, e-Mola, and Stripe, plus market-specific browsing through localized subdomains.

## How it works

1. Employers create job listings, choosing between free basic posts and paid featured posts. Featured listings are paid with Stripe in Mexico and with M-Pesa or e-Mola in Mozambique, while admin approval helps prevent spam and scams.
2. Job seekers browse by category, location, and market on localized experiences such as mz.employed.co.mz and mx.employed.co.mz. No account is required to browse jobs.
3. Listings auto-expire after 90 days to keep the marketplace fresh, while a public JSON API supports syndication and reCAPTCHA v3 reduces automated abuse.

## Market

Mozambique has a population of roughly 33 million, around 2 million formal sector jobs, and effectively zero dedicated job board brand. Mexico offers a much larger SMB recruitment market but remains underserved by expensive, global, English-first platforms. Employed can differentiate through local language support, mobile usability, moderation, and local checkout options.

## Business model

Basic listings are free. Featured listings are priced at roughly $25–50 per post in Mexico, with MZN-equivalent pricing via mobile money in Mozambique. Employer subscriptions for unlimited featured listings range from $99–199 per month. The model becomes self-sustaining at around 100 paid featured listings per month, giving a clear line of sight to break-even.

## Traction (today)

The product is live on UAT (employed.xibodev.com, Box 3) with CI/CD deploys, a 134-test backend suite plus Playwright E2E journeys, and UAT evidence with screenshots. Stripe, M-Pesa, and e-Mola payment plumbing are wired, health endpoints are monitored by UptimeRobot, and structured logging plus Sentry SDKs are in place (Sentry project provisioning pending). This is a launch execution problem, not a greenfield build.

### What we’ve built

- Subdomain-localized job board for MZ and MX
- Admin approval workflow for spam prevention
- Featured listings with Stripe, M-Pesa, and e-Mola payments
- 90-day auto-expiration
- Public JSON API for syndication
- reCAPTCHA v3 abuse prevention
- SEO-optimized localized metadata (robots, sitemap, per-market locale)
- PT, ES, and EN language support
- Health endpoints, uptime monitoring, structured logging, Sentry SDKs wired
- 134 backend tests + Playwright E2E suite and CI/CD pipeline

### What’s next (6 months)

- Promote from UAT (Box 3) to production once release gates clear
- Reach 100 paid featured listings per month
- Partner with 5 Maputo recruitment agencies
- Launch MX market with 3 SMB employers
- Integrate Pagos for unified payment processing

## Team

Abdul Meque — Founder. Full-stack engineer and serial builder. Runs XIBOX, LDA (XiboCloud) in Mozambique.

## Ask

[TBD] Bootstrap-friendly. Target is to become revenue-funded at roughly 100 paid featured listings per month, with fundraising only if expansion into new geographies or employer SaaS accelerates.

## Contact

- Email: abdul@xibodev.com
- Demo (UAT): https://employed.xibodev.com
