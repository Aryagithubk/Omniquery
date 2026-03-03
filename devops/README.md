# BloggerApp K8s DevOps Infrastructure

This repository contains the complete Infrastructure as Code (Terraform), Kubernetes manifests, and GitHub Actions CI/CD pipeline to deploy the BloggerApp (React frontend + Node.js backend) onto AWS EKS.

> **💰 AWS Cost Warning**: Leaving this infrastructure running will incur AWS costs (around ~$150/month for the EKS Control Plane + LoadBalancers + EC2 instances). **Use the Tear Down instructions below to delete all resources when you are not actively using them!**

---

## 🚀 1. Infrastructure Setup (Creating Resources)

Whenever you want to spin up your BloggerApp environment from scratch, run these commands.

### Prerequisites
* AWS CLI configured (`aws configure`)
* Terraform installed
* `kubectl` and `helm` installed

### Provision AWS EKS
```bash
cd devops/terraform

# Initialize Terraform plugins
terraform init

# Create the VPC, EKS Cluster, and EC2 Worker Nodes (~15 minutes)
terraform apply -auto-approve

# Connect kubectl to your new cluster
aws eks update-kubeconfig --region ap-south-1 --name bloggerapp-eks
```

### Deploy the Application & Monitoring
Once the cluster is up, deploy the K8s manifests from the root of the project:
```bash
cd ../..

# Create namespaces
kubectl apply -f devops/k8s/namespaces.yaml

# Apply Secrets (Edit devops/k8s/backend-secret.yaml with real values first)
kubectl apply -f devops/k8s/backend-secret.yaml

# Deploy Backend and Frontend
kubectl apply -f devops/k8s/backend-deployment.yaml
kubectl apply -f devops/k8s/frontend-deployment.yaml

# Install Prometheus & Grafana Monitoring
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f devops/k8s/monitoring-values.yaml
```

---

## 🌐 2. Getting Live URLs

It takes `~2-3 minutes` for AWS to provision the LoadBalancers after you apply the manifests. To get your live URLs:

**Frontend React Web App:**
```bash
kubectl get svc -n frontend frontend-service -o jsonpath='{"http://"}{.status.loadBalancer.ingress[0].hostname}'
```

**Grafana Dashboard:**
```bash
kubectl get svc -n monitoring monitoring-grafana -o jsonpath='{"http://"}{.status.loadBalancer.ingress[0].hostname}:3000'
```
* **Grafana Username:** `admin`
* **Grafana Password:** `admin` *(Set in `monitoring-values.yaml`)*

---

## 💻 3. SSH into Pods & Worker Nodes

### SSH into your Pods (Containers)
To look at logs, environment variables, or files inside your running applications:

**Backend (Node.js):**
```bash
# 1. Get the exact Pod Name
kubectl get pods -n backend

# 2. SSH into the pod (replace <POD_NAME>)
kubectl exec -it <POD_NAME> -n backend -- /bin/sh
# Example inside pod: printenv | grep MONGO
```

**Frontend (Nginx/React):**
```bash
# 1. Get exact Pod Name
kubectl get pods -n frontend

# 2. SSH into the pod
kubectl exec -it <POD_NAME> -n frontend -- /bin/sh
# Example inside pod: ls /usr/share/nginx/html
```

### SSH into AWS EC2 Worker Nodes
Terraform creates standard EC2 instances inside a managed node group. We use AWS Systems Manager (SSM) instead of traditional SSH keys for security.
```bash
# 1. Get the instance IDs of your worker nodes
aws ec2 describe-instances --filters "Name=tag:eks:cluster-name,Values=bloggerapp-eks" --query "Reservations[*].Instances[*].InstanceId" --region ap-south-1

# 2. Open an interactive shell session to the node
aws ssm start-session --target <i-XXXXXXXXXXXX> --region ap-south-1
```

---

## ⚙️ 4. GitHub Actions CI/CD Pipeline

The `.github/workflows/ci-cd.yml` file automates the build and deployment process.

1. **Trigger**: Any `git push origin main` triggers the workflow.
2. **Build**: It conditionally builds the `client/` or `server/` Docker images only if those folders have changes.
3. **Push**: It pushes images to your DockerHub (`aryasingh55`) with a unique Git commit tag.
4. **Deploy**: It securely connects to EKS via your stored AWS Secrets and performs a `kubectl set image` rolling update with zero downtime.

**Required GitHub Secrets:**
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

---

## 🗑️ 5. Tear Down Infrastructure (Save Money!)

When you are done working with your application, you **must delete** the resources so AWS stops charging you.

**Step 1: Delete Kubernetes LoadBalancers FIRST**
AWS ELBs created by Kubernetes can block Terraform from deleting the VPC. Destroy K8s objects first:
```bash
# This cleans up the Classic LoadBalancers attached to EKS
kubectl delete namespace frontend backend monitoring
```
*(Wait 1-2 minutes for the namespaces to fully terminate).*

**Step 2: Destroy AWS Infrastructure via Terraform**
```bash
cd devops/terraform

# This will delete the EKS Cluster, Node Groups, VPC, and all related resources
terraform destroy -auto-approve
```
It takes about ~10-15 minutes to completely destroy the cluster. After this completes, you will have **$0 ongoing AWS charges** for this project. When you want to develop again, just start from "Provision AWS EKS" at the top!
