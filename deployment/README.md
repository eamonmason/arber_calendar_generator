# AWS Lambda Deployment

This directory contains AWS deployment configuration for running Arbor Calendar Sync as a scheduled Lambda function.

## Prerequisites

1. **AWS CLI**: Install and configure with appropriate credentials
   ```bash
   aws configure
   ```

2. **AWS SAM CLI**: Install SAM CLI for deployment
   ```bash
   # macOS
   brew install aws-sam-cli

   # Or download from: https://aws.amazon.com/serverless/sam/
   ```

3. **Google Calendar API Setup**: Complete the Google authentication setup first
   ```bash
   python setup_google_auth.py client_secrets.json
   ```

4. **Local Environment Setup**: Ensure your `.env` file is configured locally for initial testing
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

## Deployment Steps

### 1. Build the Application
```bash
sam build
```

### 2. Deploy with Guided Setup (First Time)
```bash
sam deploy --guided
```

**Note**: The deployment now includes an ECR repository with a lifecycle policy that keeps only the last 5 images. When running `sam deploy --guided`, you should specify the repository URI if prompted, or ensure it matches the one defined in the template (`<stack-name>-repo`).

### 3. Upload Credentials to AWS Parameter Store
After deployment, upload your local Google OAuth credentials:

```bash
python deployment/upload-parameters.py <your-stack-name>
```

This script will:
- Find your local Google credentials and token files
- Prompt for Arbor credentials
- Upload all credentials securely to AWS Parameter Store with KMS encryption
- Configure the Lambda function to access them at runtime

### 4. Subsequent Deployments
For code updates (after initial setup):
```bash
sam deploy
```

For credential updates:
```bash
python deployment/upload-parameters.py <your-stack-name>
```

## Environment Variables

The Lambda function uses these environment variables:

| Variable | Description | Source |
|----------|-------------|---------|
| `GOOGLE_CALENDAR_ID` | Google Calendar ID | CloudFormation parameter |
| `ARBOR_BASE_URL` | School's Arbor URL | CloudFormation parameter |
| `ARBOR_STUDENT_ID` | Student ID in Arbor | CloudFormation parameter |
| `UPDATE_EXISTING_EVENTS` | Update existing events | CloudFormation parameter |
| `DELETE_ORPHANED_EVENTS` | Delete orphaned events | CloudFormation parameter |
| `ARBOR_TIMEZONE` | Timezone for events | Fixed: `Europe/London` |
| `GOOGLE_CREDENTIALS_PARAMETER` | Google credentials parameter name | Auto-generated |
| `GOOGLE_TOKEN_PARAMETER` | Google token parameter name | Auto-generated |
| `ARBOR_USERNAME_PARAMETER` | Arbor username parameter name | Auto-generated |
| `ARBOR_PASSWORD_PARAMETER` | Arbor password parameter name | Auto-generated |
| `KMS_KEY_ID` | KMS key ID for encryption | Auto-generated |

**Note**: Sensitive credentials (Google OAuth and Arbor login) are stored in AWS Systems Manager Parameter Store with KMS encryption and retrieved at runtime, not as environment variables.

## Schedule Configuration

The Lambda function runs weekly on Sundays at 8 AM UTC using this cron expression:
```
cron(0 8 ? * SUN *)
```

**Important**: Lambda execution syncs only from the current date to the end of the academic year for efficiency. This means:
- Each weekly run only processes upcoming events
- Past events are not re-processed
- Local execution still syncs the full academic year by default

To modify the schedule, edit the `Schedule` property in `template.yaml`:
```yaml
Events:
  WeeklySundaySchedule:
    Type: Schedule
    Properties:
      Schedule: 'cron(0 8 ? * SUN *)'  # Modify this line
```

## Manual Testing

Test the Lambda function manually:

```bash
# Invoke with default parameters
sam local invoke ArborCalendarSyncFunction

# Invoke with custom parameters
sam local invoke ArborCalendarSyncFunction --event events/test-event.json
```

Create `events/test-event.json` for testing:
```json
{
  "dry_run": true,
  "headless": true,
  "academic_year": 2024
}
```

## Monitoring

### CloudWatch Logs
View logs in AWS Console:
- Service: CloudWatch
- Log Groups: `/aws/lambda/arbor-calendar-sync-ArborCalendarSyncFunction-*`

### Lambda Metrics
Monitor execution in AWS Console:
- Service: Lambda
- Function: Your deployed function name
- Monitoring tab for metrics and logs

## Cleanup

To remove all AWS resources:
```bash
sam delete
```

## Cost Considerations

### Lambda Pricing
- **Free Tier**: 1M free requests and 400,000 GB-seconds per month
- **Beyond Free Tier**: ~$0.20 per 1M requests + compute time
- **Weekly Schedule**: ~52 executions per year (well within free tier)
- **Memory**: 1GB allocated for optimal performance
- **Timeout**: 15 minutes (maximum allowed) to handle large syncs

### Expected Costs
- **Typical Weekly Run**: <1 minute execution time
- **Annual Cost**: $0 (within free tier limits)
- **Data Transfer**: Minimal (API calls only)

## Troubleshooting

### Common Issues

1. **Authentication Errors**
   - Run `python deployment/upload-parameters.py <stack-name>` to refresh credentials
   - Check CloudWatch logs: `/aws/lambda/<function-name>` for specific auth errors
   - Verify Google token hasn't expired (re-run local auth setup if needed)

2. **Permission Errors**
   - Verify Lambda execution role has `ssm:GetParameter` and `kms:Decrypt` permissions
   - Check that parameters exist in the same AWS region as Lambda
   - Review CloudWatch logs for specific permission errors

3. **Credential Upload Issues**
   - Ensure local Google credentials exist in expected locations
   - Verify AWS CLI is configured and has Systems Manager and KMS permissions
   - Check stack outputs exist (deploy may have failed partially)

4. **Timeout Errors**
   - Current timeout is 15 minutes (900 seconds) - the maximum allowed for Lambda
   - If sync takes longer, consider reducing the sync window or optimizing the process
   - Monitor CloudWatch metrics for actual execution time
   - Lambda syncs only from current date to end of academic year (not full year)

5. **Parameter Access Errors**
   - Verify parameter names in environment variables match created parameters
   - Check parameters are in the same AWS region as Lambda function
   - Confirm Lambda has required IAM permissions for Systems Manager and KMS
   - Ensure KMS key policy allows Lambda role to decrypt parameters

### Debug Mode

For detailed logging, modify the Lambda function environment:
```yaml
Environment:
  Variables:
    LOG_LEVEL: DEBUG
```

### Local Testing

Test locally before deployment:
```bash
# Run locally as script (uses local .env and credential files)
python lambda_handler.py --dry-run

# Test Lambda handler locally with SAM
sam local invoke --event events/test-event.json

# Create test event file
mkdir -p events
cat > events/test-event.json << 'EOF'
{
  "dry_run": true,
  "headless": true,
  "academic_year": 2024
}
EOF
```

**Note**: Local SAM testing won't have access to AWS Parameter Store, so it will fall back to local credential files.