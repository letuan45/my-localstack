#!/bin/bash
set -e

echo "===== START LOCALSTACK INIT ====="

cd /var/task

echo "Listing mounted directory:"
ls -R /var/task || true

echo "Creating SQS queue..."
awslocal sqs create-queue --queue-name my_queue

# =======================
# COMMON SETUP
# =======================
touch common/__init__.py
touch services/__init__.py
touch services/lambda_a/__init__.py
touch services/lambda_b/__init__.py

# =======================
# BUILD LAMBDA A
# =======================
echo "Packaging lambda_a..."

BUILD_A="/tmp/build_lambda_a"
rm -rf $BUILD_A
mkdir -p $BUILD_A/services/lambda_a

echo "Installing dependencies for lambda_a..."
pip install -r /var/task/services/lambda_a/requirements.txt -t $BUILD_A/

cp -r /var/task/common $BUILD_A/
cp /var/task/services/__init__.py $BUILD_A/services/
cp -r /var/task/services/lambda_a/. $BUILD_A/services/lambda_a/ 

touch $BUILD_A/services/__init__.py
touch $BUILD_A/services/lambda_a/__init__.py

cd $BUILD_A
zip -r /tmp/lambda_a.zip .

echo "Creating lambda_a..."
awslocal lambda create-function \
  --function-name lambda_a \
  --runtime python3.10 \
  --handler services.lambda_a.handler.handler \
  --zip-file fileb:///tmp/lambda_a.zip \
  --role arn:aws:iam::000000000000:role/lambda-role \
  --environment "Variables={PYTHONPATH=.}"

cd /var/task

# =======================
# BUILD LAMBDA B
# =======================
echo "Packaging lambda_b..."

BUILD_B="/tmp/build_lambda_b"
rm -rf $BUILD_B
mkdir -p $BUILD_B/services/lambda_b

echo "Installing dependencies for lambda_b..."
pip install -r /var/task/services/lambda_b/requirements.txt -t $BUILD_B/

cp -r /var/task/common $BUILD_B/
cp /var/task/services/__init__.py $BUILD_B/services/
cp -r /var/task/services/lambda_b/. $BUILD_B/services/lambda_b/

touch $BUILD_B/services/__init__.py
touch $BUILD_B/services/lambda_b/__init__.py

cd $BUILD_B
zip -r /tmp/lambda_b.zip .

echo "Creating lambda_b..."
awslocal lambda create-function \
  --function-name lambda_b \
  --runtime python3.10 \
  --handler services.lambda_b.handler.handler \
  --zip-file fileb:///tmp/lambda_b.zip \
  --role arn:aws:iam::000000000000:role/lambda-role \
  --environment "Variables={PYTHONPATH=.}"

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
  --maximum-retry-attempts 0 \
  --event-source-arn "$QUEUE_ARN"

echo "===== INIT DONE SUCCESSFULLY ====="