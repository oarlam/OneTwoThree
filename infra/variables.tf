variable "project_name" {
  type        = string
  default     = "meetings"
  description = "Name prefix for all resources."
}

variable "region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region for resources."
}

variable "architecture" {
  type        = string
  default     = "arm64"
  description = "Architecture for Lambda functions (arm64 or x86_64)."
}

variable "parser_image_tag" {
  type        = string
  default     = "a34702f-dirty-20261028165838"
  description = "Container image tag for agenda parser Lambda."
}

variable "builder_image_tag" {
  type        = string
  default     = "486cfa2"
  description = "Container image tag for report builder Lambda."
}

variable "parser_model" {
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
  description = "Amazon Bedrock model ID for agenda parser."
}

variable "reports_from_email" {
  type        = string
  default     = "arlamovskao@gmail.com"
  description = "Sender email address for reports."
}

variable "reports_to_email" {
  type        = string
  default     = "arlamovskao@gmail.com"
  description = "Recipient email address for reports."
}

variable "callback_urls" {
  type = list(string)
  default = [
    "http://localhost:3000/auth/callback",
    "http://localhost:5173/auth/callback",
    "https://d2wrzrmr2gfc0v.cloudfront.net/auth/callback"
  ]
  description = "Cognito OAuth callback URLs."
}

variable "logout_urls" {
  type = list(string)
  default = [
    "http://localhost:3000/",
    "http://localhost:5173/",
    "https://d2wrzrmr2gfc0v.cloudfront.net/"
  ]
  description = "Cognito OAuth logout URLs."
}

variable "google_client_id" {
  type        = string
  default     = "740856258974-p226psbfmnalags4ai0sd7ppbdb5pqrb.apps.googleusercontent.com"
  description = "Google OAuth Client ID."
}

variable "google_client_secret" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Google OAuth Client Secret."
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "aws_cloudformation_stack" "backend" {
  name = "${var.project_name}-backend"
}

data "aws_cloudformation_stack" "backend_ecr" {
  name = "${var.project_name}-backend-ecr"
}

data "aws_secretsmanager_secret_version" "db" {
  secret_id = local.db_secret_arn
}

locals {
  vpc_id            = data.aws_cloudformation_stack.backend.outputs["VpcId"]
  route_table_id    = data.aws_cloudformation_stack.backend.outputs["PrivateRouteTableId"]
  security_group_id = data.aws_cloudformation_stack.backend.outputs["BackendSecurityGroupId"]
  subnet_ids = [
    data.aws_cloudformation_stack.backend.outputs["PrivateSubnet1Id"],
    data.aws_cloudformation_stack.backend.outputs["PrivateSubnet2Id"]
  ]
  db_host            = data.aws_cloudformation_stack.backend.outputs["DbEndpoint"]
  db_secret_arn      = data.aws_cloudformation_stack.backend.outputs["DbSecretArn"]
  ecr_repository_uri = data.aws_cloudformation_stack.backend_ecr.outputs["RepositoryUri"]
}
