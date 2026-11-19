#!/usr/bin/env python3
"""CDK entry point for the synthetic authorization-service demo."""

import os

import aws_cdk as cdk

from auth_service_stack import AuthServiceStack


app = cdk.App()
AuthServiceStack(
    app,
    "DeliveryCrewAuthService",
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION", "us-west-2"),
    ),
    description="Synthetic authorization demo for Delivery Crew. No card data is stored.",
)
app.synth()
