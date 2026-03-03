aws_region         = "ap-south-1"
cluster_name       = "bloggerapp-eks"
node_instance_type = "t3.medium"
node_desired_count = 2
node_min_count     = 1
node_max_count     = 3
vpc_cidr           = "10.0.0.0/16"
