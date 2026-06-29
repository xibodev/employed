# Employed — Release Notes

```yaml
last_verified: 2026-06-28T00:00:00Z
git_ref: master
verified_by: prod documentation refresh
```

## 2026-06-28 — Production live on AWS and Vercel

- Employed production is live at `joinemployed.com` with the frontend on Vercel and the API at `api.joinemployed.com` through Cloudflare Tunnel to AWS EC2.
- Backend production uses ECR image tags `prod` and `prod-<sha>`, EC2 Docker Compose, RDS PostgreSQL 17, SSM SecureString secrets, and AWS SES email.
- Production deployment uses GitHub OIDC via `deploy-prod.yml`; frontend deployment uses `deploy-vercel.yml`.
- The old shared-VPS UAT deployment is disabled.
