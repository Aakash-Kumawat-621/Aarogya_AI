# ─────────────────────────────────────────────────────────────────────────────
# deploy.ps1 — Full Aarogya AI deployment to AWS Lambda
#
# Run from the PROJECT ROOT:
#   .\backend\scripts\deploy.ps1
#
# Prerequisites:
#   - AWS CLI configured (aws configure)
#   - Docker Desktop running
#   - venv activated is NOT required (this script uses AWS CLI + Docker only)
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

# ── Config ────────────────────────────────────────────────────────────────────
$AWS_ACCOUNT    = "248825820417"
$AWS_REGION     = "us-east-1"
$ECR_URI        = "$AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/aarogya-backend"
$LAMBDA_NAME    = "aarogya-api"
$LAMBDA_ROLE    = "aarogya-lambda-role"
$POLICY_NAME    = "aarogya-lambda-policy"
$GATEWAY_NAME   = "aarogya-gateway"
$BACKEND_DIR    = "$PSScriptRoot\..\"   # backend/ folder

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Aarogya AI -- AWS Lambda Deployment" -ForegroundColor Cyan
Write-Host "  Account : $AWS_ACCOUNT" -ForegroundColor Cyan
Write-Host "  Region  : $AWS_REGION" -ForegroundColor Cyan
Write-Host "  ECR     : $ECR_URI" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — IAM Role + Policy
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "`n[1/6] Setting up IAM role: $LAMBDA_ROLE ..." -ForegroundColor Yellow

$trustPolicy = @"
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "lambda.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
"@

$trustFile = [System.IO.Path]::GetTempFileName() + ".json"
$trustPolicy | Out-File -FilePath $trustFile -Encoding utf8

# Create role (skip if exists)
$roleExists = aws iam get-role --role-name $LAMBDA_ROLE 2>$null
if (-not $roleExists) {
    aws iam create-role `
        --role-name $LAMBDA_ROLE `
        --assume-role-policy-document file://$trustFile | Out-Null
    Write-Host "  [OK] IAM role created: $LAMBDA_ROLE"
} else {
    Write-Host "  [SKIP] IAM role already exists."
}

# Attach managed policies
aws iam attach-role-policy `
    --role-name $LAMBDA_ROLE `
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" 2>$null

# Create inline policy for our AWS services
$inlinePolicy = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": ["s3:GetObject","s3:PutObject","s3:DeleteObject"],
      "Resource": "arn:aws:s3:::aarogya-uploads/*"
    },
    {
      "Sid": "DynamoDBAccess",
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem","dynamodb:PutItem","dynamodb:UpdateItem","dynamodb:Query","dynamodb:DeleteItem"],
      "Resource": [
        "arn:aws:dynamodb:$AWS_REGION:$AWS_ACCOUNT:table/aarogya-sessions",
        "arn:aws:dynamodb:$AWS_REGION:$AWS_ACCOUNT:table/aarogya-profiles"
      ]
    },
    {
      "Sid": "BedrockAccess",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream"],
      "Resource": "*"
    },
    {
      "Sid": "TextractAccess",
      "Effect": "Allow",
      "Action": ["textract:AnalyzeDocument","textract:DetectDocumentText"],
      "Resource": "*"
    },
    {
      "Sid": "LogsAccess",
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents"],
      "Resource": "*"
    }
  ]
}
"@

$policyFile = [System.IO.Path]::GetTempFileName() + ".json"
$inlinePolicy | Out-File -FilePath $policyFile -Encoding utf8

aws iam put-role-policy `
    --role-name $LAMBDA_ROLE `
    --policy-name $POLICY_NAME `
    --policy-document file://$policyFile | Out-Null

Write-Host "  [OK] IAM policy attached."

# Wait for role to propagate
Write-Host "  [WAIT] Waiting 10s for IAM role to propagate..."
Start-Sleep -Seconds 10


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — ECR Login
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "`n[2/6] Logging in to ECR ..." -ForegroundColor Yellow
aws ecr get-login-password --region $AWS_REGION | `
    docker login --username AWS --password-stdin "$AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com"
Write-Host "  [OK] Logged in to ECR."


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Build Docker image
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "`n[3/6] Building Docker image (linux/amd64) ..." -ForegroundColor Yellow
docker build --platform linux/amd64 -t aarogya-backend $BACKEND_DIR
Write-Host "  [OK] Docker image built."


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Tag and Push to ECR
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "`n[4/6] Pushing image to ECR ..." -ForegroundColor Yellow
docker tag aarogya-backend:latest "${ECR_URI}:latest"
docker push "${ECR_URI}:latest"
Write-Host "  [OK] Image pushed: ${ECR_URI}:latest"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Create or Update Lambda Function
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "`n[5/6] Deploying Lambda function: $LAMBDA_NAME ..." -ForegroundColor Yellow

