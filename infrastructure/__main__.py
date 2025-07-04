import pulumi
import pulumi_aws as aws
import json
from pulumi import Config, Output
import os

# Use stable suffix instead of timestamp to avoid resource conflicts
unique_suffix = "main"
stack_name = pulumi.get_stack()

# Get configuration
config = Config()
region = "ap-southeast-1"

# Create key pair resource with unique name - using environment variable or default
key = aws.ec2.KeyPair("mlops-key",
    key_name=f"mlops-key-{unique_suffix}",
    public_key=os.environ.get("SSH_PUBLIC_KEY", 
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC7qR4nX8J5K2Mz3vL6P9Q1sT7uV2wX4y5Z6a7B8c9D0e1F2g3H4i5J6k7L8m9N0o1P2q3R4s5T6u7V8w9X0y1Z2a3B4c5D6e7F8g9H0i1J2k3L4m5N6o7P8q9R0s1T2u3V4w5X6y7Z8a9B0c1D2e3F4g5H6i7J8k9L0m1N2o3P4q5R6s7T8u9V0w1X2y3Z4a5B6c7D8e9F0g1H2i3J4k5L6m7N8o9P0q1R2s3T4u5V6w7X8y9Z0a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0u1V2w3X4y5Z6a7B8c9D0e1F2g3H4i5J6k7L8m9N0o1P2q3R4s5T6u7V8w9X0y1Z2"
    ),
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

# Create ECR repositories with unique names and force delete
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

# Enhanced user data script (optimized for t2.micro)
user_data = f"""#!/bin/bash
# Update system (but don't upgrade to save time and resources)
apt-get update

# Install Docker (lighter installation for t2.micro)
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
usermod -aG docker ubuntu

# Install Docker Compose (lighter version)
curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
apt-get install -y unzip curl jq

# Extract and install AWS CLI
unzip awscliv2.zip
./aws/install
rm -rf aws awscliv2.zip get-docker.sh

# Configure Docker for t2.micro (limit resources)
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'DOCKER_EOF'
{{
  "log-driver": "json-file",
  "log-opts": {{
    "max-size": "10m",
    "max-file": "3"
  }},
  "storage-driver": "overlay2"
}}
DOCKER_EOF

# Start services
systemctl enable docker
systemctl start docker

# Wait for Docker to be ready
timeout=60
while ! docker info > /dev/null 2>&1 && [ $timeout -gt 0 ]; do
    sleep 2
    timeout=$((timeout-2))
done

# Create completion marker - THIS IS IMPORTANT
echo "Setup complete at $(date)" > /home/ubuntu/setup-info.txt
echo "Instance type: t2.micro" >> /home/ubuntu/setup-info.txt
echo "Docker status: $(systemctl is-active docker)" >> /home/ubuntu/setup-info.txt
chown ubuntu:ubuntu /home/ubuntu/setup-info.txt

# Release package manager locks explicitly
apt-get clean
rm -f /var/lib/apt/lists/lock
rm -f /var/lib/dpkg/lock-frontend
rm -f /var/lib/dpkg/lock

echo "User data script completed successfully" >> /home/ubuntu/setup-info.txt
"""

# Create EC2 instance
instance = aws.ec2.Instance("mlops-instance",
    key_name=key.key_name,
    instance_type="t2.micro",  # Changed to t2.micro for free tier/sandbox
    ami="ami-0df7a207adb9748c7",  # Ubuntu 22.04 LTS in ap-southeast-1
    subnet_id=public_subnet.id,
    vpc_security_group_ids=[security_group.id],
    user_data=user_data,
    root_block_device=aws.ec2.InstanceRootBlockDeviceArgs(
        volume_type="gp2",  # Changed to gp2 for free tier compatibility
        volume_size=20,     # Reduced to 20GB for free tier
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