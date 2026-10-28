import sys

from app.config import settings


def get_client():
    if settings.parser_model.startswith(("us.", "global.")):
        from anthropic import AnthropicBedrock

        return AnthropicBedrock(aws_region=settings.cognito_region or "us-east-1")
    try:
        from anthropic import AnthropicBedrockMantle

        return AnthropicBedrockMantle(aws_region=settings.cognito_region or "us-east-1")
    except Exception:
        from anthropic import AnthropicBedrock

        return AnthropicBedrock(aws_region=settings.cognito_region or "us-east-1")


def main():
    client = get_client()
    print(f"Calling Bedrock model: {settings.parser_model}")
    try:
        msg = client.messages.create(
            model=settings.parser_model,
            max_tokens=100,
            messages=[{"role": "user", "content": "Hello! Reply in one short sentence."}],
        )
    except Exception as exc:
        print(f"Error calling Bedrock ({type(exc).__name__}): {exc}", file=sys.stderr)
        sys.exit(1)

    answer = msg.content[0].text if msg.content else ""
    print(f"Answer: {answer}")
    print(f"stop_reason: {msg.stop_reason}")
    print(f"usage: input_tokens={msg.usage.input_tokens}, output_tokens={msg.usage.output_tokens}")


if __name__ == "__main__":
    main()
