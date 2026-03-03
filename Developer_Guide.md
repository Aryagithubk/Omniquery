# End-to-End Developer Guide (AWS EKS & CI/CD Pipeline)

Welcome to the Developer Guide for the BloggerApp!
Whether you are completely new to DevOps or looking to understand the mechanics of cloud-native applications, this guide is designed for you. We will go through every step in detail—explaining *what* we're doing, and *why* we're doing it.

By the end of this guide, you will have:
- A live React Frontend.
- A secure Node.js Backend running on Kubernetes.
- A fully automated CI/CD pipeline linking your code to the cloud.
- A beautiful monitoring dashboard using Prometheus and Grafana.

---

## 🏗️ Phase 1: Local Setup

Before we start building our cloud infrastructure on AWS, we need to set up our personal computer. Think of this as gathering your tools before stepping onto a construction site.

### 1. Prerequisite Installations (The Tools)
You will need the following programs installed on your computer. Here is what they do:
1. **[Git](https://git-scm.com/downloads)**: This is our version control system. It allows you to safely download (clone) the project code to your machine.
2. **[AWS CLI](https://aws.amazon.com/cli/)**: The Amazon Web Services Command Line Interface. Instead of clicking through the AWS website, this tool lets your terminal talk directly to AWS to create and manage resources securely.
3. **[Terraform](https://developer.hashicorp.com/terraform/downloads)** (>= v1.0): An "Infrastructure as Code" (IaC) tool. Instead of manually clicking to buy servers and set up networks, we write configuration files that describe what we want, and Terraform mathematically provisions it for us automatically.
4. **[kubectl](https://kubernetes.io/docs/tasks/tools/)**: The Kubernetes Command Line Tool. Once our Kubernetes "cluster" (group of computers) is physically built by Terraform, `kubectl` acts as our remote control to deploy our apps into it.
5. **[Helm](https://helm.sh/docs/intro/install/)** (>= v3.0): Think of Helm as the "App Store" or package manager for Kubernetes. It helps us install complex third-party applications (like our Grafana monitoring dashboard) using just a single command.

### 2. AWS Authentication (Gaining Access)
To let your terminal speak to AWS, it needs a secure ID badge allowing the API access.
1. Sign in to your AWS Console via your web browser.
2. Go to **IAM (Identity and Access Management)** and create a User with `AdministratorAccess` permissions.
3. Generate an **Access Key** for this user. This gives you two strings: an *Access Key ID* and a *Secret Key*.

Now, let's inject this ID badge into your terminal:
```bash
aws configure
```
* **AWS Access Key ID**: Paste the Access Key ID provided by AWS.
* **AWS Secret Access Key**: Paste the Secret Key provided by AWS.
* **Default region name**: `ap-south-1` (This tells AWS to build our computers physically in Mumbai, India. You can change this to `us-east-1` or elsewhere if desired).
* **Default output format**: `json` (This formats the CLI responses so they are easy for humans to read).

### 3. Clone the Repository (Getting the Code)
Let's download the DevOps code base (and application configurations) onto your machine.
```bash
git clone https://github.com/Aryagithubk/k8s_blogger_devops.git
cd k8s_blogger_devops
```

---

## 🚀 Phase 2: Provision Infrastructure (Terraform)

Now that our local tools are ready, we need to rent some servers and networking equipment from Amazon. Traditionally, this is hours of manual clicking. We use Terraform to handle it in minutes.

Terraform reads the code in the `devops/terraform/` folder and guarantees AWS creates exactly what is written. It handles the complicated Virtual Private Cloud (VPC), subnets, routing, and creates an elastic server park called Amazon EKS (Elastic Kubernetes Service).

1. **Enter the Terraform folder:**
   ```bash
   cd devops/terraform
   ```

2. **Initialize Terraform:**
   This downloads the necessary plugins Terraform needs specifically to communicate with AWS.
   ```bash
   terraform init
   ```

3. **Build the Architecture:**
   *Warning: Running this command starts your AWS billing! It physically creates the AWS billable resources.*
   ```bash
   terraform apply -auto-approve
   ```
   *(Wait ~15 - 20 minutes. Behind the scenes, AWS is spinning up servers, load balancers, and linking them all together into a central Kubernetes cluster).*

4. **Connect your Computer to the Cluster:**
   Once Terraform finishes building the EKS cluster, your computer doesn't automatically know how to talk to it. This command updates your local `kubectl` configuration file so it has the authorization to enter your newly formed cluster.
   ```bash
   aws eks update-kubeconfig --region ap-south-1 --name bloggerapp-eks
   ```

---

## ⚙️ Phase 3: Setup CI/CD Secrets (GitHub Actions)

We want an automated system where every time we push new application code to GitHub, it is built and deployed directly to our AWS servers. This concept is called Continuous Integration / Continuous Deployment (CI/CD).

For GitHub to execute this automation securely, we need to give it passwords to access DockerHub (to store the packaged application images) and AWS (to deploy to the EKS cluster). 

1. Go to your **GitHub Repository > Settings > Secrets and variables > Actions**.
2. Click **New repository secret**. Add the following four keys exactly as named:
   * `AWS_ACCESS_KEY_ID`: *(Your AWS Access Key ID)*
   * `AWS_SECRET_ACCESS_KEY`: *(Your AWS Secret Key)*
   * `DOCKERHUB_USERNAME`: *(Your explicit DockerHub username, e.g., aryasingh55)*
   * `DOCKERHUB_TOKEN`: *(A Personal Access Token generated from your DockerHub account security settings. Do not use your regular account password for security reasons).*

Now, the GitHub cloud has the authority to safely push updates into your environment.

---

## 📦 Phase 4: Deploy Kubernetes Workloads

It's time to actually launch the BloggerApp services into the empty Kubernetes cluster.

1. **Create Namespaces (Organizing the Cluster):**
   Namespaces are like virtual folders inside your cluster. By creating separate namespaces (`frontend`, `backend`, `monitoring`), we keep our systems logically organized and prevent accidental overlaps.
   ```bash
   cd ../..  # Go back into the main root project folder
   kubectl apply -f devops/k8s/namespaces.yaml
   ```

2. **Encode App Passwords (Kubernetes Secrets):**
   Our backend Node.js application needs to connect to an external Database (like MongoDB). We cannot place raw passwords in our configuration files. Kubernetes demands we convert strings into Base64 format as a rudimentary encryption standard before ingestion.
   
   Run this command in your terminal, replacing `my-mongo-url-string` with your actual MongoDB URL:
   ```bash
   echo -n "my-mongo-url-string" | base64
   ```
   *(Copy the scrambled output sequence, open the `devops/k8s/backend-secret.yaml` file, and paste it where the `DATABASE_URL` value goes).*

3. **Deploy the Fleet Configurations:**
   Now we command Kubernetes to establish the blueprint for our backend, frontend, and secret keys. They won't have the active Docker image mapped securely until the next step, but this primes the cluster.
   ```bash
   kubectl apply -f devops/k8s/backend-secret.yaml
   kubectl apply -f devops/k8s/backend-deployment.yaml
   kubectl apply -f devops/k8s/frontend-deployment.yaml
   ```

4. **Kick off the automated CI/CD Pipeline:**
   Instead of manually packaging our app into Docker containers and copying them into the cluster by hand, we simply send a git update, letting the GitHub Actions runner take care of it entirely!
   ```bash
   git add .
   git commit -m "Trigger initial CI/CD pipeline deploy"
   git push origin main
   ```
   *(You can navigate to the "Actions" tab on your GitHub repository page to watch the automation build the images and deploy them seamlessly).*

---

## 📊 Phase 5: Install Grafana Monitoring

A professional application cannot run blindly. If the CPU spikes excessively or we suffer network drops, we need an alerting and monitoring interface. We will use Helm to install the industry-standard "Kube-Prometheus-Stack" (Prometheus collects the raw metrics, Grafana turns those metrics into beautiful graphs).

1. **Add the Prometheus Helm Repository:**
   This dictates where the Helm package manager searches to download the monitoring charts.
   ```bash
   helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
   helm repo update
   ```

2. **Install the Monitoring Stack:**
   This complex single command deploys the entire infrastructure metrics stack into the `monitoring` namespace using our custom pre-written configuration file values.
   ```bash
   helm install monitoring prometheus-community/kube-prometheus-stack \
     --namespace monitoring --create-namespace \
     -f devops/k8s/monitoring-values.yaml
   ```

---

## 🌐 Phase 6: Retrieve Active URLs

When everything is deployed successfully, AWS allocates public Elastic LoadBalancers to give your frontend and monitoring dashboards true internet addresses. Since these endpoints are dynamically generated by AWS during setup, we have to extract them.

**To access the Frontend App (The website users will see):**
```bash
kubectl get svc -n frontend frontend-service -o jsonpath='{"http://"}{.status.loadBalancer.ingress[0].hostname}'
```
*(Copy the resulting address and paste it directly into your web browser to interact with your live site!)*

**To access the Grafana Dashboard (The monitoring interface):**
```bash
kubectl get svc -n monitoring monitoring-grafana -o jsonpath='{"http://"}{.status.loadBalancer.ingress[0].hostname}:3000'
```
*(Open this URL in your web browser. To login to the Grafana dashboard, the standard default Username is `admin`, and Password is `prom-operator` — you will be immediately prompted to change the default password).*

**Why is there no public Backend URL?**
For enterprise security, the Backend is intentionally hidden inside the private Kubernetes intranet network. The frontend strictly communicates with it internally using an internal bridge: `backend.svc.cluster.local:5000`. This completely prevents external malicious attacks directly against your backend API!

---

## 💻 Phase 7: Debugging (When things go wrong)

In software development and operations, things break. When an application crashes, it is your job to act as an investigator.

### 1. Inspecting Kubernetes Pods (The Virtual Application Containers)
If your backend or frontend isn't reachable, you need to check the "Pod" running the specific code.

**Step A - Find out what is running:**
```bash
kubectl get pods -n backend
```
*(This command queries every pod inside the backend namespace. Pay attention to the `STATUS` column! You want to see `Running`. If you see `CrashLoopBackOff` or `Error`, the application keeps restarting).*

**Step B - Read the logs to see what crashed:**
```bash
kubectl logs <exact-pod-name> -n backend
```
*(This is the equivalent of reading standard console output for the code. Most of the time, this instantly tells you why the backend crashed—e.g., 'MongoDB Timeout' or 'Missing Variable').*

**Step C - Teleport exactly inside the Pod for advanced interaction:**
```bash
kubectl exec -it <exact-pod-name> -n backend -- /bin/sh
```
*(Once you drop into this shell, you are physically browsing files directly beside your runtime code inside Kubernetes. You can run `env` to prove secrets injected correctly or run active network checks. Type `exit` to return).*

### 2. Inspecting AWS Worker Nodes (The Physical Computers)
Occasionally, it's not the code that is failing, but the physical AWS computers hosting the cluster (Node Groups) might be starved for hardware RAM.

**Step A - Fetch your underlying AWS Machine IDs:**
```bash
aws ec2 describe-instances --filters "Name=tag:eks:cluster-name,Values=bloggerapp-eks" --query "Reservations[*].Instances[*].InstanceId" --region ap-south-1
```

**Step B - Open a remote shell directly inside the physical AWS EC2 node:**
```bash
aws ssm start-session --target <insert-instance-id> --region ap-south-1
```
*(Use this to monitor heavy OS level processes like `top` or check deeply configured kernel logs).*

---

## 🗑️ Phase 8: Tear Down Instructions (Stop Cloud Billing)

**CRITICAL WARNING:** Leaving this entire enterprise AWS architecture running 24/7 indefinitely will slowly burn billing resources. This setup specifically costs roughly **~$150/month**. 

If you are just executing this guide for learning or testing, you MUST destroy the environment completely when finished to return your cost perfectly down to **$0.00**.

**Step 1: Destroy Kubernetes Resources (LoadBalancers)**
AWS automatically creates separate physical routing resources (ELB LoadBalancers) when traffic routes are exposed using Kubernetes services. If these are not deleted gracefully via Kubernetes *before* Terraform destruction, AWS will get extremely confused and the server tear-down will fail.
```bash
kubectl delete namespace frontend backend monitoring
```
*(Ensure you wait a full 1 to 2 minutes for the namespace deletion loops to finalize entirely).*

**Step 2: Destroy Terraform Infrastructure**
Once the Kubernetes layer is scrubbed, tell Terraform to analyze the original blueprint configuration, and formally execute a delete command across every remaining provisioned AWS asset.
```bash
cd devops/terraform
terraform destroy -auto-approve
```
*(This takes ~10 minutes. Once you are returned to your terminal prompt, your cloud footprint physically ceases to exist and billing accurately neutralizes).*

---

## 📚 General Devops command line Dictionary

Here is a summarized cheat sheet for the critical terminal commands you will use to pilot the DevOps architecture:

| Command | What it does & When to use it |
|---|---|
| `terraform validate` | **Syntax Check:** Analyzes your Terraform module code looking for formatting typos or missing strings locally, before trying to build it remotely. |
| `terraform plan` | **Dry-Run Predictor:** Safely queries live AWS infrastructure and compares it against your local files. Tells you exactly what *would* happen if you applied the changes. Excellent sanity check. |
| `kubectl get pods -A` | **Check Health:** Lists every single tiny workload container across the whole cluster. Look for the `Running` state! |
| `kubectl describe pod <podname> -n <namespace>` | **Diagnostic Event Scan:** If a pod fails to start, this command is invaluable. It prints the active Kubernetes event diary (e.g. "Ran out of memory", "Invalid container image tag", "Failed mount"). |
| `kubectl logs <podname> -n <namespace>` | **Reading Output Data:** Streams the active standard application output from your internal files directly out locally. Helpful to observe application behavior just like `npm start`. |
| `kubectl get svc -A` | **Network Mapping:** Provides an index of every virtual `ClusterIP` router port currently listening, including showing which LoadBalancers map to the wide-open internet. |

---
*Happy Building and automating your infrastructure!*
