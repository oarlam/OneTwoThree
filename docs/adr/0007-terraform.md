# ADR 0007: Migrating Infrastructure from CloudFormation to Terraform & HCP Terraform

- **Status**: Accepted
- **Date**: 2026-10-31
- **Context**: Meetings Application (Spry) — Lab 7

---

## Context

In Labs 4, 5, and 6, we introduced three CloudFormation templates to manage infrastructure:
- `infra/cognito.yaml` (Cognito User Pool, App Client, Domain, Google IdP, Managed Login)
- `infra/reports.yaml` (Weekly Report S3 Bucket, Gateway VPCEndpoint, SQS Queues, EventBridge Scheduler, Lambdas)
- `infra/ai.yaml` (Agenda Parser Lambda outside VPC, Function URL, IAM Bedrock permissions)

While CloudFormation successfully deployed these components, it introduced several long-term limitations:
1. **AWS-Only Boundary**: CloudFormation cannot manage external resources, such as Google Cloud OAuth credentials, GitHub repository webhooks/branch protection, or multi-cloud assets.
2. **Implicit Dependency & State Ownership**: CloudFormation maintains state internally inside AWS stacks. If a stack fails during complex updates, it rolls back or enters `UPDATE_ROLLBACK_FAILED`, requiring manual stack recovery.
3. **Lack of Uniform Plan Previews**: CloudFormation Change Sets are cumbersome and rarely integrated cleanly into team pull requests.
4. **Environment Portability**: Parameterizing environments (dev, stage, prod) across multiple accounts or providers requires maintaining complex nested stacks or custom scripts.

We need a unified Infrastructure as Code (IaC) tool that provides cross-provider support, centralized state management with locking, and automated CI/CD execution without distributing permanent AWS access keys.

---

## Decision

We migrate all application infrastructure from CloudFormation to **Terraform** managed via **HCP Terraform (formerly Terraform Cloud)** using a **VCS-driven workflow**:

```
Developer ──> Pull Request (GitHub) ──> HCP Terraform Speculative Plan
                     │
                   Merge
                     ▼
             HCP Terraform Apply (Assumes IAM OIDC Role)
                     │
         ┌───────────┼───────────┐
         ▼           ▼           ▼
      Cognito     Reports        AI
     (Auth)       (S3/SQS)   (Bedrock)
```

1. **Modular HCL Structure**:
   - `infra/versions.tf`: Configures HCP Terraform cloud backend (`ooad-oarlam` organization, `meetings-dev` workspace) and required providers (`aws`, `archive`).
   - `infra/variables.tf`: Defines strongly-typed inputs with sensible defaults and queries upstream base stacks (backend VPC, Aurora DB, ECR) via `data.aws_cloudformation_stack`.
   - `infra/auth.tf`: Replaces `cognito.yaml` with declarative `aws_cognito_*` resources.
   - `infra/reports.tf`: Replaces `reports.yaml` with `aws_s3_bucket`, `aws_sqs_queue`, `aws_scheduler_schedule`, and report Lambdas.
   - `infra/ai.tf`: Replaces `ai.yaml` with `aws_lambda_function` (agenda parser) and `aws_lambda_function_url`.
   - `infra/outputs.tf`: Exports clean outputs consumed by `Makefile` and frontend build steps via `terraform output -raw`.

2. **Zero-Loss Adoption (Importing Existing Infrastructure)**:
   - Added `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain` to all CloudFormation templates and redeployed them before deleting the stacks.
   - Deleted the CloudFormation stacks without touching any underlying AWS resources.
   - Used Terraform 1.5+ declarative `import` blocks in `infra/imports.tf` to bind existing physical IDs into Terraform state without recreation or downtime.
   - Verified that `terraform plan` produces `0 to destroy` and `0 to add` before applying.

3. **Dynamic Credentials via AWS OIDC**:
   - Eliminated long-lived AWS Access Keys in HCP Terraform.
   - Created an IAM OIDC Identity Provider for `https://app.terraform.io` and an IAM role `hcp-terraform-ooad-oarlam` with trust scoped to `organization:ooad-oarlam:*`.
   - HCP Terraform requests short-lived STS credentials for every plan and apply run.

---

## Alternatives Considered

### 1. Remaining on CloudFormation
- **Why it lost**: CloudFormation is strictly limited to AWS APIs. It cannot manage the Google OAuth project, GitHub repo protections, or external DNS, and lacks rich local plan preview ergonomics.

### 2. AWS CDK (Cloud Development Kit)
- **Why it lost**: While CDK provides programming language constructs (TypeScript/Python), it synthesizes into CloudFormation templates under the hood and remains subject to the same CloudFormation engine constraints, rollback bottlenecks, and single-provider limitations.

### 3. OpenTofu with S3 + DynamoDB Backend
- **Why it lost**: OpenTofu is a robust open-source alternative. However, managing an independent S3 bucket and DynamoDB state-locking table requires additional bootstrap infrastructure, manual key management, and custom CI pipelines. HCP Terraform provides free-tier remote state management, automated locking, and integrated OIDC runners out of the box.

---

## Consequences & Operational Model

### 1. Who can change infrastructure, and how?
- **Workflow**: No developer applies changes directly from their laptop. All infrastructure modifications are authored in `infra/*.tf`, pushed to GitHub, and reviewed in Pull Requests.
- **Verification**: HCP Terraform runs a speculative plan on the pull request. Once merged to `main`, HCP Terraform applies the changes automatically using its temporary OIDC credentials.

### 2. Where do secrets end up?
- **Sensitive Variables**: The Google OAuth client secret and sensitive parameters are marked with `sensitive = true` and stored in HCP Terraform workspace variables, never in git.
- **State File**: The state file (`terraform.tfstate`) is encrypted at rest (AES-256) and in transit (TLS 1.3) within HCP Terraform. Plans automatically mask sensitive values as `(sensitive value)`.

### 3. What happens if HCP Terraform is down?
- **Runtime Resilience**: Live AWS resources (Cognito, Aurora, Lambdas, S3) are completely decoupled from Terraform. They run independently inside AWS and suffer zero downtime if HCP Terraform experiences an outage.
- **Control Plane Fallback**: In an emergency where an immediate infrastructure fix is needed during an HCP Terraform outage, an engineer with temporary AWS credentials can authenticate locally, pull the state using Terraform CLI, or manage urgent AWS resources directly while preserving state integrity.

