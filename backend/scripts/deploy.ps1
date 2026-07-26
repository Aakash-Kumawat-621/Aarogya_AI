# ─────────────────────────────────────────────────────────────────────────────
# deploy.ps1 — Aarogya AI full deployment to AWS Lambda
# Run from PROJECT ROOT: .\backend\scripts\deploy.ps1
# ─────────────────────────────────────────────────────────────────────────────

# Use Continue so aws CLI stderr doesn't abort the script
$ErrorActionPreference = "Continue"

# ── Config ────────────────────────────────────────────────────────────────────
$AWS_ACCOUNT  = "248825820417"
$AWS_REGION   = "us-east-1"
$ECR_REPO     = "aarogya-backend"
$ECR_URI      = "${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
$LAMBDA_NAME  = "aarogya-api"
$LAMBDA_ROLE  = "aarogya-lambda-role"
$POLICY_NAME  = "aarogya-lambda-policy"
$GATEWAY_NAME = "aarogya-gateway"
$BACKEND_DIR  = Join-Path $PSScriptRoot "..\"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Aarogya AI -- AWS Lambda Deployment" -ForegroundColor Cyan
Write-Host "  Account : $AWS_ACCOUNT  |  Region: $AWS_REGION" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — IAM Role + Policy
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "`n[1/6] IAM Role setup ..." -ForegroundColor Yellow

# Write trust policy to temp file
$trustFile = Join-Path $env:TEMP "trust_policy.json"
@"
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}
"@ | Set-Content -Path $trustFile -Encoding utf8

# Create role — ignore error if already exists
$out = aws iam create-role --role-name $LAMBDA_ROLE --assume-role-policy-document "file://$trustFile" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] IAM role created."
} else {
    Write-Host "  [SKIP] IAM role already exists."
}

# Attach basic Lambda execution policy
aws iam attach-role-policy --role-name $LAMBDA_ROLE --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" 2>&1 | Out-Null

# Write inline policy to temp file
$policyFile = Join-Path $env:TEMP "lambda_policy.json"
@"
{
  "Version": "2012-10-17",
  "Statement": [
    {"Sid":"S3","Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject"],"Resource":"arn:aws:s3:::aarogya-uploads/*"},
    {"Sid":"DDB","Effect":"Allow","Action":["dynamodb:GetItem","dynamodb:PutItem","dynamodb:UpdateItem","dynamodb:Query","dynamodb:DeleteItem"],"Resource":["arn:aws:dynamodb:${AWS_REGION}:${AWS_ACCOUNT}:table/aarogya-sessions","arn:aws:dynamodb:${AWS_REGION}:${AWS_ACCOUNT}:table/aarogya-profiles"]},
    {"Sid":"Bedrock","Effect":"Allow","Action":["bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream"],"Resource":"*"},
    {"Sid":"Textract","Effect":"Allow","Action":["textract:AnalyzeDocument","textract:DetectDocumentText"],"Resource":"*"},
    {"Sid":"Logs","Effect":"Allow","Action":["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents"],"Resource":"*"}
  ]
}
"@ | Set-Content -Path $policyFile -Encoding utf8

aws iam put-role-policy --role-name $LAMBDA_ROLE --policy-name $POLICY_NAME --policy-document "file://$policyFile" 2>&1 | Out-Null
Write-Host "  [OK] IAM policy attached."

Write-Host "  [WAIT] 20s for IAM to propagate..."
Start-Sleep -Seconds 20


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — ECR Login
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "`n[2/6] ECR Login ..." -ForegroundColor Yellow
$pwd = aws ecr get-login-password --region $AWS_REGION
$pwd | docker login --username AWS --password-stdin "${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"
if ($LASTEXITCODE -ne 0) { Write-Host "ECR login failed!" -ForegroundColor Red; exit 1 }
Write-Host "  [OK] Logged in to ECR."


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Docker Build
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "`n[3/6] Building Docker image ..." -ForegroundColor Yellow
docker buildx build --platform linux/amd64 --provenance=false --load -t $ECR_REPO $BACKEND_DIR
if ($LASTEXITCODE -ne 0) { Write-Host "Docker build failed!" -ForegroundColor Red; exit 1 }
Write-Host "  [OK] Image built."


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Push to ECR
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "`n[4/6] Pushing to ECR ..." -ForegroundColor Yellow
docker tag "${ECR_REPO}:latest" "${ECR_URI}:latest"
docker push "${ECR_URI}:latest"
if ($LASTEXITCODE -ne 0) { Write-Host "Docker push failed!" -ForegroundColor Red; exit 1 }
Write-Host "  [OK] Image pushed: ${ECR_URI}:latest"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Lambda Function
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "`n[5/6] Lambda deployment ..." -ForegroundColor Yellow

