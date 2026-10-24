# Configura AWS SES para Plunk. Es idempotente: se puede repetir sin duplicar nada.
# Formato "snippet": código con await en el nivel superior y `result` como última expresión.
#  - Con el MCP oficial de AWS: sustituye los __MARCADORES__ y pásalo tal cual a run_script.
#  - Sin él: python3 run_snippet.py ses_setup.snippet.py --profile PERFIL --set REGION=... (ver run_snippet.py)
# No crea access keys: la persona las crea en la consola y las pega en Dokploy.
# Requisito: la API de Plunk ya responde por HTTPS en API_DOMAIN (Plunk confirma la suscripción SNS al recibirla).

R = "__REGION__"
EXPECTED_ACCOUNT = "__ACCOUNT_ID__"
SERVER_IP = "__SERVER_IP__/32"
ENDPOINT = "https://__API_DOMAIN__/webhooks/sns"
USER = "plunk-ses"
TOPIC = "plunk-ses-events"
CONFIG_SETS = {
    "plunk-configuration-set": ["DELIVERY", "OPEN", "CLICK", "BOUNCE", "COMPLAINT"],
    "plunk-no-tracking-configuration-set": ["DELIVERY", "BOUNCE", "COMPLAINT"],
}
log = []

ident = await call_boto3(service_name="sts", operation_name="GetCallerIdentity")
acct = ident["Account"]
if acct != EXPECTED_ACCOUNT:
    raise Exception(f"Cuenta inesperada {acct}")

def already(e):
    s = str(e)
    return "AlreadyExists" in s or "EntityAlreadyExists" in s

# 1. IAM user (no access key) with least-privilege SES policy, usable only from the Plunk server
try:
    await call_boto3(service_name="iam", operation_name="CreateUser",
        params={"UserName": USER, "Tags": [{"Key": "app", "Value": "plunk"}]})
    log.append("iam user creado")
except Exception as e:
    if not already(e): raise
    log.append("iam user ya existía")

policy = {
    "Version": "2012-10-17",
    "Statement": [{
        "Sid": "PlunkSES",
        "Effect": "Allow",
        "Action": [
            "ses:SendRawEmail", "ses:GetSendQuota",
            "ses:VerifyDomainDkim", "ses:GetIdentityDkimAttributes",
            "ses:GetIdentityVerificationAttributes", "ses:SetIdentityMailFromDomain",
            "ses:SetIdentityFeedbackForwardingEnabled", "ses:DeleteIdentity",
        ],
        "Resource": "*",
        "Condition": {
            "StringEquals": {"aws:RequestedRegion": R},
            "IpAddress": {"aws:SourceIp": SERVER_IP},
        },
    }],
}
await call_boto3(service_name="iam", operation_name="PutUserPolicy",
    params={"UserName": USER, "PolicyName": "plunk-ses-sending", "PolicyDocument": json.dumps(policy)})
log.append("política inline aplicada")

# 2. SNS topic for SES events
t = await call_boto3(service_name="sns", operation_name="CreateTopic", region_name=R,
    params={"Name": TOPIC, "Attributes": {"SignatureVersion": "2"}, "Tags": [{"Key": "app", "Value": "plunk"}]})
topic_arn = t["TopicArn"]
topic_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {"Sid": "OwnerManage", "Effect": "Allow", "Principal": {"AWS": f"arn:aws:iam::{acct}:root"},
         "Action": ["sns:GetTopicAttributes", "sns:SetTopicAttributes", "sns:AddPermission", "sns:RemovePermission",
                    "sns:DeleteTopic", "sns:Subscribe", "sns:ListSubscriptionsByTopic", "sns:Publish"],
         "Resource": topic_arn},
        {"Sid": "AllowSESPublish", "Effect": "Allow", "Principal": {"Service": "ses.amazonaws.com"},
         "Action": "sns:Publish", "Resource": topic_arn,
         "Condition": {"StringEquals": {"AWS:SourceAccount": acct},
                       "ArnLike": {"AWS:SourceArn": f"arn:aws:ses:{R}:{acct}:configuration-set/*"}}},
    ],
}
await call_boto3(service_name="sns", operation_name="SetTopicAttributes", region_name=R,
    params={"TopicArn": topic_arn, "AttributeName": "Policy", "AttributeValue": json.dumps(topic_policy)})
log.append(f"topic listo {topic_arn}")

# 3. Configuration sets with SNS event destinations
for cs, events in CONFIG_SETS.items():
    try:
        await call_boto3(service_name="sesv2", operation_name="CreateConfigurationSet", region_name=R,
            params={"ConfigurationSetName": cs, "ReputationOptions": {"ReputationMetricsEnabled": True},
                    "SendingOptions": {"SendingEnabled": True}})
        log.append(f"config set {cs} creado")
    except Exception as e:
        if not already(e): raise
        log.append(f"config set {cs} ya existía")
    try:
        await call_boto3(service_name="sesv2", operation_name="CreateConfigurationSetEventDestination", region_name=R,
            params={"ConfigurationSetName": cs, "EventDestinationName": "plunk-sns",
                    "EventDestination": {"Enabled": True, "MatchingEventTypes": events,
                                         "SnsDestination": {"TopicArn": topic_arn}}})
        log.append(f"destino de eventos en {cs}: {events}")
    except Exception as e:
        if not already(e): raise
        log.append(f"destino de eventos en {cs} ya existía")

# 4. HTTPS subscription to Plunk (Plunk confirms it automatically)
subs = await call_boto3(service_name="sns", operation_name="ListSubscriptionsByTopic", region_name=R, params={"TopicArn": topic_arn})
if not any(s.get("Endpoint") == ENDPOINT for s in subs.get("Subscriptions", [])):
    s = await call_boto3(service_name="sns", operation_name="Subscribe", region_name=R,
        params={"TopicArn": topic_arn, "Protocol": "https", "Endpoint": ENDPOINT, "ReturnSubscriptionArn": True})
    log.append(f"suscripción creada: {s.get('SubscriptionArn')}")
else:
    log.append("suscripción ya existía")

result = {"account": acct, "log": log, "topic_arn": topic_arn}
result
