#!/usr/bin/env python3
"""AWS CDK app for Employed (UAT + PROD on the thibit account).

Wires the isolated ``Employed-*`` stacks for the current single-EC2 production
posture: account governance, no-NAT VPC/security groups, RDS PostgreSQL, and
budget guardrails. The API runtime itself lives under ``deploy/ec2/`` and is
fronted by Cloudflare Tunnel; there is no Fargate, ALB, Api stack, or
Observability stack in this app.

Stages: ``-c environment=uat`` (default) or ``-c environment=prod``. The same
code deploys to either; ``Employed-Governance`` is account-wide (no env suffix).

Account & region MUST be supplied at synth/deploy time — never hardcoded
(account IDs must not be committed). Pass via either:
  - CDK context: ``cdk deploy -c account=<id> -c region=us-east-1``
  - Env vars:    ``AWS_ACCOUNT_ID=<id> AWS_REGION=us-east-1 cdk deploy``
Always run under the intended thibit AWS profile for real infra operations.
"""

import os
import sys
from pathlib import Path

# Allow ``python app.py`` from ``infrastructure/`` while keeping package imports
# stable for stack modules.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aws_cdk as cdk

from infrastructure.stacks.governance_stack import GovernanceStack
from infrastructure.stacks.network_stack import NetworkStack
from infrastructure.stacks.database_stack import DatabaseStack
from infrastructure.stacks.budget_stack import BudgetStack
from infrastructure.stacks.compute_stack import ComputeStack

app = cdk.App()

# --- Stage --------------------------------------------------------------
environment = app.node.try_get_context("environment") or "uat"
if environment not in ("uat", "prod"):
    sys.stderr.write(f"ERROR: environment must be 'uat' or 'prod', got '{environment}'.\n")
    sys.exit(2)
is_prod = environment == "prod"

# --- Account & region (mandatory, never hardcoded) ----------------------
_account = app.node.try_get_context("account") or os.environ.get("AWS_ACCOUNT_ID")
_region = app.node.try_get_context("region") or os.environ.get("AWS_REGION") or "us-east-1"

if not _account:
    sys.stderr.write(
        "ERROR: AWS account ID not provided. Pass via either:\n"
        "  cdk deploy -c account=<id>\n"
        "  AWS_ACCOUNT_ID=<id> cdk deploy\n"
        "Use the intended thibit AWS profile for real infra operations.\n"
    )
    sys.exit(2)
if not (_account.isdigit() and len(_account) == 12):
    sys.stderr.write(f"ERROR: AWS account ID '{_account}' is not a 12-digit numeric string.\n")
    sys.exit(2)

env = cdk.Environment(account=_account, region=_region)

# --- Account-wide tags (cost allocation + budget filtering) -------------
# Activate Product and CostCenter as Cost Allocation Tags in Billing once
# Governance is deployed.
cdk.Tags.of(app).add("Product", "employed")
cdk.Tags.of(app).add("CostCenter", f"employed-{environment}")
cdk.Tags.of(app).add("Env", environment)
cdk.Tags.of(app).add("ManagedBy", "cdk")

# --- Account-wide governance (deployed ONCE, no env suffix) -------------
GovernanceStack(
    app,
    "Employed-Governance",
    product="employed",
    product_monthly_limit_usd=float(app.node.try_get_context("product_budget_usd") or 200.0),
    alert_email=app.node.try_get_context("alert_email") or "mekjr1@gmail.com",
    github_org="xibodev",
    github_repos=("employed",),
    oidc_provider_arn=app.node.try_get_context("oidc_provider_arn"),
    env=env,
    description="Employed account-wide governance — per-product budget, ECR, AppRegistry, GitHub OIDC deploy role",
)

# --- Network (VPC + SGs; no ALB) ---------------------------------------
network_stack = NetworkStack(
    app,
    f"Employed-Network-{environment}",
    environment=environment,
    env=env,
    description=f"Employed network — no-NAT VPC and security groups, {environment}",
)

# --- Database (RDS Postgres) in the network VPC ------------------------
database_stack = DatabaseStack(
    app,
    f"Employed-Database-{environment}",
    network_stack=network_stack,
    environment=environment,
    env=env,
    description=f"Employed database — RDS PostgreSQL 17 t4g.micro Single-AZ (private), {environment}",
)
database_stack.add_dependency(network_stack)

# --- Per-stage budget guardrail ----------------------------------------
_stage_budget = 80.0 if is_prod else 50.0
BudgetStack(
    app,
    f"Employed-Budget-{environment}",
    environment=environment,
    monthly_limit_usd=_stage_budget,
    alert_email=app.node.try_get_context("alert_email") or "mekjr1@gmail.com",
    env=env,
    description=f"Employed per-stage cost guardrail (${_stage_budget:.0f} USD, CostCenter-scoped)",
)

if is_prod:
    compute_stack = ComputeStack(
        app,
        "Employed-Compute-prod",
        network_stack=network_stack,
        database_stack=database_stack,
        environment=environment,
        env=env,
        description="Employed production compute — single Graviton EC2 API box with Cloudflare Tunnel",
    )
    compute_stack.add_dependency(network_stack)
    compute_stack.add_dependency(database_stack)

app.synth()
