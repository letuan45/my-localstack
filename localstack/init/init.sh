#!/bin/bash
set -e

echo "===== START LOCALSTACK INIT ====="

echo "Listing mounted directory:"
ls -R /var/task || true

echo "Creating SQS queue..."
awslocal sqs create-queue --queue-name my_queue

# =======================
# LAMBDA A
# =======================
echo "Packaging lambda_a..."

LAMBDA_A_SRC="/var/task/services/lambda_a/handler.py"
LAMBDA_A_ZIP="/tmp/lambda_a.zip"

if [ ! -f "$LAMBDA_A_SRC" ]; then
  echo "ERROR: lambda_a handler not found at $LAMBDA_A_SRC"
  exit 1
fi

zip -j "$LAMBDA_A_ZIP" "$LAMBDA_A_SRC"

echo "Creating lambda_a..."
awslocal lambda create-function \
  --function-name lambda_a \
  --runtime python3.10 \
  --handler handler.handler \
  --zip-file fileb://"$LAMBDA_A_ZIP" \
  --role arn:aws:iam::000000000000:role/lambda-role

# =======================
# LAMBDA B
# =======================
echo "Packaging lambda_b..."

LAMBDA_B_SRC="/var/task/services/lambda_b/handler.py"
LAMBDA_B_ZIP="/tmp/lambda_b.zip"

if [ ! -f "$LAMBDA_B_SRC" ]; then
  echo "ERROR: lambda_b handler not found at $LAMBDA_B_SRC"
  exit 1
fi

zip -j "$LAMBDA_B_ZIP" "$LAMBDA_B_SRC"

echo "Creating lambda_b..."
awslocal lambda create-function \
  --function-name lambda_b \
  --runtime python3.10 \
  --handler handler.handler \
  --zip-file fileb://"$LAMBDA_B_ZIP" \
  --role arn:aws:iam::000000000000:role/lambda-role

# =======================
# SQS → Lambda mapping
# =======================
echo "Linking SQS → lambda_b..."

QUEUE_URL="http://localhost:4566/000000000000/my_queue"

QUEUE_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url "$QUEUE_URL" \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' \
  --output text)

if [ -z "$QUEUE_ARN" ]; then
  echo "ERROR: Cannot get QueueArn"
  exit 1
fi

awslocal lambda create-event-source-mapping \
  --function-name lambda_b \
  --batch-size 1 \
  --event-source-arn "$QUEUE_ARN"

echo "===== INIT DONE SUCCESSFULLY ====="