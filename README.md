# DevOps Projects Portfolio

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

## 🧠 Skills Demonstrated
- AWS infrastructure fundamentals
- Linux server management
- Web server configuration
- CI/CD automation
- Infrastructure as Code (Terraform)
- Secure credential handling
- Cloud security best practices
- Technical documentation

---

## 📌 About Me
I am building hands-on DevOps experience by designing, deploying, automating, and documenting real-world infrastructure and deployment workflows.  
My focus is on automation, reliability, and security.