$ROLE_ARN = "arn:aws:iam::${AWS_ACCOUNT}:role/${LAMBDA_ROLE}"

# Build env vars JSON from .env file
$envVars = [ordered]@{}
$skipKeys = @("AWS_REGION", "AWS_ACCOUNT_ID", "ECR_REPO_URI", "LAMBDA_FUNCTION_NAME", "API_GATEWAY_URL", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
Get-Content (Join-Path $BACKEND_DIR ".env") | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        $val = $parts[1].Trim()
        if ($skipKeys -notcontains $key) {
            $envVars[$key] = $val
        }
    }
}
$envFile = Join-Path $env:TEMP "lambda_env.json"
$jsonStr = @{ Variables = $envVars } | ConvertTo-Json -Compress
[System.IO.File]::WriteAllText($envFile, $jsonStr, [System.Text.UTF8Encoding]::new($false))

# Try to get existing Lambda
$getResult = aws lambda get-function --function-name $LAMBDA_NAME 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Updating existing Lambda..."
    aws lambda update-function-code --function-name $LAMBDA_NAME --image-uri "${ECR_URI}:latest" | Out-Null
    aws lambda wait function-updated --function-name $LAMBDA_NAME
    aws lambda update-function-configuration --function-name $LAMBDA_NAME --environment "file://$envFile" | Out-Null
    Write-Host "  [OK] Lambda updated."
} else {
    Write-Host "  Creating new Lambda..."
    aws lambda create-function `
        --function-name $LAMBDA_NAME `
        --package-type Image `
        --code "ImageUri=${ECR_URI}:latest" `
        --role $ROLE_ARN `
        --memory-size 1024 `
        --timeout 30 `
        --architecture x86_64 `
        --environment "file://$envFile" | Out-Null
    aws lambda wait function-active --function-name $LAMBDA_NAME
    Write-Host "  [OK] Lambda created."
}


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — API Gateway HTTP API
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "`n[6/6] API Gateway setup ..." -ForegroundColor Yellow

$LAMBDA_ARN = "arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT}:function:${LAMBDA_NAME}"

# Check if gateway already exists
$apis = (aws apigatewayv2 get-apis --region $AWS_REGION | ConvertFrom-Json).Items
$existingApi = $apis | Where-Object { $_.Name -eq $GATEWAY_NAME }

if ($existingApi) {
    $API_ID = $existingApi.ApiId
    Write-Host "  [SKIP] API Gateway already exists: $API_ID"
} else {
    # Create API
    $apiResult = aws apigatewayv2 create-api --name $GATEWAY_NAME --protocol-type HTTP --region $AWS_REGION | ConvertFrom-Json
    $API_ID = $apiResult.ApiId

    # Create Lambda integration
    $integResult = aws apigatewayv2 create-integration `
        --api-id $API_ID `
        --integration-type AWS_PROXY `
        --integration-uri $LAMBDA_ARN `
        --payload-format-version "2.0" `
        --region $AWS_REGION | ConvertFrom-Json
    $INTEG_ID = $integResult.IntegrationId

    # Catch-all route
    aws apigatewayv2 create-route --api-id $API_ID --route-key "ANY /{proxy+}" --target "integrations/$INTEG_ID" --region $AWS_REGION | Out-Null

    # Auto-deploy stage
    aws apigatewayv2 create-stage --api-id $API_ID --stage-name '$default' --auto-deploy --region $AWS_REGION | Out-Null

    Write-Host "  [OK] API Gateway created: $API_ID"
}

# Ensure Lambda has permission to be invoked by API Gateway (ignore error if already added)
aws lambda add-permission `
    --function-name $LAMBDA_NAME `
    --statement-id apigateway-invoke `
    --action lambda:InvokeFunction `
    --principal apigateway.amazonaws.com `
    --source-arn "arn:aws:execute-api:${AWS_REGION}:${AWS_ACCOUNT}:${API_ID}/*" 2>&1 | Out-Null

$API_URL = "https://${API_ID}.execute-api.${AWS_REGION}.amazonaws.com"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  API URL    : $API_URL" -ForegroundColor Green
Write-Host "  Health     : $API_URL/api/v1/health" -ForegroundColor Green
Write-Host "  Save this as VITE_API_BASE_URL in Lovable!" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Green
