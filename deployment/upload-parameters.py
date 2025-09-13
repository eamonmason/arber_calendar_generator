#!/usr/bin/env python3
"""
Upload local credentials to AWS Systems Manager Parameter Store for Lambda function.

This script reads your local Google OAuth credentials and token files,
then uploads them to AWS Parameter Store with KMS encryption for the Lambda function to use.
"""

import json
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError


def read_json_file(file_path: Path) -> dict:
    """Read and parse a JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ File not found: {file_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in {file_path}: {e}")
        return None


def update_parameter(ssm_client, parameter_name: str, parameter_value: str, kms_key_id: str, description: str, is_json: bool = False) -> bool:
    """Update a parameter in AWS Systems Manager Parameter Store."""
    try:
        ssm_client.put_parameter(
            Name=parameter_name,
            Value=parameter_value,
            Type='SecureString',
            KeyId=kms_key_id,
            Description=description,
            Overwrite=True
        )
        param_type = "JSON parameter" if is_json else "parameter"
        print(f"✅ {description} {param_type} updated successfully")
        return True
    except ClientError as e:
        print(f"❌ Failed to update {description}: {e}")
        return False


def main():
    """Main function to upload parameters to AWS Parameter Store."""
    if len(sys.argv) != 2:
        print("Usage: python upload-parameters.py <stack-name>")
        print("Example: python upload-parameters.py arbor-calendar-sync")
        sys.exit(1)

    stack_name = sys.argv[1]

    # Initialize AWS clients
    try:
        cloudformation = boto3.client('cloudformation')
        ssm_client = boto3.client('ssm')
    except NoCredentialsError:
        print("❌ AWS credentials not configured. Run 'aws configure' first.")
        sys.exit(1)

    # Get stack outputs to find parameter names and KMS key
    try:
        response = cloudformation.describe_stacks(StackName=stack_name)
        if not response['Stacks']:
            print(f"❌ Stack '{stack_name}' not found")
            sys.exit(1)

        outputs = {output['OutputKey']: output['OutputValue']
                  for output in response['Stacks'][0].get('Outputs', [])}

    except ClientError as e:
        print(f"❌ Failed to describe stack '{stack_name}': {e}")
        sys.exit(1)

    # Required parameter names and KMS key
    required_outputs = [
        'GoogleCredentialsParameter',
        'GoogleTokenParameter',
        'ArborUsernameParameter',
        'ArborPasswordParameter',
        'KMSKeyId'
    ]

    missing_outputs = [output for output in required_outputs if output not in outputs]
    if missing_outputs:
        print(f"❌ Missing stack outputs: {missing_outputs}")
        print("Make sure the stack deployed successfully with the latest template.")
        sys.exit(1)

    print(f"📦 Found stack '{stack_name}' with required parameters")

    kms_key_id = outputs['KMSKeyId']
    print(f"🔑 Using KMS key: {kms_key_id}")

    # Path configurations - check common locations
    config_dir = Path.home() / '.config' / 'arbor-calendar-sync'
    local_paths = {
        'credentials': [
            config_dir / 'credentials.json',
            Path('./credentials.json'),
            Path('./client_secret.json'),
            Path('./client_secrets.json')
        ],
        'token': [
            config_dir / 'token.json',
            Path('./token.json')
        ]
    }

    # Find credential files
    credentials_path = None
    for path in local_paths['credentials']:
        if path.exists():
            credentials_path = path
            break

    token_path = None
    for path in local_paths['token']:
        if path.exists():
            token_path = path
            break

    if not credentials_path:
        print("❌ Google credentials file not found in these locations:")
        for path in local_paths['credentials']:
            print(f"   {path}")
        print("\nPlease ensure you have run 'python setup_google_auth.py' first")
        sys.exit(1)

    if not token_path:
        print("❌ Google token file not found in these locations:")
        for path in local_paths['token']:
            print(f"   {path}")
        print("\nPlease ensure you have completed Google OAuth setup first")
        sys.exit(1)

    # Read credential files
    print(f"📖 Reading credentials from {credentials_path}")
    credentials_data = read_json_file(credentials_path)
    if not credentials_data:
        sys.exit(1)

    print(f"📖 Reading token from {token_path}")
    token_data = read_json_file(token_path)
    if not token_data:
        sys.exit(1)

    # Get Arbor credentials from user
    print("\n🔐 Enter Arbor credentials:")
    arbor_username = input("Arbor username: ").strip()
    arbor_password = input("Arbor password: ").strip()

    if not arbor_username or not arbor_password:
        print("❌ Both username and password are required")
        sys.exit(1)

    # Upload parameters to AWS Parameter Store
    print("\n🚀 Uploading parameters to AWS Parameter Store with KMS encryption...")

    success = True

    success &= update_parameter(
        ssm_client,
        outputs['GoogleCredentialsParameter'],
        json.dumps(credentials_data, indent=2),
        kms_key_id,
        "Google credentials",
        is_json=True
    )

    success &= update_parameter(
        ssm_client,
        outputs['GoogleTokenParameter'],
        json.dumps(token_data, indent=2),
        kms_key_id,
        "Google token",
        is_json=True
    )

    success &= update_parameter(
        ssm_client,
        outputs['ArborUsernameParameter'],
        arbor_username,
        kms_key_id,
        "Arbor username"
    )

    success &= update_parameter(
        ssm_client,
        outputs['ArborPasswordParameter'],
        arbor_password,
        kms_key_id,
        "Arbor password"
    )

    if success:
        print("\n🎉 All parameters uploaded successfully!")
        print("Your Lambda function can now access the encrypted credentials from AWS Parameter Store.")
        print("\n⚠️  Security reminder:")
        print("- These parameters are now stored securely in AWS Parameter Store")
        print("- All sensitive parameters are encrypted with your dedicated KMS key")
        print("- Your local credential files remain on your machine")
        print("- The Lambda function will retrieve and decrypt parameters at runtime")
        print("- Monitor CloudWatch logs for any authentication issues")
        print(f"\n🔍 Parameter Store locations:")
        print(f"   Google Credentials: {outputs['GoogleCredentialsParameter']}")
        print(f"   Google Token: {outputs['GoogleTokenParameter']}")
        print(f"   Arbor Username: {outputs['ArborUsernameParameter']}")
        print(f"   Arbor Password: {outputs['ArborPasswordParameter']}")
    else:
        print("\n❌ Some parameters failed to upload. Check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()