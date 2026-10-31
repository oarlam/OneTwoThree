# =====================================================================
# Auth / Cognito imports
# =====================================================================
import {
  to = aws_cognito_user_pool.main
  id = "us-east-1_GvyvKxQYy"
}

import {
  to = aws_cognito_user_pool_domain.main
  id = "meetings-859464366778"
}

import {
  to = aws_cognito_user_pool_client.main
  id = "us-east-1_GvyvKxQYy/2id3ee5uhgur9lfh0lu1gmd7dl"
}

import {
  to = aws_cognito_identity_provider.google[0]
  id = "us-east-1_GvyvKxQYy:Google"
}

# =====================================================================
# Reports imports
# =====================================================================
import {
  to = aws_vpc_endpoint.s3
  id = "vpce-0c2c1b2a4c90ccfe9"
}

import {
  to = aws_s3_bucket.reports
  id = "meetings-reports-859464366778"
}

import {
  to = aws_s3_bucket_lifecycle_configuration.reports
  id = "meetings-reports-859464366778"
}

import {
  to = aws_sqs_queue.report_requests_dlq
  id = "https://sqs.us-east-1.amazonaws.com/859464366778/meetings-report-requests-dlq"
}

import {
  to = aws_sqs_queue.report_requests
  id = "https://sqs.us-east-1.amazonaws.com/859464366778/meetings-report-requests"
}

import {
  to = aws_sqs_queue_policy.report_requests
  id = "https://sqs.us-east-1.amazonaws.com/859464366778/meetings-report-requests"
}

import {
  to = aws_iam_role.scheduler
  id = "meetings-reports-SchedulerRole-PgW1EbW3jyK8"
}

import {
  to = aws_iam_role_policy.scheduler
  id = "meetings-reports-SchedulerRole-PgW1EbW3jyK8:SendReportRequestPolicy"
}

import {
  to = aws_scheduler_schedule.weekly_report
  id = "default/meetings-weekly-report"
}

import {
  to = aws_cloudwatch_log_group.report_builder
  id = "/aws/lambda/meetings-report-builder"
}

import {
  to = aws_iam_role.report_builder
  id = "meetings-reports-ReportBuilderRole-9p5DV7A64jzz"
}

import {
  to = aws_iam_role_policy_attachment.report_builder_vpc
  id = "meetings-reports-ReportBuilderRole-9p5DV7A64jzz/arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

import {
  to = aws_iam_role_policy_attachment.report_builder_sqs
  id = "meetings-reports-ReportBuilderRole-9p5DV7A64jzz/arn:aws:iam::aws:policy/service-role/AWSLambdaSQSQueueExecutionRole"
}

import {
  to = aws_iam_role_policy.report_builder_s3
  id = "meetings-reports-ReportBuilderRole-9p5DV7A64jzz:S3PutReportPolicy"
}

import {
  to = aws_lambda_function.report_builder
  id = "meetings-report-builder"
}

import {
  to = aws_lambda_event_source_mapping.report_queue
  id = "e4af97cf-10bd-4510-9081-39543531aca9"
}

import {
  to = aws_cloudwatch_log_group.report_mailer
  id = "/aws/lambda/meetings-report-mailer"
}

import {
  to = aws_iam_role.report_mailer
  id = "meetings-reports-ReportMailerRole-4jHGz6Dnh0an"
}

import {
  to = aws_iam_role_policy_attachment.report_mailer_basic
  id = "meetings-reports-ReportMailerRole-4jHGz6Dnh0an/arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

import {
  to = aws_iam_role_policy.report_mailer
  id = "meetings-reports-ReportMailerRole-4jHGz6Dnh0an:MailerPermissions"
}

import {
  to = aws_lambda_function.report_mailer
  id = "meetings-report-mailer"
}

# =====================================================================
# AI / Agenda Parser imports
# =====================================================================
import {
  to = aws_iam_role.agenda_parser
  id = "meetings-agenda-parser-role"
}

import {
  to = aws_iam_role_policy_attachment.agenda_parser_basic
  id = "meetings-agenda-parser-role/arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

import {
  to = aws_iam_role_policy.agenda_parser_bedrock
  id = "meetings-agenda-parser-role:BedrockAccess"
}

import {
  to = aws_lambda_function.agenda_parser
  id = "meetings-agenda-parser"
}

import {
  to = aws_lambda_function_url.agenda_parser
  id = "meetings-agenda-parser"
}


import {
  to = aws_lambda_permission.report_mailer_s3
  id = "meetings-report-mailer/meetings-reports-ReportMailerPermission-wuvHNM5HwI7t"
}

import {
  to = aws_lambda_permission.agenda_parser_url
  id = "meetings-agenda-parser/meetings-ai-AgendaParserFunctionUrlPermission-ljKGFgu1hYEZ"
}

import {
  to = aws_lambda_permission.agenda_parser_invoke
  id = "meetings-agenda-parser/meetings-ai-AgendaParserFunctionInvokePermission-QbtAMZLWFdz5"
}

import {
  to = aws_s3_bucket_notification.reports
  id = "meetings-reports-859464366778"
}

import {
  to = aws_cognito_managed_login_branding.main
  id = "us-east-1_GvyvKxQYy,e8ac03db-baa9-408c-869a-6fee6735cdbd"
}
