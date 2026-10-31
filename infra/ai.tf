resource "aws_iam_role" "agenda_parser" {
  name = "${var.project_name}-agenda-parser-role"

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

resource "aws_iam_role_policy_attachment" "agenda_parser_basic" {
  role       = aws_iam_role.agenda_parser.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "agenda_parser_bedrock" {
  name = "BedrockAccess"
  role = aws_iam_role.agenda_parser.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "bedrock-mantle:CreateInference",
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ]
      Resource = "*"
    }]
  })
}

resource "aws_lambda_function" "agenda_parser" {
  function_name = "${var.project_name}-agenda-parser"
  package_type  = "Image"
  image_uri     = "${local.ecr_repository_uri}:${var.parser_image_tag}"

  image_config {
    command = ["app.ai.agenda_lambda.handler"]
  }

  architectures = [var.architecture]
  memory_size   = 512
  timeout       = 30
  role          = aws_iam_role.agenda_parser.arn

  environment {
    variables = {
      PARSER_MODEL         = var.parser_model
      COGNITO_USER_POOL_ID = aws_cognito_user_pool.main.id
      COGNITO_CLIENT_ID    = aws_cognito_user_pool_client.main.id
      COGNITO_REGION       = var.region
    }
  }

  tags = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_lambda_function_url" "agenda_parser" {
  function_name      = aws_lambda_function.agenda_parser.function_name
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "agenda_parser_url" {
  statement_id           = "meetings-ai-AgendaParserFunctionUrlPermission-ljKGFgu1hYEZ"
  function_name          = aws_lambda_function.agenda_parser.function_name
  action                 = "lambda:InvokeFunctionUrl"
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "agenda_parser_invoke" {
  statement_id             = "meetings-ai-AgendaParserFunctionInvokePermission-QbtAMZLWFdz5"
  function_name            = aws_lambda_function.agenda_parser.function_name
  action                   = "lambda:InvokeFunction"
  principal                = "*"
  invoked_via_function_url = true
}
