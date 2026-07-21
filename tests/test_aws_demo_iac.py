"""Offline structural checks for the optional AWS public-demo deployment."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "infra" / "aws" / "receipts-demo.template.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "deploy-demo.yml"
LIVE_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "publish-live-evidence.yml"


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
    live_behavior = distribution["CacheBehaviors"][0]
    assert live_behavior["PathPattern"] == "live/*"
    # AWS managed CachingDisabled: the latest receipt must not sit at an edge.
    assert live_behavior["CachePolicyId"] == "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"

    trust = resources["GitHubDemoDeployRole"]["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]
    condition = trust["Condition"]["StringEquals"]
    assert condition["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    assert condition["token.actions.githubusercontent.com:sub"] == {"Ref": "GitHubOidcSubject"}
    assert "*" not in json.dumps(condition)

    site_policy = resources["GitHubDemoDeployRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    live_deny = next(statement for statement in site_policy if statement["Sid"] == "DenyLiveFeedObjectsToSiteDeployer")
    assert live_deny["Effect"] == "Deny"
    assert live_deny["Resource"] == {"Fn::Sub": "${DemoBucket.Arn}/live/*"}

    live_role = resources["GitHubLiveFeedPublisherRole"]["Properties"]
    live_trust = live_role["AssumeRolePolicyDocument"]["Statement"][0]["Condition"]["StringEquals"]
    assert live_trust == condition
    live_statements = live_role["Policies"][0]["PolicyDocument"]["Statement"]
    publish = next(statement for statement in live_statements if statement["Sid"] == "PutOnlyLatestSanitizedFeedObjects")
    assert publish["Action"] == "s3:PutObject"
    assert publish["Resource"] == [
        {"Fn::Sub": "${DemoBucket.Arn}/live/latest.json"},
        {"Fn::Sub": "${DemoBucket.Arn}/live/latest.html"},
    ]


def test_aws_demo_workflow_uses_oidc_not_long_lived_keys() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "id-token: write" in workflow
    assert "aws-actions/configure-aws-credentials@v4" in workflow
    assert "aws s3 sync docs/" in workflow
    assert '--exclude "live/*"' in workflow
    assert "aws cloudfront create-invalidation" in workflow
    assert "AWS_ACCESS_KEY_ID" not in workflow
    assert "AWS_SECRET_ACCESS_KEY" not in workflow


def test_live_feed_workflow_builds_a_verified_public_projection_and_uses_prefix_scoped_oidc() -> None:
    workflow = LIVE_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "github.ref == 'refs/heads/master'" in workflow
    assert "id-token: write" in workflow
    assert "AWS_LIVE_FEED_ROLE_TO_ASSUME" in workflow
    assert "receipts demo --live" in workflow
    assert "receipts export-public" in workflow
    assert "--landing-href ../index.html" in workflow
    assert 'receipts verify "$manifest"' in workflow
    assert 'receipts verify "$RUNNER_TEMP/latest.json"' in workflow
    assert "aws s3api put-object" in workflow
    assert "--key live/latest.json" in workflow
    assert "--key live/latest.html" in workflow
    assert "no-store, max-age=0, must-revalidate" in workflow
    assert "aws s3 sync" not in workflow
    assert "AWS_ACCESS_KEY_ID" not in workflow
    assert "AWS_SECRET_ACCESS_KEY" not in workflow
