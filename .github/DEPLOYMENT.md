# GitHub Actions Deployment Setup

This document explains how to set up automated deployment using GitHub Actions.

## Overview

The GitHub Actions workflow automatically:
1. **Tests and lints** code on every push and pull request
2. **Builds and deploys** to AWS Lambda on pushes to `main` branch
3. **Tests the deployment** with a dry-run Lambda invocation
4. **Notifies** about deployment status

## Prerequisites

### 1. AWS Setup

#### Create an IAM Role for GitHub Actions

1. Go to [AWS IAM Console](https://console.aws.amazon.com/iam/)
2. Create a new IAM role with the following trust policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_USERNAME/arbor-calendar-sync:*"
        }
      }
    }
  ]
}
```

3. Attach these policies to the role:
   - `AWSCloudFormationFullAccess`
   - `IAMFullAccess`
   - `AWSLambdaFullAccess`
   - `AmazonEventBridgeFullAccess`
   - `CloudWatchLogsFullAccess`
   - `AmazonSSMFullAccess`
   - `AmazonS3FullAccess` (required for SAM deployment S3 bucket creation)
   - `AmazonEC2ContainerRegistryFullAccess` (required for Docker image repository creation)

#### Configure OIDC Provider (if not already done)

1. In IAM Console, go to "Identity providers"
2. Click "Add provider"
3. Choose "OpenID Connect"
4. Provider URL: `https://token.actions.githubusercontent.com`
5. Audience: `sts.amazonaws.com`

### 2. Store Credentials in AWS Systems Manager

Store your credentials in AWS Parameter Store:

```bash
# Google credentials (JSON content)
aws ssm put-parameter \
  --name "/arbor-calendar-sync/google-credentials" \
  --value file://path/to/credentials.json \
  --type "SecureString"

# Google token (JSON content)
aws ssm put-parameter \
  --name "/arbor-calendar-sync/google-token" \
  --value file://path/to/token.json \
  --type "SecureString"

# Arbor username
aws ssm put-parameter \
  --name "/arbor-calendar-sync/arbor-username" \
  --value "your.username@example.com" \
  --type "SecureString"

# Arbor password
aws ssm put-parameter \
  --name "/arbor-calendar-sync/arbor-password" \
  --value "your-password" \
  --type "SecureString"
```

## GitHub Repository Setup

### 1. Repository Secrets

Go to your GitHub repository → Settings → Secrets and variables → Actions

Add the following **Repository Secrets**:

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `AWS_ROLE_ARN` | IAM role ARN for GitHub Actions | `arn:aws:iam::123456789012:role/GitHubActionsRole` |
| `GOOGLE_CREDENTIALS_PARAMETER` | Parameter Store path for Google credentials | `/arbor-calendar-sync/google-credentials` |
| `GOOGLE_TOKEN_PARAMETER` | Parameter Store path for Google token | `/arbor-calendar-sync/google-token` |
| `ARBOR_USERNAME` | Arbor username for login | `your.username@example.com` |
| `ARBOR_PASSWORD` | Arbor password for login | `your-password` |
| `GOOGLE_CALENDAR_ID` | Google Calendar ID | `abc123@group.calendar.google.com` |
| `ARBOR_BASE_URL` | Arbor system URL | `https://your-school.uk.arbor.sc` |
| `ARBOR_STUDENT_OBJECT_ID` | Student object ID | `1234` |

### 2. Repository Variables (Optional)

Add the following **Repository Variables**:

| Variable Name | Description | Default |
|---------------|-------------|---------|
| `ARBOR_TIMEZONE` | Timezone for events | `Europe/London` |

## Workflow Configuration

### Environment Variables

The workflow uses these environment variables (configurable at the top of `.github/workflows/deploy.yml`):

- `AWS_REGION`: AWS region for deployment (default: `eu-west-1`)
- `SAM_STACK_NAME`: CloudFormation stack name (default: `arbor-calendar-sync`)

### Workflow Triggers

The workflow runs on:
- **Push to main**: Runs tests + deployment
- **Pull requests**: Runs tests only
- **Manual trigger**: Available in GitHub Actions tab

## Usage

### Automatic Deployment

1. Push code to `main` branch:
   ```bash
   git push origin main
   ```

2. Monitor the deployment in GitHub Actions tab

### Manual Deployment

1. Go to GitHub repository → Actions
2. Select "Build and Deploy to AWS Lambda" workflow
3. Click "Run workflow"
4. Choose branch and click "Run workflow"

## Monitoring

### GitHub Actions Logs

- View real-time logs in GitHub Actions tab
- Each step shows detailed output
- Failed deployments will show error details

### AWS CloudWatch

- Lambda logs: `/aws/lambda/arbor-calendar-sync-ArborCalendarSyncFunction-*`
- Monitor execution and errors

### Deployment Testing

The workflow automatically tests deployments by:
1. Invoking the Lambda function with `dry_run: true`
2. Checking the response status code
3. Failing the pipeline if the test fails

## Troubleshooting

### Common Issues

1. **AWS Credentials Error**
   - Verify the IAM role ARN is correct
   - Check the trust policy includes your repository
   - Ensure OIDC provider is configured

2. **Parameter Store Access**
   - Verify parameter names match exactly
   - Check IAM role has `AmazonSSMFullAccess`
   - Ensure parameters exist in the correct region

3. **SAM Build/Deploy Failures**
   - Check CloudFormation events in AWS Console
   - Verify all required parameters are provided
   - Ensure no naming conflicts with existing resources
   - **S3 Bucket Creation Error**: Ensure IAM role has `AmazonS3FullAccess` policy attached
   - **ECR Repository Creation Error**: Ensure IAM role has `AmazonEC2ContainerRegistryFullAccess` policy attached

4. **Lambda Test Failure**
   - Check Lambda logs in CloudWatch
   - Verify environment variables are set correctly
   - Test credentials and calendar access

### Debugging Steps

1. **Check GitHub Actions logs** for detailed error messages
2. **Review CloudWatch logs** for Lambda execution errors
3. **Verify AWS resources** in CloudFormation console
4. **Test locally** with the same configuration

## Security Best Practices

1. **Use IAM roles** instead of access keys
2. **Store sensitive data** in AWS Parameter Store
3. **Limit repository access** to necessary team members
4. **Regular credential rotation** for Arbor and Google accounts
5. **Monitor CloudTrail** for AWS API usage

## Customization

### Modify Deployment Region

Update the `AWS_REGION` environment variable in the workflow file:

```yaml
env:
  AWS_REGION: eu-west-1  # Change to your preferred region
```

### Add Deployment Environments

Create separate workflows or modify the existing one to deploy to different environments (dev, staging, prod).

### Custom Notifications

Add Slack, Discord, or email notifications by adding steps to the `notify` job.