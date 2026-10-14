#!/usr/bin/env bash
set -euo pipefail

# Build and push the backend Lambda container image using AWS CodeBuild.
# Does not require Docker installed locally.

PROJECT="${PROJECT:-meetings}"
ARCH="${ARCH:-arm64}"
TAG="${TAG:-latest}"
AWS_REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="${PROJECT}-codebuild"

echo "==> Deploying/Verifying CodeBuild stack: ${STACK_NAME}"
aws cloudformation deploy \
  --stack-name "${STACK_NAME}" \
  --template-file infra/codebuild.yaml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides ProjectName="${PROJECT}" Architecture="${ARCH}" \
  --tags PROJECT_NAME="${PROJECT}" \
  --no-fail-on-empty-changeset

BUCKET=$(aws cloudformation describe-stacks --stack-name "${STACK_NAME}" \
  --query "Stacks[0].Outputs[?OutputKey=='SourceBucket'].OutputValue" --output text)

echo "==> Source bucket: ${BUCKET}"

TMP_ZIP=$(mktemp -t backend-src-XXXXXX.zip)
rm -f "${TMP_ZIP}"
trap 'rm -f "${TMP_ZIP}"' EXIT

echo "==> Packaging back/ into ${TMP_ZIP}"
(
  cd back
  zip -q -r "${TMP_ZIP}" . -x "**/__pycache__/*" -x "**/.pytest_cache/*" -x "**/.ruff_cache/*"
)

echo "==> Uploading source zip to s3://${BUCKET}/${PROJECT}-source.zip"
aws s3 cp "${TMP_ZIP}" "s3://${BUCKET}/${PROJECT}-source.zip" --quiet

echo "==> Starting AWS CodeBuild build for tag: ${TAG}"
BUILD_ID=$(aws codebuild start-build \
  --project-name "${PROJECT}-backend-builder" \
  --environment-variables-override name=IMAGE_TAG,value="${TAG}",type=PLAINTEXT \
  --query "build.id" --output text)

echo "==> Build started: ${BUILD_ID}"
echo "==> Waiting for CodeBuild to complete..."

while true; do
  STATUS=$(aws codebuild batch-get-builds --ids "${BUILD_ID}" \
    --query "builds[0].buildStatus" --output text)
  PHASE=$(aws codebuild batch-get-builds --ids "${BUILD_ID}" \
    --query "builds[0].currentPhase" --output text)

  echo "    Current phase: ${PHASE}, Status: ${STATUS}"

  if [ "${STATUS}" = "SUCCEEDED" ]; then
    echo "==> CodeBuild SUCCEEDED! Image pushed to ECR with tag: ${TAG}"
    break
  elif [ "${STATUS}" = "FAILED" ] || [ "${STATUS}" = "FAULT" ] || [ "${STATUS}" = "STOPPED" ] || [ "${STATUS}" = "TIMED_OUT" ]; then
    echo "==> CodeBuild ${STATUS}!"
    echo "Logs:"
    LOG_GROUP=$(aws codebuild batch-get-builds --ids "${BUILD_ID}" \
      --query "builds[0].logs.groupName" --output text)
    LOG_STREAM=$(aws codebuild batch-get-builds --ids "${BUILD_ID}" \
      --query "builds[0].logs.streamName" --output text)
    if [ -n "${LOG_GROUP}" ] && [ -n "${LOG_STREAM}" ] && [ "${LOG_GROUP}" != "None" ]; then
      aws logs get-log-events --log-group-name "${LOG_GROUP}" --log-stream-name "${LOG_STREAM}" \
        --query "events[].message" --output text | tail -n 40
    fi
    exit 1
  fi
  sleep 10
done
