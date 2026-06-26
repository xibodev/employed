"""Account-wide governance for Employed.

Account-wide, **deployed ONCE** under the fixed name ``Employed-Governance``
(no env suffix). Holds the things a uat deploy and a prod deploy must NOT each
try to create:

  1. Per-PRODUCT monthly budget (spans both stages; filters on the ``Product``
     tag) with tiered 50/80/100% notifications. Complements the per-STAGE
     ``BudgetStack``.
  2. Account-wide ACTUAL tripwire ($5, no tag filter) — catches unexpected
     spend, including untagged/hand-clicked resources, on a fresh product setup.
  3. ECR repository ``employed-api`` for the backend image.
  4. A myApplications (AppRegistry) Application "Employed" — one cost/ops pane.
  5. GitHub Actions OIDC provider reference + a keyless deploy role scoped to
     the ``xibodev/employed`` repo (never org-wide).

Profile/account: the thibit AWS account. Account IDs are supplied at deploy time
and must not be committed.
"""
from __future__ import annotations

from aws_cdk import (
    Stack,
    CfnOutput,
    RemovalPolicy,
    aws_budgets as budgets,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subs,
    aws_servicecatalogappregistry as appregistry,
)
from constructs import Construct


class GovernanceStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        product: str = "employed",
        product_monthly_limit_usd: float = 200.0,
        account_tripwire_usd: float = 5.0,
        alert_email: str,
        github_org: str = "xibodev",
        github_repos: tuple[str, ...] = ("employed",),
        oidc_provider_arn: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ---------------------------------------------------------------
        # 1. Per-PRODUCT budget (cross-stage). Filters on the `Product` tag,
        #    which must be activated as a Cost Allocation Tag in Billing.
        # ---------------------------------------------------------------
        budget_topic = sns.Topic(
            self, "ProductBudgetAlertTopic", display_name=f"{product} product budget alerts"
        )
        budget_topic.add_subscription(sns_subs.EmailSubscription(alert_email))

        subscribers = [
            budgets.CfnBudget.SubscriberProperty(subscription_type="EMAIL", address=alert_email),
            budgets.CfnBudget.SubscriberProperty(
                subscription_type="SNS", address=budget_topic.topic_arn
            ),
        ]

        def _notif(threshold: float) -> budgets.CfnBudget.NotificationWithSubscribersProperty:
            return budgets.CfnBudget.NotificationWithSubscribersProperty(
                notification=budgets.CfnBudget.NotificationProperty(
                    notification_type="FORECASTED" if threshold < 100 else "ACTUAL",
                    comparison_operator="GREATER_THAN",
                    threshold=threshold,
                    threshold_type="PERCENTAGE",
                ),
                subscribers=subscribers,
            )

        budgets.CfnBudget(
            self,
            "EmployedProductMonthlyBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name=f"{product}-product-monthly",
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=product_monthly_limit_usd, unit="USD"
                ),
                cost_filters={"TagKeyValue": [f"user:Product${product}"]},
            ),
            notifications_with_subscribers=[_notif(50.0), _notif(80.0), _notif(100.0)],
        )

        def _actual(threshold: float) -> budgets.CfnBudget.NotificationWithSubscribersProperty:
            return budgets.CfnBudget.NotificationWithSubscribersProperty(
                notification=budgets.CfnBudget.NotificationProperty(
                    notification_type="ACTUAL",
                    comparison_operator="GREATER_THAN",
                    threshold=threshold,
                    threshold_type="PERCENTAGE",
                ),
                subscribers=subscribers,
            )

        budgets.CfnBudget(
            self,
            "EmployedAccountSpendTripwire",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name=f"{product}-account-tripwire-monthly",
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(amount=account_tripwire_usd, unit="USD"),
            ),
            notifications_with_subscribers=[_actual(50.0), _actual(100.0)],
        )

        # ---------------------------------------------------------------
        # 2. ECR repository for the backend image.
        # ---------------------------------------------------------------
        self.repository = ecr.Repository(
            self,
            "ApiRepository",
            repository_name=f"{product}-api",
            image_scan_on_push=True,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                ecr.LifecycleRule(
                    description="Keep the 20 most recent images; expire older untagged.",
                    max_image_count=20,
                )
            ],
        )

        # ---------------------------------------------------------------
        # 3. myApplications (AppRegistry) Application.
        # ---------------------------------------------------------------
        self.application = appregistry.CfnApplication(
            self,
            "EmployedApplication",
            name="Employed",
            description="All AWS resources for the Employed product (cost + ops single pane).",
            tags={"Product": product, "ManagedBy": "cdk"},
        )

        # ---------------------------------------------------------------
        # 4. GitHub Actions OIDC provider + keyless deploy role.
        #    GitHub's OIDC provider is account-wide. If another product stack
        #    already created token.actions.githubusercontent.com, pass
        #    `-c oidc_provider_arn=<arn>` so this stack imports it; attempting to
        #    create a second provider for the same URL in the same account fails.
        # ---------------------------------------------------------------
        if oidc_provider_arn:
            oidc_provider = iam.OpenIdConnectProvider.from_open_id_connect_provider_arn(
                self,
                "GitHubActionsOIDC",
                oidc_provider_arn,
            )
        else:
            oidc_provider = iam.OpenIdConnectProvider(
                self,
                "GitHubActionsOIDC",
                url="https://token.actions.githubusercontent.com",
                client_ids=["sts.amazonaws.com"],
            )
        # sub claims like `repo:xibodev/employed:*` — any ref on the repo.
        sub_patterns = [f"repo:{github_org}/{repo}:*" for repo in github_repos]

        self.deploy_role = iam.Role(
            self,
            "GitHubActionsDeployRole",
            role_name=f"{product}-github-actions-deploy",
            assumed_by=iam.OpenIdConnectPrincipal(
                oidc_provider,
                conditions={
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                    },
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": sub_patterns,
                    },
                },
            ),
            description="Keyless CI deploy role for the xibodev/employed repo (OIDC). Assumes CDK bootstrap roles + pushes ECR.",
        )
        self.deploy_role.add_to_policy(
            iam.PolicyStatement(
                sid="AssumeCdkBootstrapRoles",
                actions=["sts:AssumeRole"],
                resources=[f"arn:aws:iam::{self.account}:role/cdk-*"],
            )
        )
        self.repository.grant_pull_push(self.deploy_role)
        self.deploy_role.add_to_policy(
            iam.PolicyStatement(
                sid="EcrAuthToken",
                actions=["ecr:GetAuthorizationToken"],
                resources=["*"],
            )
        )

        # ---------------------------------------------------------------
        # Outputs
        # ---------------------------------------------------------------
        CfnOutput(self, "EcrRepositoryUri", value=self.repository.repository_uri,
                  description="ECR repo URI for the employed-api image")
        CfnOutput(self, "ApplicationArn", value=self.application.attr_arn,
                  description="AppRegistry Application ARN (myApplications)")
        CfnOutput(self, "GitHubDeployRoleArn", value=self.deploy_role.role_arn,
                  description="Role ARN for GitHub Actions to assume via OIDC (set as a repo VARIABLE, not a secret)")
