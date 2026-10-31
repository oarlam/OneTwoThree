# =====================================================================
# Storage: S3 Bucket & S3 Gateway Endpoint
# =====================================================================

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = local.vpc_id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [local.route_table_id]

  tags = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_s3_bucket" "reports" {
  bucket = "${var.project_name}-reports-${data.aws_caller_identity.current.account_id}"

  tags = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id

  rule {
    id     = "DeleteAfter90Days"
    status = "Enabled"

    expiration {
      days = 90
    }
  }

  rule {
    id     = "DeleteRequestsAfter1Day"
    status = "Enabled"

    filter {
      prefix = "requests/"
    }

    expiration {
      days = 1
    }
  }
}

# =====================================================================
# Queues: SQS & DLQ
# =====================================================================

resource "aws_sqs_queue" "report_requests_dlq" {
  name                      = "${var.project_name}-report-requests-dlq"
  message_retention_seconds = 1209600

  tags = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_sqs_queue" "report_requests" {
  name                       = "${var.project_name}-report-requests"
  visibility_timeout_seconds = 360

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.report_requests_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_sqs_queue_policy" "report_requests" {
  queue_url = aws_sqs_queue.report_requests.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "s3.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.report_requests.arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = aws_s3_bucket.reports.arn
        }
      }
    }]
  })
}

# =====================================================================
# Scheduler: EventBridge Scheduler
# =====================================================================

resource "aws_iam_role" "scheduler" {
  name = "meetings-reports-SchedulerRole-PgW1EbW3jyK8"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name = "SendReportRequestPolicy"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.report_requests.arn
    }]
  })
}

resource "aws_scheduler_schedule" "weekly_report" {
  name                         = "${var.project_name}-weekly-report"
  schedule_expression          = "cron(0 7 ? * MON *)"
  schedule_expression_timezone = "Europe/Kyiv"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sqs_queue.report_requests.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ week = null, source = "schedule" })
  }
}

# =====================================================================
# Builder Lambda (runs in VPC, reads Aurora, writes CSV to S3)
# =====================================================================

resource "aws_cloudwatch_log_group" "report_builder" {
  name              = "/aws/lambda/${var.project_name}-report-builder"
  retention_in_days = 7

  tags = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_iam_role" "report_builder" {
  name = "meetings-reports-ReportBuilderRole-9p5DV7A64jzz"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_iam_role_policy_attachment" "report_builder_vpc" {
  role       = aws_iam_role.report_builder.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy_attachment" "report_builder_sqs" {
  role       = aws_iam_role.report_builder.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaSQSQueueExecutionRole"
}

resource "aws_iam_role_policy" "report_builder_s3" {
  name = "S3PutReportPolicy"
  role = aws_iam_role.report_builder.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:PutObject",
        "s3:GetObject"
      ]
      Resource = "${aws_s3_bucket.reports.arn}/*"
    }]
  })
}

