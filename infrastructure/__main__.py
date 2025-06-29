import pulumi
import pulumi_aws as aws
import json
from pulumi import Config, Output
import os

# Create key pair resource
key = aws.ec2.KeyPair("mlops-key",
    key_name="mlops-key",
    public_key=open("../mlops-key.pub").read(),  
    tags={"Project": "mlops-pipeline"}
)

# Get configuration
config = Config()
region = "ap-southeast-1"

# Create VPC
vpc = aws.ec2.Vpc("mlops-vpc",
    cidr_block="10.0.0.0/16",
    enable_dns_hostnames=True,
    enable_dns_support=True,
    tags={
        "Name": "mlops-vpc",
        "Project": "mlops-pipeline"
    }
)

# Create Internet Gateway
igw = aws.ec2.InternetGateway("mlops-igw",
    vpc_id=vpc.id,
    tags={
        "Name": "mlops-igw",
        "Project": "mlops-pipeline"
    }
)

# Create public subnet
public_subnet = aws.ec2.Subnet("mlops-public-subnet",
    vpc_id=vpc.id,
    cidr_block="10.0.1.0/24",
    availability_zone=f"{region}a",
    map_public_ip_on_launch=True,
    tags={
        "Name": "mlops-public-subnet",
        "Project": "mlops-pipeline"
    }
)

# Create route table
route_table = aws.ec2.RouteTable("mlops-route-table",
    vpc_id=vpc.id,
    routes=[
        aws.ec2.RouteTableRouteArgs(
            cidr_block="0.0.0.0/0",
            gateway_id=igw.id,
        )
    ],
    tags={
        "Name": "mlops-route-table",
        "Project": "mlops-pipeline"
    }
)

# Associate route table with subnet
route_table_association = aws.ec2.RouteTableAssociation("mlops-rta",
    subnet_id=public_subnet.id,
    route_table_id=route_table.id
)

# Create security group
security_group = aws.ec2.SecurityGroup("mlops-sg",
    vpc_id=vpc.id,
    description="Security group for MLOps services",
    ingress=[
        # SSH
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=22,
            to_port=22,
            cidr_blocks=["0.0.0.0/0"],
            description="SSH"
        ),
        # ML Inference Service
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=8001,
            to_port=8001,
            cidr_blocks=["0.0.0.0/0"],
            description="ML Inference Service"
        ),
        # Data Ingestion Service
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=8002,
            to_port=8002,
            cidr_blocks=["0.0.0.0/0"],
            description="Data Ingestion Service"
        ),
        # Prometheus
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=9090,
            to_port=9090,
            cidr_blocks=["0.0.0.0/0"],
            description="Prometheus"
        ),
        # Grafana
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=3000,
            to_port=3000,
            cidr_blocks=["0.0.0.0/0"],
            description="Grafana"
        ),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            protocol="-1",
            from_port=0,
            to_port=0,
            cidr_blocks=["0.0.0.0/0"],
            description="Allow all outbound traffic"
        )
    ],
    tags={
        "Name": "mlops-security-group",
        "Project": "mlops-pipeline"
    }
)

# Create ECR repositories
ml_inference_repo = aws.ecr.Repository("ml-inference-repo",
    name="mlops/ml-inference",
    image_tag_mutability="MUTABLE",
    image_scanning_configuration=aws.ecr.RepositoryImageScanningConfigurationArgs(
        scan_on_push=True,
    ),
    tags={
        "Name": "ml-inference-repo",
        "Project": "mlops-pipeline"
    }
)

data_ingestion_repo = aws.ecr.Repository("data-ingestion-repo",
    name="mlops/data-ingestion",
    image_tag_mutability="MUTABLE",
    image_scanning_configuration=aws.ecr.RepositoryImageScanningConfigurationArgs(
        scan_on_push=True,
    ),
    tags={
        "Name": "data-ingestion-repo",
        "Project": "mlops-pipeline"
    }
)

# Modified user data script - removed ECR login since no IAM role
user_data = """#!/bin/bash
# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Install AWS CLI
sudo apt-get install -y awscli

# Create directories
mkdir -p /home/ubuntu/mlops/{services,monitoring}

# Note: ECR login will be done manually or through GitHub Actions
echo "Please configure AWS credentials and ECR access manually" > /home/ubuntu/setup-notes.txt
"""

# Create EC2 instance WITHOUT IAM instance profile
instance = aws.ec2.Instance("mlops-instance",
    key_name=key.key_name,
    instance_type="t3.medium",
    ami="ami-0df7a207adb9748c7",  # Ubuntu 22.04 LTS in ap-southeast-1
    subnet_id=public_subnet.id,
    vpc_security_group_ids=[security_group.id],
    # REMOVED: iam_instance_profile parameter
    user_data=user_data,
    root_block_device=aws.ec2.InstanceRootBlockDeviceArgs(
        volume_type="gp3",
        volume_size=30,
        delete_on_termination=True
    ),
    tags={
        "Name": "mlops-instance",
        "Project": "mlops-pipeline"
    }
)

# Create Elastic IP
elastic_ip = aws.ec2.Eip("mlops-eip",
    instance=instance.id,
    vpc=True,
    tags={
        "Name": "mlops-eip",
        "Project": "mlops-pipeline"
    }
)

# Export outputs
pulumi.export("vpc_id", vpc.id)
pulumi.export("subnet_id", public_subnet.id)
pulumi.export("security_group_id", security_group.id)
pulumi.export("instance_id", instance.id)
pulumi.export("instance_public_ip", elastic_ip.public_ip)
pulumi.export("ml_inference_repo_url", ml_inference_repo.repository_url)
pulumi.export("data_ingestion_repo_url", data_ingestion_repo.repository_url)
pulumi.export("grafana_url", Output.concat("http://", elastic_ip.public_ip, ":3000"))
pulumi.export("prometheus_url", Output.concat("http://", elastic_ip.public_ip, ":9090"))