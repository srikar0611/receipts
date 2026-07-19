# Host the Receipts demo on AWS

This is an optional public showcase for the curated files in `docs/`. It does **not** upload a user's `.receipts/` directory, raw agent transcripts, source code, or an API key. Receipts itself remains offline-first.

The deployed path is:

```text
GitHub push → short-lived GitHub OIDC token → scoped AWS role
           → private S3 bucket → CloudFront HTTPS URL
```

The S3 bucket is private. CloudFront is its only permitted reader; there is no public S3 website endpoint and no always-on server.

## 1. Put cost guardrails in place first

In **AWS Console → Billing and Cost Management → Budgets**, create a monthly cost budget for this account:

- budget amount: `$5`;
- email alerts: `50%`, `80%`, and `100%` actual cost, plus `100%` forecast cost;
- set the budget end date to the end of the hackathon unless you intend to keep the demo online.

AWS Budgets is an alerting tool, not an instant billing kill-switch: cost data refreshes at least daily. Also check **Billing → Credits** for the credit's expiry and eligible services before you deploy.

Do not provision EC2, RDS, NAT Gateway, ECS, or Bedrock for this demo.

## 2. Publish this repository to GitHub

The workflow uses GitHub Actions OIDC, so it needs a GitHub repository before AWS can trust it. Create an empty GitHub repository, then push this local repository to it. Keep the default branch as `master`, or update both `.github/workflows/deploy-demo.yml` and the OIDC subject below to your chosen branch.

## 3. Calculate the exact OIDC subject

The OIDC subject is a security boundary: only that repository and branch can assume the AWS deployment role. Do not replace it with `*`.

For a repository created on or after 15 July 2026, GitHub's default subject includes immutable owner and repository IDs:

```text
repo:OWNER@OWNER_ID/REPOSITORY@REPOSITORY_ID:ref:refs/heads/master
```

For an older repository that still uses the legacy format, it is:

```text
repo:OWNER/REPOSITORY:ref:refs/heads/master
```

For a newly created public repository, this standard-library command prints the current immutable-format value. Replace the three values before running it:

```bash
python3 - <<'PY'
import json
from urllib.request import urlopen

owner = "OWNER"
repository = "REPOSITORY"
branch = "master"
with urlopen(f"https://api.github.com/repos/{owner}/{repository}") as response:
    repo = json.load(response)
print(f"repo:{repo['owner']['login']}@{repo['owner']['id']}/{repo['name']}@{repo['id']}:ref:refs/heads/{branch}")
PY
```

If the repository is older, use the legacy format only when GitHub's OIDC configuration says it is still in use. Do not add a GitHub Actions `environment:` to this workflow without changing the subject: environment deployments use a different OIDC subject format.

## 4. Create the AWS stack

Install and authenticate the [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html), then run this from the repository root. `ap-south-1` is only an example; choose the region you want to use for the S3/IAM stack. CloudFront itself is global.

```bash
aws cloudformation validate-template \
  --template-body file://infra/aws/receipts-demo.template.json \
  --region ap-south-1

aws cloudformation deploy \
  --stack-name receipts-demo \
  --template-file infra/aws/receipts-demo.template.json \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    GitHubOidcSubject='repo:OWNER@OWNER_ID/REPOSITORY@REPOSITORY_ID:ref:refs/heads/master' \
    CloudFrontPriceClass=PriceClass_200 \
  --region ap-south-1
```

If this AWS account already has an IAM provider for `https://token.actions.githubusercontent.com`, supply its ARN as `ExistingGitHubOidcProviderArn=...`; otherwise the stack creates it. Do not create a duplicate provider.

Read the stack outputs:

```bash
aws cloudformation describe-stacks \
  --stack-name receipts-demo \
  --query 'Stacks[0].Outputs' \
  --output table \
  --region ap-south-1
```

`DemoUrl` is the public HTTPS link. It uses CloudFront's default `*.cloudfront.net` certificate; a custom domain is intentionally deferred until after the hackathon.

## 5. Configure four GitHub repository variables

In **GitHub repository → Settings → Secrets and variables → Actions → Variables**, add the values from the stack outputs:

| Variable | Stack output / value |
|---|---|
| `AWS_REGION` | `ap-south-1` (or the region you chose) |
| `AWS_ROLE_TO_ASSUME` | `GitHubDeployRoleArn` |
| `AWS_DEMO_BUCKET` | `DemoBucketName` |
| `AWS_CLOUDFRONT_DISTRIBUTION_ID` | `CloudFrontDistributionId` |

These are identifiers, not secrets. The workflow never stores `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` in GitHub.

## 6. Deploy and verify

Push the M6 commit to `master`, or open **Actions → Deploy Receipts demo to AWS → Run workflow**. The workflow uploads only `docs/`, then creates a CloudFront invalidation so judges do not see stale content.

After the distribution finishes deploying, verify both the public demo and the private origin:

```bash
curl -I 'https://YOUR_CLOUDFRONT_DOMAIN/'
curl -fsS 'https://YOUR_CLOUDFRONT_DOMAIN/replay.html' | grep -q 'Receipts'

aws s3api get-bucket-policy-status \
  --bucket 'YOUR_DEMO_BUCKET' \
  --query 'PolicyStatus.IsPublic' \
  --output text \
  --region ap-south-1
```

The final command must print `False`.

## Cleanup

Keep the demo only while you need it. CloudFormation cannot delete a non-empty S3 bucket. After verifying the exact bucket name from the stack output, these commands permanently delete the hosted static files and then remove the stack:

```bash
aws s3 rm 's3://YOUR_DEMO_BUCKET' --recursive --region ap-south-1
aws cloudformation delete-stack --stack-name receipts-demo --region ap-south-1
aws cloudformation wait stack-delete-complete --stack-name receipts-demo --region ap-south-1
```

## Why this architecture

- AWS [documents Origin Access Control](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html) as the way to keep an S3 origin private while CloudFront serves content.
- GitHub [documents OIDC for AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws) so the workflow can receive short-lived credentials instead of storing long-lived keys.
- The default CloudFront domain gives HTTPS without buying a domain or introducing certificate-management work.
