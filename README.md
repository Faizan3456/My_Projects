# DevOps/SRE Projects Portfolio

This repository is a central portfolio showcasing my hands-on DevOps projects.  
It highlights cloud infrastructure deployment, CI/CD automation, security best practices, and clear technical documentation.

---

## Extended Description

This portfolio documents my hands-on journey into DevOps by building, deploying, and automating real infrastructure on AWS.  
Rather than relying only on theory, these projects focus on practical implementation, security awareness, and automation.

The work begins with manual cloud infrastructure provisioning to establish a strong foundation in AWS, Linux systems, and web server configuration.  
It then progresses to CI/CD automation using GitHub Actions, demonstrating how manual deployment processes can be transformed into reliable and repeatable pipelines.  
Infrastructure is later managed using Terraform to ensure reproducibility, consistency, and Infrastructure as Code best practices.

Across these projects, I apply core DevOps principles such as:
- Infrastructure ownership and responsibility
- Automation of repetitive tasks
- Secure handling of credentials and access
- Clear and maintainable documentation
- Verification of deployments through real-world testing

This repository serves as a central index, while each linked repository contains detailed technical implementation and supporting evidence.

---

## 🔹 Project 1: AWS EC2 Apache Deployment

### Overview
Deployed a static website on AWS EC2 using Amazon Linux 2023 and Apache HTTP Server, with proper network security configuration.

### Key Concepts
- AWS EC2
- Security Groups
- Linux administration
- Apache HTTP Server

### What I Did
- Secured AWS root account and used IAM for daily access
- Launched and configured an EC2 instance
- Configured SSH and HTTP access via security groups
- Installed and enabled Apache
- Deployed and verified a custom website

### Repository
🔗 https://github.com/Faizan3456/aws-ec2-apache-deployment

---

## 🔹 Project 2: CI/CD Deployment to AWS EC2

### Overview
Built a CI/CD pipeline using GitHub Actions to automatically deploy website updates to an AWS EC2 instance on every commit.

### Key Concepts
- GitHub Actions
- CI/CD pipelines
- SSH-based deployment
- GitHub Secrets
- AWS EC2

### What I Did
- Created a GitHub Actions workflow
- Stored credentials securely using GitHub Secrets
- Automated deployment of website files to EC2
- Restarted Apache automatically
- Verified live updates after each commit

### Repository
🔗 https://github.com/Faizan3456/aws-ec2-cicd-website

---

## 🔹 Project 3: AWS EC2 Apache Deployment with Terraform

### Overview
Provisioned a secure AWS EC2 web server using **Terraform (Infrastructure as Code)**.  
The project automates EC2 creation, security group configuration, Apache installation, and exposes the application via a public URL.

### Key Concepts
- Terraform (Infrastructure as Code)
- AWS EC2
- Security Groups
- Amazon Linux 2023
- Apache HTTP Server

### What I Did
- Designed reusable Terraform configuration
- Dynamically fetched the latest Amazon Linux AMI
- Restricted SSH access to a single IP using CIDR rules
- Automated server bootstrapping using `user_data`
- Verified deployment through a live browser endpoint
- Managed the full infrastructure lifecycle using Terraform

### Repository
🔗 https://github.com/Faizan3456/aws-ec2-terraform-deployment

---

## 🔹 Project 4: AWS EC2 Deployment Behind Application Load Balancer (Terraform)

### Overview
Provisioned a highly available AWS web architecture using **Terraform (Infrastructure as Code)** by deploying multiple EC2 instances behind an **Application Load Balancer (ALB)**.

### Key Concepts
- Application Load Balancer (ALB)
- Target Groups and Health Checks
- Multi-EC2 architecture
- Infrastructure as Code (Terraform)
- Secure networking (Security Groups)

### What I Did
- Designed Terraform configuration to provision ALB and EC2 resources
- Deployed multiple EC2 instances running Apache HTTP Server
- Configured security groups to control traffic flow between ALB and instances
- Implemented target groups with health checks
- Verified load balancing by observing traffic distribution across instances
- Managed the complete infrastructure lifecycle using Terraform

### Repository
🔗 https://github.com/Faizan3456/aws-terraform-ec2-alb

---

## 🧠 Skills Demonstrated
- AWS infrastructure fundamentals
- Linux server management
- Web server configuration
- CI/CD automation
- Infrastructure as Code (Terraform)
- Load balancing and high availability
- Secure credential handling
- Cloud security best practices
- Technical documentation

