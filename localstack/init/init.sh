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
# BUILD LAMBDA C
# =======================
echo "Packaging lambda_c..."

BUILD_C="/tmp/build_lambda_c"
rm -rf $BUILD_C
mkdir -p $BUILD_C/services/lambda_c

echo "Installing dependencies for lambda_c..."
pip install -r /var/task/services/lambda_c/requirements.txt -t $BUILD_C/

cp -r /var/task/common $BUILD_C/
cp /var/task/services/__init__.py $BUILD_C/services/
cp -r /var/task/services/lambda_c/. $BUILD_C/services/lambda_c/

touch $BUILD_C/services/__init__.py
touch $BUILD_C/services/lambda_c/__init__.py

cd $BUILD_C
zip -r /tmp/lambda_c.zip .

echo "Creating lambda_c..."
awslocal lambda create-function \
  --function-name lambda_c \
  --runtime python3.10 \
  --handler services.lambda_c.handler.handler \
  --zip-file fileb:///tmp/lambda_c.zip \
  --role arn:aws:iam::000000000000:role/lambda-role \
  --environment "Variables={PYTHONPATH=.}"

# =======================
# SQS → Lambda mapping
# =======================
echo "Linking SQS → lambda_b..."

# QUEUE_URL="http://localhost:4566/000000000000/my_queue"

# QUEUE_ARN=$(awslocal sqs get-queue-attributes \
#   --queue-url "$QUEUE_URL" \
#   --attribute-names QueueArn \
#   --query 'Attributes.QueueArn' \
#   --output text)

# if [ -z "$QUEUE_ARN" ]; then
#   echo "ERROR: Cannot get QueueArn"
#   exit 1
# fi

# awslocal lambda create-event-source-mapping \
#   --function-name lambda_b \
#   --batch-size 5 \
#   --maximum-retry-attempts 10 \
#   --event-source-arn "$QUEUE_ARN"

# =======================
# SNS SETUP
# =======================
echo "Creating SNS Topic..."
TOPIC_ARN=$(awslocal sns create-topic --name my_topic --query 'TopicArn' --output text)

# Register Lambda B to SNS
awslocal sns subscribe \
    --topic-arn "$TOPIC_ARN" \
    --protocol lambda \
    --notification-endpoint arn:aws:lambda:us-east-1:000000000000:function:lambda_b

# Register Lambda C to SNS
awslocal sns subscribe \
    --topic-arn "$TOPIC_ARN" \
    --protocol lambda \
    --notification-endpoint arn:aws:lambda:us-east-1:000000000000:function:lambda_c

# Grant SNS permission to invoke Lambda B and Lambda C
awslocal lambda add-permission --function-name lambda_b --statement-id sns-tab --action lambda:InvokeFunction --principal sns.amazonaws.com
awslocal lambda add-permission --function-name lambda_c --statement-id sns-tab --action lambda:InvokeFunction --principal sns.amazonaws.com
awslocal logs create-log-group --log-group-name /aws/lambda/lambda_c || true
awslocal logs create-log-group --log-group-name /aws/lambda/lambda_b || true

echo "===== INIT DONE SUCCESSFULLY ====="