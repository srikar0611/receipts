"""Offline structural checks for the optional AWS public-demo deployment."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "infra" / "aws" / "receipts-demo.template.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "deploy-demo.yml"


def test_aws_demo_template_keeps_s3_private_and_scopes_oidc() -> None:
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    resources = template["Resources"]

    bucket = resources["DemoBucket"]["Properties"]
    assert bucket["PublicAccessBlockConfiguration"] == {
        "BlockPublicAcls": True,
        "BlockPublicPolicy": True,
        "IgnorePublicAcls": True,
        "RestrictPublicBuckets": True,
    }
    assert bucket["OwnershipControls"]["Rules"] == [{"ObjectOwnership": "BucketOwnerEnforced"}]
    assert "WebsiteConfiguration" not in bucket

    distribution = resources["DemoDistribution"]["Properties"]["DistributionConfig"]
    origin = distribution["Origins"][0]
    assert origin["S3OriginConfig"] == {"OriginAccessIdentity": ""}
    assert origin["OriginAccessControlId"] == {"Fn::GetAtt": ["DemoOriginAccessControl", "Id"]}
    assert distribution["DefaultCacheBehavior"]["ViewerProtocolPolicy"] == "redirect-to-https"

    trust = resources["GitHubDemoDeployRole"]["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]
    condition = trust["Condition"]["StringEquals"]
    assert condition["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    assert condition["token.actions.githubusercontent.com:sub"] == {"Ref": "GitHubOidcSubject"}
    assert "*" not in json.dumps(condition)


def test_aws_demo_workflow_uses_oidc_not_long_lived_keys() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "id-token: write" in workflow
    assert "aws-actions/configure-aws-credentials@v4" in workflow
    assert "aws s3 sync docs/" in workflow
    assert "aws cloudfront create-invalidation" in workflow
    assert "AWS_ACCESS_KEY_ID" not in workflow
    assert "AWS_SECRET_ACCESS_KEY" not in workflow
