"""Per-stage monthly AWS Budget guard for Employed, scoped to
``CostCenter=employed-<env>``.

Tiered SNS + email notifications at 50/80/100% of the per-stage limit (uat $50,
prod $80). At 100% a **Budget-Action kill-switch** attaches a deny policy to
the Employed GitHub deploy role so no new spend can be provisioned.

Shared-account safety: this action must never stop, terminate, or scale running
compute. It only applies an IAM deny-new-spend managed policy to
``employed-github-actions-deploy``.

Complements the per-PRODUCT budget in ``Employed-Governance``.
"""
from __future__ import annotations

from aws_cdk import (
    Stack,
    aws_budgets as budgets,
    aws_iam as iam,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subs,
)
from constructs import Construct


class BudgetStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment: str,
        monthly_limit_usd: float = 50.0,
        alert_email: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        cost_center = f"employed-{environment}"

        alert_topic = sns.Topic(
            self, "BudgetAlertTopic", display_name=f"Employed {environment} budget alerts"
        )
        alert_topic.add_subscription(sns_subs.EmailSubscription(alert_email))

        subscribers = [
            budgets.CfnBudget.SubscriberProperty(subscription_type="EMAIL", address=alert_email),
            budgets.CfnBudget.SubscriberProperty(
                subscription_type="SNS", address=alert_topic.topic_arn
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

        budget = budgets.CfnBudget(
            self,
            f"EmployedMonthlyBudget{environment.capitalize()}",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name=f"employed-{environment}-monthly",
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(amount=monthly_limit_usd, unit="USD"),
                cost_filters={"TagKeyValue": [f"user:CostCenter${cost_center}"]},
            ),
            notifications_with_subscribers=[_notif(50.0), _notif(80.0), _notif(100.0)],
        )

        deny_new_spend = iam.ManagedPolicy(
            self,
            "DenyNewSpendPolicy",
            managed_policy_name=f"employed-{environment}-deny-new-spend",
            statements=[
                iam.PolicyStatement(
                    sid="DenyExpensiveCreates",
                    effect=iam.Effect.DENY,
                    actions=[
                        "ec2:RunInstances",
                        "rds:CreateDBInstance",
                        "rds:CreateDBCluster",
                        "ecs:CreateService",
                        "ecs:RunTask",
                        "elasticloadbalancing:CreateLoadBalancer",
                        "elasticache:CreateCacheCluster",
                    ],
                    resources=["*"],
                )
            ],
        )

        budgets.CfnBudgetsAction(
            self,
            "KillSwitch",
            action_threshold=budgets.CfnBudgetsAction.ActionThresholdProperty(
                type="PERCENTAGE", value=100.0
            ),
            action_type="APPLY_IAM_POLICY",
            approval_model="AUTOMATIC",
            budget_name=budget.ref,
            definition=budgets.CfnBudgetsAction.DefinitionProperty(
                iam_action_definition=budgets.CfnBudgetsAction.IamActionDefinitionProperty(
                    policy_arn=deny_new_spend.managed_policy_arn,
                    roles=["employed-github-actions-deploy"],
                )
            ),
            execution_role_arn=self._kill_switch_role().role_arn,
            notification_type="ACTUAL",
            subscribers=[
                budgets.CfnBudgetsAction.SubscriberProperty(
                    type="EMAIL", address=alert_email
                )
            ],
        )

    def _kill_switch_role(self) -> iam.Role:
        """Role AWS Budgets assumes to apply the deny policy."""
        role = iam.Role(
            self,
            "BudgetActionRole",
            assumed_by=iam.ServicePrincipal("budgets.amazonaws.com"),
            description="Lets AWS Budgets apply the Employed deny-new-spend policy at 100%.",
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "iam:AttachRolePolicy",
                    "iam:DetachRolePolicy",
                ],
                resources=[f"arn:aws:iam::{self.account}:role/employed-github-actions-deploy"],
            )
        )
        return role
