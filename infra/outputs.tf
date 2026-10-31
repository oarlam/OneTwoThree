# Cognito / Auth outputs
output "user_pool_id" {
  description = "Cognito User Pool ID"
  value       = aws_cognito_user_pool.main.id
}

output "user_pool_client_id" {
  description = "Cognito User Pool Client ID"
  value       = aws_cognito_user_pool_client.main.id
}

output "hosted_ui_domain" {
  description = "Cognito Hosted UI Domain"
  value       = "${aws_cognito_user_pool_domain.main.domain}.auth.${var.region}.amazoncognito.com"
}

output "issuer" {
  description = "Cognito Token Issuer URL"
  value       = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
}

output "google_enabled" {
  description = "Whether Google OAuth is enabled"
  value       = var.google_client_id != "" ? "true" : "false"
}

# Reports outputs
output "reports_bucket_name" {
  description = "Reports S3 Bucket Name"
  value       = aws_s3_bucket.reports.bucket
}

output "queue_url" {
  description = "Reports Requests SQS Queue URL"
  value       = aws_sqs_queue.report_requests.id
}

output "dlq_url" {
  description = "Reports Requests DLQ URL"
  value       = aws_sqs_queue.report_requests_dlq.id
}

output "builder_function_name" {
  description = "Report Builder Lambda Function Name"
  value       = aws_lambda_function.report_builder.function_name
}

output "mailer_function_name" {
  description = "Report Mailer Lambda Function Name"
  value       = aws_lambda_function.report_mailer.function_name
}

output "schedule_arn" {
  description = "EventBridge Weekly Report Schedule ARN"
  value       = aws_scheduler_schedule.weekly_report.arn
}

# AI outputs
output "parser_function_url" {
  description = "Agenda Parser Lambda Function URL"
  value       = aws_lambda_function_url.agenda_parser.function_url
}

output "parser_function_name" {
  description = "Agenda Parser Lambda Function Name"
  value       = aws_lambda_function.agenda_parser.function_name
}

output "parser_function_arn" {
  description = "Agenda Parser Lambda Function ARN"
  value       = aws_lambda_function.agenda_parser.arn
}