resource "aws_lambda_function" "report_builder" {
  function_name = "${var.project_name}-report-builder"
  package_type  = "Image"
  image_uri     = "${local.ecr_repository_uri}:${var.builder_image_tag}"

  image_config {
    command = ["app.reports.lambda_handler.handler"]
  }

  architectures = [var.architecture]
  memory_size   = 512
  timeout       = 60
  role          = aws_iam_role.report_builder.arn

  vpc_config {
    subnet_ids         = local.subnet_ids
    security_group_ids = [local.security_group_id]
  }

  environment {
    variables = {
      DB_HOST        = local.db_host
      DB_PORT        = "5432"
      DB_NAME        = "meetings"
      DB_USER        = "meetings"
      DB_PASSWORD    = jsondecode(data.aws_secretsmanager_secret_version.db.secret_string)["password"]
      DB_NULL_POOL   = "true"
      REPORTS_BUCKET = aws_s3_bucket.reports.bucket
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.report_builder.name
  }

  tags = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_lambda_event_source_mapping" "report_queue" {
  event_source_arn = aws_sqs_queue.report_requests.arn
  function_name    = aws_lambda_function.report_builder.arn
  batch_size       = 1
  enabled          = true
}

# =====================================================================
# Mailer Lambda (runs outside VPC, sends email via SES)
# =====================================================================

resource "aws_cloudwatch_log_group" "report_mailer" {
  name              = "/aws/lambda/${var.project_name}-report-mailer"
  retention_in_days = 7

  tags = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_iam_role" "report_mailer" {
  name = "meetings-reports-ReportMailerRole-4jHGz6Dnh0an"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_iam_role_policy_attachment" "report_mailer_basic" {
  role       = aws_iam_role.report_mailer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "report_mailer" {
  name = "MailerPermissions"
  role = aws_iam_role.report_mailer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.reports.arn}/reports/*"
      },
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "*"
      }
    ]
  })
}

data "archive_file" "report_mailer" {
  type        = "zip"
  output_path = "${path.module}/report_mailer.zip"

  source {
    content  = <<-PY
import email.message
import logging
import os
import urllib.parse
from typing import Any
import boto3

logger = logging.getLogger("report-mailer")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger.setLevel(logging.INFO)

def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    records = event.get("Records", [])
    if not records:
        logger.warning("No records found in event")
        return {"status": "no_records"}

    s3_info = records[0].get("s3", {})
    bucket = s3_info.get("bucket", {}).get("name")
    raw_key = s3_info.get("object", {}).get("key", "")
    key = urllib.parse.unquote_plus(raw_key)

    logger.info(
        "report-mailer triggered [trigger=s3, bucket=%s, key=%s]",
        bucket, key,
        extra={"trigger": "s3", "bucket": bucket, "key": key}
    )

    if not bucket or not key or not key.startswith("reports/") or not key.endswith(".csv"):
        logger.info("Skipping non-report key: %s", key)
        return {"status": "skipped", "key": key}

    sender = os.environ.get("REPORTS_FROM_EMAIL")
    recipient = os.environ.get("REPORTS_TO_EMAIL")
    if not sender or not recipient:
        raise ValueError("REPORTS_FROM_EMAIL and REPORTS_TO_EMAIL must be set")

    s3 = boto3.client("s3")
    logger.info("Downloading s3://%s/%s...", bucket, key)
    response = s3.get_object(Bucket=bucket, Key=key)
    csv_bytes = response["Body"].read()

    filename = key.split("/")[-1]
    week = filename.removesuffix(".csv")

    msg = email.message.EmailMessage()
    msg["Subject"] = f"Weekly Meetings Report — {week}"
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(
        f"Hello,\n\nPlease find attached the weekly meetings report for {week}.\n\n"
        f"Generated automatically by the Meetings Scheduler Event-Driven Reporting System.\n"
    )
    msg.add_attachment(csv_bytes, maintype="text", subtype="csv", filename=filename)

    ses = boto3.client("sesv2")
    logger.info("Sending report email to %s...", recipient)
    res = ses.send_email(
        FromEmailAddress=sender,
        Destination={"ToAddresses": [recipient]},
        Content={"Raw": {"Data": msg.as_bytes()}}
    )
    logger.info("Email sent successfully! MessageId: %s", res.get("MessageId"))
    return {"status": "success", "trigger": "s3", "key": key, "message_id": res.get("MessageId")}
PY
    filename = "index.py"
  }
}

resource "aws_lambda_function" "report_mailer" {
  function_name    = "${var.project_name}-report-mailer"
  runtime          = "python3.12"
  handler          = "index.handler"
  role             = aws_iam_role.report_mailer.arn
  timeout          = 30
  memory_size      = 256
  filename         = data.archive_file.report_mailer.output_path
  source_code_hash = data.archive_file.report_mailer.output_base64sha256

  environment {
    variables = {
      REPORTS_FROM_EMAIL = var.reports_from_email
      REPORTS_TO_EMAIL   = var.reports_to_email
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.report_mailer.name
  }

  tags = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_lambda_permission" "report_mailer_s3" {
  statement_id   = "meetings-reports-ReportMailerPermission-wuvHNM5HwI7t"
  function_name  = aws_lambda_function.report_mailer.function_name
  action         = "lambda:InvokeFunction"
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.reports.arn
  source_account = data.aws_caller_identity.current.account_id
}

resource "aws_s3_bucket_notification" "reports" {
  bucket = aws_s3_bucket.reports.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.report_mailer.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "reports/"
    filter_suffix       = ".csv"
  }

  queue {
    queue_arn     = aws_sqs_queue.report_requests.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "requests/"
    filter_suffix = ".json"
  }

  depends_on = [
    aws_lambda_permission.report_mailer_s3,
    aws_sqs_queue_policy.report_requests
  ]
}

