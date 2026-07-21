# Host the Receipts demo on AWS

This is an optional public showcase for the curated files in `docs/`. It does **not** upload a user's `.receipts/` directory, raw agent transcripts, source code, or an API key. Receipts itself remains offline-first.

M11 adds a separate, manual **live evidence feed**. It records a fresh synthetic demo session on a trusted GitHub Actions runner, verifies the private source receipt, then publishes only an alias-only public projection at `live/latest.json` plus its safe replay at `live/latest.html`. It is not a user-data SaaS or a terminal stream.

The deployed path is:

```text
GitHub push → short-lived GitHub OIDC token → site deploy role
           → private S3 bucket → CloudFront HTTPS dashboard

Manual GitHub Actions run → separate prefix-scoped OIDC role
                          → `live/latest.{json,html}` only
                          → CloudFront HTTPS live feed
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

## 5. Configure five GitHub repository variables

In **GitHub repository → Settings → Secrets and variables → Actions → Variables**, add the values from the stack outputs:

| Variable | Stack output / value |
|---|---|
| `AWS_REGION` | `ap-south-1` (or the region you chose) |
| `AWS_ROLE_TO_ASSUME` | `GitHubDeployRoleArn` |
| `AWS_LIVE_FEED_ROLE_TO_ASSUME` | `GitHubLiveFeedPublisherRoleArn` |
| `AWS_DEMO_BUCKET` | `DemoBucketName` |
| `AWS_CLOUDFRONT_DISTRIBUTION_ID` | `CloudFrontDistributionId` |

These are identifiers, not secrets. The workflow never stores `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` in GitHub.

## 6. Deploy the safe dashboard and verify

Push the M11 commit to `master`, or open **Actions → Deploy Receipts demo to AWS → Run workflow**. The workflow uploads only `docs/`, deliberately excludes `live/*`, then creates a CloudFront invalidation so judges do not see stale dashboard assets. The ordinary site role is explicitly denied `live/*`, so it cannot erase a fresh feed by accident.

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

## 7. Publish a fresh live evidence receipt

First update the existing stack with the M11 CloudFormation template and add `AWS_LIVE_FEED_ROLE_TO_ASSUME` from the new stack output. Then, from the `master` branch in GitHub, open **Actions → Publish live Receipts evidence → Run workflow**.

That workflow:

1. runs `receipts demo --live` inside an Ubuntu GitHub runner, exercising the real PTY capture path;
2. runs `receipts verify` against the resulting private manifest;
3. runs `receipts export-public`, which removes task text, paths, commands, Git metadata, transcript information, and all source-path mappings;
4. verifies the new public projection's own SHA-256; and
5. assumes the separate live-feed role and overwrites only `live/latest.json` and `live/latest.html`.

No raw source manifest or log is uploaded. The normal deploy role has an explicit deny for `live/*`; the live role has only `s3:PutObject` for the two fixed latest keys. CloudFront's `live/*` behavior uses AWS's managed **CachingDisabled** policy and the objects set `Cache-Control: no-store`, so no CloudFront invalidation is needed for a feed publication.

Verify after the action succeeds:

```bash
curl -fsS 'https://YOUR_CLOUDFRONT_DOMAIN/live/latest.json' > latest.json
receipts verify latest.json
curl -fsS 'https://YOUR_CLOUDFRONT_DOMAIN/live/latest.html' | grep -q 'Alias-only evidence projection'
```

Refresh the root CloudFront URL. The dashboard should say **LIVE PUBLISHED** and link to `/live/latest.html`. Before the first manual publication—or if a public projection fails browser hash verification—it visibly falls back to the checked-in alias-only sample rather than guessing.

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
- The live-feed cache behavior uses CloudFront's managed CachingDisabled policy only for `live/*`; the normal static dashboard keeps the lower-cost optimized cache behavior.
