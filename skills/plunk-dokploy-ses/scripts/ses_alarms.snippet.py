# Alarmas de CloudWatch para la reputación de SES y la cola de eventos perdidos. Opcional, recomendado
# antes de enviar en volumen. Es idempotente: se puede repetir sin duplicar nada.
# Formato "snippet", como ses_setup: sustituye los __MARCADORES__ o usa run_snippet.py.
#   python3 run_snippet.py ses_alarms.snippet.py --profile PERFIL --set REGION=eu-north-1 \
#     --set ACCOUNT_ID=123456789012 --set ALARM_EMAIL=persona@example.com \
#     --set API_DOMAIN=envio-api.example.com --set PANEL=si
# Cabe en la capa gratuita: 3 alarmas (10 gratis) y emails de SNS (1.000 gratis al mes).
# La suscripción de email hay que confirmarla desde el correo que manda AWS.
# PANEL=si (solo con Plunk Lite) suscribe además el topic al webhook de Plunk, que confirma solo, y las
# alarmas salen también en el banner del panel. Con la imagen oficial, PANEL=no.

R = "__REGION__"
EXPECTED_ACCOUNT = "__ACCOUNT_ID__"
EMAIL = "__ALARM_EMAIL__"
ENDPOINT = "https://__API_DOMAIN__/webhooks/sns"
PANEL = "__PANEL__".strip().lower() in ("si", "sí", "yes", "true", "1")
# El nombre lo reconoce Plunk Lite (AwsAlarmService): sus mensajes nunca se toman por eventos de SES
TOPIC = "plunk-alarmas"
DLQ = "plunk-ses-events-dlq"
# Los mismos reintentos que la suscripción de eventos (ses_setup), y sin DLQ: si la DLQ de eventos
# recibiera los avisos de las alarmas, haría saltar su propia alarma
DELIVERY_POLICY = {
    "healthyRetryPolicy": {
        "minDelayTarget": 10, "maxDelayTarget": 100, "numRetries": 40,
        "numNoDelayRetries": 0, "numMinDelayRetries": 5, "numMaxDelayRetries": 15,
        "backoffFunction": "exponential",
    }
}
log = []

ident = await call_boto3(service_name="sts", operation_name="GetCallerIdentity")
if ident["Account"] != EXPECTED_ACCOUNT:
    raise Exception(f"Cuenta inesperada {ident['Account']}")

t = await call_boto3(service_name="sns", operation_name="CreateTopic", region_name=R,
    params={"Name": TOPIC, "Tags": [{"Key": "app", "Value": "plunk"}]})
topic_arn = t["TopicArn"]
subs = (await call_boto3(service_name="sns", operation_name="ListSubscriptionsByTopic", region_name=R,
    params={"TopicArn": topic_arn})).get("Subscriptions", [])

if not any(s.get("Endpoint") == EMAIL for s in subs):
    await call_boto3(service_name="sns", operation_name="Subscribe", region_name=R,
        params={"TopicArn": topic_arn, "Protocol": "email", "Endpoint": EMAIL})
    log.append(f"suscripción de email creada: confírmala desde el correo de AWS que llega a {EMAIL}")
else:
    log.append("suscripción de email ya existía")

if PANEL:
    if not any(s.get("Endpoint") == ENDPOINT for s in subs):
        await call_boto3(service_name="sns", operation_name="Subscribe", region_name=R,
            params={"TopicArn": topic_arn, "Protocol": "https", "Endpoint": ENDPOINT,
                    "Attributes": {"DeliveryPolicy": json.dumps(DELIVERY_POLICY)}})
        log.append("suscripción al panel creada (Plunk Lite la confirma solo)")
    else:
        log.append("suscripción al panel ya existía")

common = {"AlarmActions": [topic_arn], "OKActions": [topic_arn], "EvaluationPeriods": 1,
          "ComparisonOperator": "GreaterThanOrEqualToThreshold", "Statistic": "Maximum"}
alarms = [
    # SES publica Reputation.* a intervalos irregulares (de 20 min a varias horas): sin datos se
    # conserva el estado (ignore) para no alternar ALARM y OK con un email cada vez
    {"AlarmName": "ses-rebotes-alto", "Namespace": "AWS/SES", "MetricName": "Reputation.BounceRate",
     "Period": 3600, "Threshold": 0.04, "TreatMissingData": "ignore",
     "AlarmDescription": "La tasa de rebotes de SES llega al 4 %. AWS revisa la cuenta al 5 % y la pausa al 10 %. Revisa la última campaña o el formulario de altas."},
    {"AlarmName": "ses-quejas-alto", "Namespace": "AWS/SES", "MetricName": "Reputation.ComplaintRate",
     "Period": 3600, "Threshold": 0.0008, "TreatMissingData": "ignore",
     "AlarmDescription": "La tasa de quejas de SES llega al 0,08 %. AWS revisa la cuenta al 0,1 % y la pausa al 0,5 %."},
    # SQS deja de publicar la métrica con la cola inactiva: sin datos es que no hay nada (notBreaching)
    {"AlarmName": "ses-eventos-dlq", "Namespace": "AWS/SQS", "MetricName": "ApproximateNumberOfMessagesVisible",
     "Dimensions": [{"Name": "QueueName", "Value": DLQ}], "Period": 300, "Threshold": 1,
     "TreatMissingData": "notBreaching",
     "AlarmDescription": f"Hay eventos de SES (rebotes, quejas) en la cola {DLQ}: el webhook de Plunk no los aceptó. Revisa que la API responda."},
]
for a in alarms:
    await call_boto3(service_name="cloudwatch", operation_name="PutMetricAlarm", region_name=R, params={**common, **a})
log.append("alarmas: " + ", ".join(a["AlarmName"] for a in alarms))

result = {"topic_arn": topic_arn, "log": log}
result