---
## 🔹 Project 5: IBM MQ SRE Lab on AWS (Sender / Receiver, Monitoring & Automation)

### Overview
Designed and implemented a **production-style IBM MQ sender/receiver topology** on AWS EC2 using Docker, with a strong focus on **Site Reliability Engineering (SRE)** practices, including secure channel authentication (CHLAUTH), proactive monitoring, automation, and incident simulation.

This project goes beyond basic MQ setup and demonstrates how messaging platforms are **operated, monitored, and recovered** in real enterprise environments.

### Key Concepts
- IBM MQ (Sender / Receiver Queue Managers)
- MQ Channels, XMITQs, Remote and Local Queues
- CHLAUTH (Channel Authentication) security
- AWS EC2 networking (private IP communication)
- Docker-based MQ deployment
- Split-horizon monitoring design
- systemd-based automation
- Incident response and runbooks

### What I Did
- Deployed IBM MQ Queue Managers in Docker containers on separate AWS EC2 instances
- Designed a sender/receiver messaging flow using:
  - Sender QM with remote queue and transmission queue
  - Receiver QM with local queue and TCP listener
- Diagnosed and resolved **channel authentication failures** caused by default CHLAUTH rules
- Implemented least-privilege CHLAUTH rules using `ADDRESSMAP` to securely allow sender connections
- Built **split-horizon monitoring**:
  - Sender-side monitoring of XMITQ backlog depth with OK / WARN / CRIT thresholds
  - Receiver-side monitoring of listener and channel availability
- Automated monitoring execution using **systemd timers** instead of cron
- Simulated real production incidents (“game day”) by:
  - Stopping listeners and channels
  - Injecting message backlogs
  - Observing alerts and queue growth
  - Performing controlled recovery and validation
- Documented operational **runbooks**, captured evidence, and validated recovery to steady state

### Repository
🔗 https://github.com/Faizan3456/ibm-mq-sre-lab


---

## 🔹 Project 6: UK Job Agent — Autonomous LinkedIn Application Bot

### Overview
An **autonomous job application bot** that searches LinkedIn, scores every job using Claude AI against a personalised MasterPrompt (skills, sponsorship rules, salary floor), tailors the CV per application, and submits — fully automatically for LinkedIn Easy Apply, semi-automatically for external ATS platforms (Workday, Greenhouse, Lever, iCIMS, etc.).

Built specifically for UK Skilled Worker visa sponsorship roles in banking, payments, and infrastructure support.

### Key Concepts
- Claude AI (Haiku for fast parallel scoring, Sonnet for CV tailoring)
- Playwright browser automation
- LinkedIn Easy Apply automation
- External ATS automation (Workday, Greenhouse, Lever)
- Parallel job scoring with ThreadPoolExecutor
- AI-generated LinkedIn search queries from CV + prompt
- Tailored CV and cover letter generation per application

### What It Does
- **Phase 0** — Claude reads the candidate CV + MasterPrompt and generates targeted LinkedIn search queries
- **Phase 1** — Searches LinkedIn with all queries, collects unique job URLs
- **Phase 2** — Scrapes each job page (title, company, full description) with bot-detection avoidance
- **Phase 3** — Scores all jobs in parallel using Claude Haiku with a weighted formula (Role 30%, Tech 25%, Sponsorship 25%, Salary 10%, Company 10%)
- **Phase 4** — Ranks jobs, shows full breakdown table with reasons
- **Phase 5** — For top N jobs: generates tailored CV + cover letter with Claude Sonnet, then submits via Easy Apply (fully automatic) or external ATS (auto-fills, pauses for login and review)

### Scoring Formula
| Dimension | Weight |
|---|---|
| Role Alignment | 30% |
| Technology Match | 25% |
| Sponsorship Probability | 25% |
| Salary Probability | 10% |
| Company Quality | 10% |

Apply if score ≥ 60. Hard skip if sponsorship explicitly unavailable, salary below £45,000, or role outside the UK.

### Repository
🔗 https://github.com/Faizan3456/UK-Job-Agent


## 📌 About Me
I am building hands-on DevOps experience by designing, deploying, automating, and documenting real-world infrastructure and deployment workflows.  
My focus is on automation, reliability, and security.
