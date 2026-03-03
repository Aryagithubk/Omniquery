# BloggerApp DevOps

Complete DevOps setup: **AWS EKS** (Terraform) + **GitHub Actions CI/CD** + **Prometheus & Grafana** monitoring.

## Architecture

```
GitHub Push → GitHub Actions → DockerHub → EKS Cluster
                                              ├── frontend namespace (React/Nginx)
                                              ├── backend namespace  (Node.js/Express)
                                              └── monitoring namespace (Prometheus + Grafana via Helm)
```

## Prerequisites

- [AWS CLI](https://aws.amazon.com/cli/) configured with IAM credentials
- [Terraform](https://www.terraform.io/downloads) >= 1.0
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [Helm](https://helm.sh/docs/intro/install/) >= 3.0
- [Docker](https://docs.docker.com/get-docker/) (for local testing)
- DockerHub account (free tier)

---

## 1. Provision AWS Infrastructure (Terraform)

```bash
cd devops/terraform

# Initialize Terraform
terraform init

# Preview the infrastructure
terraform plan

# Create the infrastructure (takes ~15 min)
terraform apply

# Configure kubectl
aws eks update-kubeconfig --region ap-south-1 --name bloggerapp-eks
```

## 2. Deploy Kubernetes Resources

```bash
# Create namespaces
kubectl apply -f devops/k8s/namespaces.yaml

# Create backend secrets (EDIT VALUES FIRST!)
# Generate base64: echo -n "your-value" | base64
kubectl apply -f devops/k8s/backend-secret.yaml

# Deploy backend and frontend
kubectl apply -f devops/k8s/backend-deployment.yaml
kubectl apply -f devops/k8s/frontend-deployment.yaml
```

## 3. Install Monitoring (Helm)

```bash
# Add Prometheus Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install kube-prometheus-stack in monitoring namespace
helm install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  -f devops/k8s/monitoring-values.yaml
```

## 4. Configure GitHub Secrets

Go to your GitHub repo → **Settings → Secrets and variables → Actions** → Add these secrets:

| Secret | Description |
|---|---|
| `DOCKERHUB_USERNAME` | Your DockerHub username |
| `DOCKERHUB_TOKEN` | DockerHub access token ([create here](https://hub.docker.com/settings/security)) |
| `AWS_ACCESS_KEY_ID` | AWS IAM access key |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM secret key |

## 5. Access Services

```bash
# Get frontend URL (LoadBalancer)
kubectl get svc frontend-service -n frontend

# Get Grafana URL (LoadBalancer)
kubectl get svc -n monitoring | grep grafana
# Default login: admin / admin

# Port-forward Prometheus (if needed)
kubectl port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090 -n monitoring
```

## 6. Verify Everything

```bash
# Check all pods
kubectl get pods -A

# Check all services
kubectl get svc -A

# Check nodes
kubectl get nodes
```

---

## CI/CD Flow

1. Push code to `main` branch
2. GitHub Actions detects changes in `client/` or `server/`
3. Builds Docker image and pushes to DockerHub with commit SHA tag
4. Updates EKS deployment with new image → rolling update

## Cost Breakdown (Estimated)

| Resource | Cost |
|---|---|
| EKS Control Plane | ~$73/month |
| 2× t3.medium (On-Demand) | ~$60/month |
| LoadBalancer (ELB) | ~$18/month |
| **Total** | **~$151/month** |

> **Tip**: To reduce costs, scale down to 1 node when not in use:
> ```bash
> aws eks update-nodegroup-config --cluster-name bloggerapp-eks \
>   --nodegroup-name bloggerapp-eks-workers \
>   --scaling-config minSize=0,maxSize=3,desiredSize=0 \
>   --region ap-south-1
> ```

## Tear Down

```bash
# Remove K8s resources
kubectl delete -f devops/k8s/

# Uninstall monitoring
helm uninstall monitoring -n monitoring

# Destroy AWS infrastructure
cd devops/terraform
terraform destroy
```
