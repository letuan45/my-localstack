#!/bin/bash
set -e

echo "===== START LOCALSTACK INIT ====="

cd /var/task

echo "Listing mounted directory:"
ls -R /var/task || true

# =======================
# 1. SETUP LOGGING
# =======================
echo "Creating Log Groups..."
awslocal logs create-log-group --log-group-name /aws/lambda/lambda_a || true
awslocal logs create-log-group --log-group-name /aws/lambda/lambda_b || true
awslocal logs create-log-group --log-group-name /aws/lambda/lambda_c || true

# =======================
# 2. CREATE RESOURCES (SNS & SQS)
# =======================
echo "Creating SQS queue..."
QUEUE_URL=$(awslocal sqs create-queue --queue-name my_queue --query 'QueueUrl' --output text)

echo "Creating SNS Topic..."
TOPIC_ARN=$(awslocal sns create-topic --name my_topic --query 'TopicArn' --output text)

# =======================
# 3. COMMON SETUP & BUILD LAMBDAS
# =======================
touch common/__init__.py
touch services/__init__.py
touch services/lambda_a/__init__.py
touch services/lambda_b/__init__.py
touch services/lambda_c/__init__.py

build_lambda() {
    local LAMBDA_NAME=$1
    echo "Packaging $LAMBDA_NAME..."
    local BUILD_DIR="/tmp/build_$LAMBDA_NAME"

    rm -rf $BUILD_DIR
    mkdir -p $BUILD_DIR/services/$LAMBDA_NAME

    echo "Installing dependencies for $LAMBDA_NAME..."
    pip install -r /var/task/services/$LAMBDA_NAME/requirements.txt -t $BUILD_DIR/ > /dev/null 2>&1

    cp -r /var/task/common $BUILD_DIR/
    cp /var/task/services/__init__.py $BUILD_DIR/services/
    cp -r /var/task/services/$LAMBDA_NAME/. $BUILD_DIR/services/$LAMBDA_NAME/

    touch $BUILD_DIR/services/__init__.py
    touch $BUILD_DIR/services/$LAMBDA_NAME/__init__.py

    cd $BUILD_DIR
    zip -rq /tmp/$LAMBDA_NAME.zip .

    echo "Creating $LAMBDA_NAME..."
    awslocal lambda create-function \
      --function-name $LAMBDA_NAME \
      --runtime python3.10 \
      --handler services.$LAMBDA_NAME.handler.handler \
      --zip-file fileb:///tmp/$LAMBDA_NAME.zip \
      --role arn:aws:iam::000000000000:role/lambda-role \
      --environment "Variables={PYTHONPATH=.}" > /dev/null

    cd /var/task
}

build_lambda "lambda_a"
build_lambda "lambda_b"
build_lambda "lambda_c"

# =======================
# 4. WIRING IT ALL TOGETHER
# =======================

# --- A. SQS to Lambda B Mapping ---
echo "Linking SQS -> lambda_b..."
QUEUE_ARN=$(awslocal sqs get-queue-attributes \
    --queue-url "$QUEUE_URL" \
    --attribute-names QueueArn \
    --query 'Attributes.QueueArn' \
    --output text)

awslocal lambda create-event-source-mapping \
    --function-name lambda_b \
    --batch-size 5 \
    --maximum-retry-attempts 10 \
    --event-source-arn "$QUEUE_ARN" > /dev/null

# --- B. SNS to Lambda B & C Mapping ---
echo "Linking SNS -> lambda_b & lambda_c..."

# Subscribe B and C to Topic
awslocal sns subscribe \
    --topic-arn "$TOPIC_ARN" \
    --protocol lambda \
    --notification-endpoint arn:aws:lambda:us-east-1:000000000000:function:lambda_b > /dev/null

awslocal sns subscribe \
    --topic-arn "$TOPIC_ARN" \
    --protocol lambda \
    --notification-endpoint arn:aws:lambda:us-east-1:000000000000:function:lambda_c > /dev/null

# Grant SNS invoke permissions
awslocal lambda add-permission --function-name lambda_b --statement-id sns-invoke-b --action lambda:InvokeFunction --principal sns.amazonaws.com > /dev/null
awslocal lambda add-permission --function-name lambda_c --statement-id sns-invoke-c --action lambda:InvokeFunction --principal sns.amazonaws.com > /dev/null

echo "===== INIT DONE SUCCESSFULLY ====="