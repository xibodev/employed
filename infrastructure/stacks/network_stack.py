"""Network stack for Employed on AWS.

Default topology: one VPC, **no NAT gateway**, no ALB. The production backend is
expected to run on a single EC2 box fronted by Cloudflare Tunnel (see
``deploy/ec2/``); the box has no inbound application ports and reaches RDS over
the VPC once its security group is explicitly allowed on the RDS SG.

Security groups:

  * ``service-sg`` — app-tier source SG (stable source for DB access rules).
  * ``rds-sg``     — 5432, from ``service-sg`` (SG-to-SG).

Deployed once per env (``Employed-Network-<env>``). The VPC CIDR is explicitly
``10.1.0.0/16`` to avoid overlapping the existing sibling product VPC in the shared
account.
"""
from aws_cdk import (
    Stack,
    CfnOutput,
    aws_ec2 as ec2,
)
from constructs import Construct

# The api container listens on 8000 (matches the EC2 compose container port).
API_CONTAINER_PORT = 8000


class NetworkStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment: str = "uat",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self._env_name = environment

        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            ip_addresses=ec2.IpAddresses.cidr("10.1.0.0/16"),
            max_azs=2,
            nat_gateways=0,  # no NAT — public subnets + IGW for egress
            subnet_configuration=[
                ec2.SubnetConfiguration(name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24),
                ec2.SubnetConfiguration(
                    name="private", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=24
                ),
            ],
        )

        self.service_sg = ec2.SecurityGroup(
            self,
            "ServiceSg",
            vpc=self.vpc,
            allow_all_outbound=True,
            description="Employed app service tier",
        )

        self.rds_sg = ec2.SecurityGroup(
            self,
            "RdsSg",
            vpc=self.vpc,
            allow_all_outbound=True,
            description="Employed RDS - 5432 from the app tier",
        )
        self.rds_sg.add_ingress_rule(
            self.service_sg, ec2.Port.tcp(5432), "App tier to Postgres"
        )

        CfnOutput(self, "VpcId", value=self.vpc.vpc_id, export_name=f"Employed-{environment}-VpcId")
        CfnOutput(self, "ServiceSecurityGroupId", value=self.service_sg.security_group_id,
                  export_name=f"Employed-{environment}-ServiceSgId")
        CfnOutput(self, "RdsSecurityGroupId", value=self.rds_sg.security_group_id,
                  export_name=f"Employed-{environment}-RdsSgId")
