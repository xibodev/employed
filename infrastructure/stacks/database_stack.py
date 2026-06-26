"""Database stack for Employed (RDS PostgreSQL).

RDS for PostgreSQL **17**, ``db.t4g.micro``, **Single-AZ**, in the network
stack's PRIVATE_ISOLATED subnets, reachable only from the service SG (5432).
Master credentials are generated into Secrets Manager (never in the repo); the
deploy path assembles them + the endpoint into the SSM SecureString
``/employed/<env>/DATABASE_URL`` that the api container consumes.

Per-stage hardening:
  * **uat**  — 7-day snapshots, removal ``DESTROY`` (clean teardown).
  * **prod** — 14-day snapshots, **deletion protection**, removal ``RETAIN``.

Deployed once per env (``Employed-Database-<env>``). Depends on the network stack.
"""
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_ec2 as ec2,
    aws_rds as rds,
)
from constructs import Construct

from infrastructure.stacks.network_stack import NetworkStack

DB_NAME = "employed"
DB_PORT = 5432


class DatabaseStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        network_stack: NetworkStack,
        environment: str = "uat",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self._env_name = environment
        is_prod = environment == "prod"

        self.instance = rds.DatabaseInstance(
            self,
            "Postgres",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_17
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE4_GRAVITON, ec2.InstanceSize.MICRO
            ),
            vpc=network_stack.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[network_stack.rds_sg],
            multi_az=False,
            allocated_storage=20,
            max_allocated_storage=100,
            storage_type=rds.StorageType.GP3,
            database_name=DB_NAME,
            port=DB_PORT,
            credentials=rds.Credentials.from_generated_secret(
                "employed_admin", secret_name=f"employed/{environment}/rds-master"
            ),
            backup_retention=Duration.days(14 if is_prod else 7),
            deletion_protection=is_prod,
            removal_policy=RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY,
            delete_automated_backups=not is_prod,
            cloudwatch_logs_exports=["postgresql"],
            auto_minor_version_upgrade=True,
            publicly_accessible=False,
        )

        CfnOutput(self, "DbEndpoint", value=self.instance.db_instance_endpoint_address,
                  description=f"RDS endpoint host — feeds /employed/{environment}/DATABASE_URL",
                  export_name=f"Employed-{environment}-DbEndpoint")
        CfnOutput(self, "DbPort", value=str(DB_PORT), export_name=f"Employed-{environment}-DbPort")
        CfnOutput(self, "DbName", value=DB_NAME, export_name=f"Employed-{environment}-DbName")
        if self.instance.secret is not None:
            CfnOutput(
                self, "DbSecretArn", value=self.instance.secret.secret_arn,
                description="Secrets Manager ARN holding the RDS master user/pass (assemble DATABASE_URL from this)",
                export_name=f"Employed-{environment}-DbSecretArn",
            )
