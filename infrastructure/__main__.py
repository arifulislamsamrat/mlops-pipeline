import pulumi
import pulumi_aws as aws
import json
from pulumi import Config, Output
import os
import time

# Generate unique suffix to avoid resource conflicts
unique_suffix = str(int(time.time()))[-6:]
stack_name = pulumi.get_stack()

# Get configuration
config = Config()
region = "ap-southeast-1"

# Create key pair resource with unique name - reading from your existing file
key = aws.ec2.KeyPair("mlops-key",
    key_name=f"mlops-key-{unique_suffix}",
    public_key=open("../mlops-key.pub").read().strip(),  # Read from your existing SSH key file
    tags={"Project": f"mlops-pipeline-{stack_name}"}
)

# Create VPC
vpc = aws.ec2.Vpc("mlops-vpc",
    cidr_block="10.0.0.0/16",
    enable_dns_hostnames=True,
    enable_dns_support=True,
    tags={
        "Name": f"mlops-vpc-{stack_name}",
        "Project": f"mlops-pipeline-{stack_name}"
    }
)

# Create Internet Gateway
igw = aws.ec2.InternetGateway("mlops-igw",
    vpc_id=vpc.id,
    tags={
        "Name": f"mlops-igw-{stack_name}",
        "Project": f"mlops-pipeline-{stack_name}"
    }
)

# Create public subnet
public_subnet = aws.ec2.Subnet("mlops-public-subnet",
    vpc_id=vpc.id,
    cidr_block="10.0.1.0/24",
    availability_zone=f"{region}a",
    map_public_ip_on_launch=True,
    tags={
        "Name": f"mlops-public-subnet-{stack_name}",
        "Project": f"mlops-pipeline-{stack_name}"
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
        "Name": f"mlops-route-table-{stack_name}",
        "Project": f"mlops-pipeline-{stack_name}"
    }
)

# Associate route table with subnet
route_table_association = aws.ec2.RouteTableAssociation("mlops-rta",
    subnet_id=public_subnet.id,
    route_table_id=route_table.id
)

# Create security group
security_group = aws.ec2.SecurityGroup("mlops-sg",
    name=f"mlops-sg-{unique_suffix}",
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
        "Name": f"mlops-security-group-{stack_name}",
        "Project": f"mlops-pipeline-{stack_name}"
    }
)

# Create ECR repositories with unique names
ml_inference_repo = aws.ecr.Repository("ml-inference-repo",
    name=f"mlops/ml-inference-{unique_suffix}",
    image_tag_mutability="MUTABLE",
    force_delete=True,  # This allows deletion even with images
    image_scanning_configuration=aws.ecr.RepositoryImageScanningConfigurationArgs(
        scan_on_push=True,
    ),
    tags={
        "Name": f"ml-inference-repo-{stack_name}",
        "Project": f"mlops-pipeline-{stack_name}"
    }
)

data_ingestion_repo = aws.ecr.Repository("data-ingestion-repo",
    name=f"mlops/data-ingestion-{unique_suffix}",
    image_tag_mutability="MUTABLE",
    force_delete=True,  # This allows deletion even with images
    image_scanning_configuration=aws.ecr.RepositoryImageScanningConfigurationArgs(
        scan_on_push=True,
    ),
    tags={
        "Name": f"data-ingestion-repo-{stack_name}",
        "Project": f"mlops-pipeline-{stack_name}"
    }
)

# Enhanced user data script
user_data = f"""#!/bin/bash
# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
sudo apt-get install -y unzip
unzip awscliv2.zip
sudo ./aws/install

# Install curl for health checks
sudo apt-get install -y curl jq

# Create directories
mkdir -p /home/ubuntu/mlops/{{services,monitoring}}
mkdir -p /home/ubuntu/monitoring/{{prometheus,grafana}}

# Set up Docker to start on boot
sudo systemctl enable docker
sudo systemctl start docker

# Create setup info file
cat > /home/ubuntu/setup-info.txt << 'INFO_EOF'
MLOps Infrastructure Setup Complete

Key Information:
- Docker and Docker Compose installed
- AWS CLI v2 installed
- Directories created for services and monitoring
- ECR repositories created with unique suffix: {unique_suffix}

Next Steps:
1. Configure AWS credentials
2. Login to ECR
3. Deploy services via GitHub Actions

Repository URLs:
- ML Inference: {unique_suffix}
- Data Ingestion: {unique_suffix}
INFO_EOF

# Set proper ownership
sudo chown -R ubuntu:ubuntu /home/ubuntu/

# Wait for cloud-init to complete
cloud-init status --wait
"""

# Create EC2 instance
instance = aws.ec2.Instance("mlops-instance",
    key_name=key.key_name,
    instance_type="t3.medium",
    ami="ami-0df7a207adb9748c7",  # Ubuntu 22.04 LTS in ap-southeast-1
    subnet_id=public_subnet.id,
    vpc_security_group_ids=[security_group.id],
    user_data=user_data,
    root_block_device=aws.ec2.InstanceRootBlockDeviceArgs(
        volume_type="gp3",
        volume_size=30,
        delete_on_termination=True
    ),
    tags={
        "Name": f"mlops-instance-{stack_name}",
        "Project": f"mlops-pipeline-{stack_name}"
    }
)

# Create Elastic IP with correct syntax
elastic_ip = aws.ec2.Eip("mlops-eip",
    instance=instance.id,
    domain="vpc",  # Use domain instead of vpc=True
    tags={
        "Name": f"mlops-eip-{stack_name}",
        "Project": f"mlops-pipeline-{stack_name}"
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
pulumi.export("key_pair_name", key.key_name)
pulumi.export("unique_suffix", unique_suffix)