# Employed AWS infrastructure (CDK Python)

Infrastructure code and notes for Employed's AWS production foundation in the thibit account, `us-east-1`. The intended production posture is a FastAPI backend on one EC2 box running Docker Compose + Cloudflare Tunnel, AWS RDS PostgreSQL 17, and a Vercel-hosted frontend at `joinemployed.com`. There is no Fargate, ALB, Api stack, or Observability stack in this app.

## Stacks

| Stack | Scope | Purpose |
| ----- | ----- | ------- |
| `Employed-Governance` | account-wide | Product budget, account tripwire, ECR `employed-api`, AppRegistry application, GitHub OIDC deploy role |
| `Employed-Network-<env>` | per env | VPC `10.1.0.0/16`, public + private-isolated subnets, app/RDS security groups |
| `Employed-Database-<env>` | per env | RDS PostgreSQL 17, `db.t4g.micro`, Single-AZ, private, generated secret `employed/<env>/rds-master` |
| `Employed-Budget-<env>` | per env | CostCenter-scoped budget with IAM deny-new-spend kill-switch on `employed-github-actions-deploy` |

## Shared-account safety

The budget kill-switch only applies a managed IAM deny policy to `employed-github-actions-deploy` via `action_type=APPLY_IAM_POLICY`. It must not stop, terminate, or scale any running compute because the same AWS account hosts other production workloads.

The GitHub OIDC provider (`token.actions.githubusercontent.com`) is account-wide. If it already exists, synth/deploy with:

```bash
cd infrastructure
cdk synth -c environment=prod -c account=<account-id> -c region=us-east-1 -c oidc_provider_arn=<existing-provider-arn>
```

Without `oidc_provider_arn`, the governance stack declares a new provider, which is only safe in an account where it does not already exist.

## Local synth

```bash
cd infrastructure
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\cdk synth -c environment=prod -c account=000000000000 -c region=us-east-1
```

Use the dummy account above for local validation. For real operations, pass the account/region at runtime and use the intended thibit AWS profile. Do not commit account IDs, credentials, generated `cdk.out/`, or `.env` files.

## Runtime assets

The EC2 runtime assets live in [`deploy/ec2/`](../deploy/ec2/):

- `bootstrap.sh` — EC2 user-data that installs Docker, downloads deploy assets, renders `.env`, and starts compose.
- `docker-compose.ec2.yml` — `api`, `worker`, `redis`, and `cloudflared` only. The frontend is Vercel.
- `render-env.sh` — reads `/employed/prod/*` SSM parameters and writes `/opt/employed/.env`.