$ROLE_ARN = "arn:aws:iam::${AWS_ACCOUNT}:role/$LAMBDA_ROLE"

# Load env vars from .env file to pass to Lambda
$envVars = @{}
Get-Content "$BACKEND_DIR\.env" | ForEach-Object {
    if ($_ -match "^([^#][^=]+)=(.*)$") {
        $envVars[$matches[1].Trim()] = $matches[2].Trim()
    }
}
$envJson = ($envVars.GetEnumerator() | ForEach-Object { "`"$($_.Key)`":`"$($_.Value)`"" }) -join ","
$envJson = "{`"Variables`":{$envJson}}"

$lambdaExists = aws lambda get-function --function-name $LAMBDA_NAME 2>$null
if (-not $lambdaExists) {
    aws lambda create-function `
        --function-name $LAMBDA_NAME `
        --package-type Image `
        --code ImageUri="${ECR_URI}:latest" `
        --role $ROLE_ARN `
        --memory-size 1024 `
        --timeout 30 `
        --architecture x86_64 `
        --environment $envJson | Out-Null
    Write-Host "  [WAIT] Waiting for Lambda to become active..."
    aws lambda wait function-active --function-name $LAMBDA_NAME
    Write-Host "  [OK] Lambda function created."
} else {
    aws lambda update-function-code `
        --function-name $LAMBDA_NAME `
        --image-uri "${ECR_URI}:latest" | Out-Null
    Write-Host "  [WAIT] Waiting for update to complete..."
    aws lambda wait function-updated --function-name $LAMBDA_NAME
    aws lambda update-function-configuration `
        --function-name $LAMBDA_NAME `
        --environment $envJson | Out-Null
    Write-Host "  [OK] Lambda function updated."
}


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — Create API Gateway (HTTP API)
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "`n[6/6] Setting up API Gateway ..." -ForegroundColor Yellow

$LAMBDA_ARN = "arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT}:function:$LAMBDA_NAME"

# Check if API already exists
$existingApis = aws apigatewayv2 get-apis --region $AWS_REGION | ConvertFrom-Json
$api = $existingApis.Items | Where-Object { $_.Name -eq $GATEWAY_NAME }

if (-not $api) {
    # Create HTTP API
    $apiResult = aws apigatewayv2 create-api `
        --name $GATEWAY_NAME `
        --protocol-type HTTP `
        --region $AWS_REGION | ConvertFrom-Json

    $API_ID = $apiResult.ApiId

    # Create Lambda integration
    $integResult = aws apigatewayv2 create-integration `
        --api-id $API_ID `
        --integration-type AWS_PROXY `
        --integration-uri $LAMBDA_ARN `
        --payload-format-version "2.0" `
        --region $AWS_REGION | ConvertFrom-Json

    $INTEG_ID = $integResult.IntegrationId

    # Create catch-all route
    aws apigatewayv2 create-route `
        --api-id $API_ID `
        --route-key "ANY /{proxy+}" `
        --target "integrations/$INTEG_ID" `
        --region $AWS_REGION | Out-Null

    # Auto-deploy stage
    aws apigatewayv2 create-stage `
        --api-id $API_ID `
        --stage-name '$default' `
        --auto-deploy `
        --region $AWS_REGION | Out-Null

    # Give API Gateway permission to invoke Lambda
    aws lambda add-permission `
        --function-name $LAMBDA_NAME `
        --statement-id apigateway-invoke `
        --action lambda:InvokeFunction `
        --principal apigateway.amazonaws.com `
        --source-arn "arn:aws:execute-api:${AWS_REGION}:${AWS_ACCOUNT}:${API_ID}/*" | Out-Null

    Write-Host "  [OK] API Gateway created."
} else {
    $API_ID = $api.ApiId
    Write-Host "  [SKIP] API Gateway already exists."
}

$API_URL = "https://${API_ID}.execute-api.${AWS_REGION}.amazonaws.com"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  API Gateway URL : $API_URL" -ForegroundColor Green
Write-Host "  Health check    : $API_URL/api/v1/health" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Save this URL as VITE_API_BASE_URL in Lovable." -ForegroundColor Cyan
Write-Host ""
