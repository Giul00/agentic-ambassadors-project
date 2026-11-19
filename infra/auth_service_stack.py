"""Infrastructure for the synthetic authorization service."""

from pathlib import Path

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, Tags
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct


class AuthServiceStack(Stack):
    """API Gateway, Lambda and DynamoDB rate-window storage for the demo."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Tags.of(self).add("project", "delivery-crew")
        Tags.of(self).add("environment", "workshop")
        Tags.of(self).add("data-classification", "synthetic")

        # Nombres acordados en delivery_crew/conventions.py y en el deployment_spec del diseño.
        counters = dynamodb.Table(
            self,
            "AuthorizationFrequency",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )

        service_dir = Path(__file__).resolve().parents[1] / "services" / "auth_service"
        function = lambda_.Function(
            self,
            "AuthorizationHandler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="auth_service.handler.lambda_handler",
            code=lambda_.Code.from_asset(str(service_dir), exclude=["tests", "tests/**", "*.ini", "*.md", "**/__pycache__"]),
            timeout=Duration.seconds(10),
            memory_size=256,
            tracing=lambda_.Tracing.ACTIVE,
            environment={"FREQUENCY_TABLE_NAME": counters.table_name, "FREQUENCY_STORE": "dynamodb"},
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
        counters.grant_read_write_data(function)

        api = apigateway.RestApi(
            self,
            "AuthorizationApi",
            rest_api_name="delivery-crew-auth-service",
            deploy_options=apigateway.StageOptions(
                stage_name="demo",
                logging_level=apigateway.MethodLoggingLevel.INFO,
                data_trace_enabled=False,
                metrics_enabled=True,
                tracing_enabled=True,
                throttling_burst_limit=20,
                throttling_rate_limit=10,
            ),
        )
        api.root.add_resource("authorize").add_method("POST", apigateway.LambdaIntegration(function))

        CfnOutput(self, "AuthorizeUrl", value=f"{api.url}authorize", description="POST endpoint for synthetic authorizations")
        CfnOutput(self, "FrequencyTableName", value=counters.table_name)
