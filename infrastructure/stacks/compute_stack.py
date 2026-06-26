"""Compute stack for the Employed production API box.

Single Graviton EC2 instance in a public subnet, reached publicly only through
Cloudflare Tunnel. The instance pulls its immutable backend image from ECR and
its compose/runtime assets from the deploy-assets S3 bucket named in SSM.
"""
from __future__ import annotations

from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Stack,
    Tags,
    aws_ec2 as ec2,
    aws_ecr as ecr,
    aws_iam as iam,
)
from constructs import Construct

from infrastructure.stacks.database_stack import DatabaseStack
from infrastructure.stacks.network_stack import NetworkStack


class ComputeStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        network_stack: NetworkStack,
        database_stack: DatabaseStack,
        environment: str = "prod",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        repo_root = Path(__file__).resolve().parents[2]
        bootstrap_path = repo_root / "deploy" / "ec2" / "bootstrap.sh"
        user_data = ec2.UserData.custom(bootstrap_path.read_text(encoding="utf-8"))

        repository = ecr.Repository.from_repository_name(self, "Ecr", "employed-api")

        role = iam.Role(
            self,
            "InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ],
            description="EC2 role for the Employed production API box.",
        )

        if database_stack.instance.secret is not None:
            database_stack.instance.secret.grant_read(role)

        role.add_to_policy(
            iam.PolicyStatement(
                sid="ReadProdParameters",
                actions=["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/employed/prod/*"
                ],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                sid="DecryptSecureStringParameters",
                actions=["kms:Decrypt"],
                # SSM SecureString values may use the AWS-managed SSM key or a
                # future customer key; keep this broad and scoped by the SSM
                # parameter policy above.
                resources=["*"],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                sid="SendTransactionalEmail",
                actions=["ses:SendEmail", "ses:SendRawEmail"],
                resources=["*"],
            )
        )
        repository.grant_pull(role)
        role.add_to_policy(
            iam.PolicyStatement(
                sid="EcrAuthToken",
                actions=["ecr:GetAuthorizationToken"],
                resources=["*"],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                sid="ReadDeployAssets",
                actions=["s3:GetObject"],
                # Exact bucket name is runtime config in SSM
                # /employed/prod/DEPLOY_ASSETS_BUCKET.
                resources=["arn:aws:s3:::employed-prod-deploy-assets-*/*"],
            )
        )

        instance = ec2.Instance(
            self,
            "Box",
            vpc=network_stack.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE4_GRAVITON, ec2.InstanceSize.SMALL
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(
                cpu_type=ec2.AmazonLinuxCpuType.ARM_64
            ),
            security_group=network_stack.service_sg,
            role=role,
            user_data=user_data,
            require_imdsv2=True,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        30, volume_type=ec2.EbsDeviceVolumeType.GP3
                    ),
                )
            ],
        )
        cfn_instance = instance.node.default_child
        cfn_instance.add_property_override("MetadataOptions.HttpPutResponseHopLimit", 2)
        instance.node.add_dependency(database_stack.instance)

        Tags.of(instance).add("Name", f"employed-{environment}-api")

        CfnOutput(
            self,
            "InstanceId",
            value=instance.instance_id,
            description="Employed production API EC2 instance ID.",
            export_name=f"Employed-{environment}-InstanceId",
        )
