# Prueba de punta a punta del vaciado de la DLQ de Plunk Lite (references/plunk-lite.md §4). Deja en la cola
# plunk-ses-events-dlq un rebote permanente firmado por SNS, como el que SNS deja ahí cuando no consigue
# entregarlo al webhook, para ver que Plunk Lite lo recoge, lo procesa y lo marca. Solo con Plunk Lite.
# Formato "snippet", como ses_setup: sustituye los __MARCADORES__ o usa run_snippet.py.
#   python3 run_snippet.py dlq_test.snippet.py --profile PERFIL --set REGION=eu-north-1 \
#     --set ACCOUNT_ID=123456789012 --set EMAIL_ID=<id del email> --set PROJECT_ID=<id del proyecto> \
#     --set FROM=pruebas@news.example.com
# Antes, desde Plunk: crea el contacto suscrito success@simulator.amazonses.com y envíale un email
# (plunk_send_email o /v1/send). EMAIL_ID es el id que devuelve el envío; PROJECT_ID, el del proyecto. Se usa
# success@ y no bounce@ porque bounce@ manda el rebote en vivo: el de la DLQ sería una copia ya registrada.
# El rebote es del simulador de SES: no cuenta en la reputación ni suprime la dirección, pero da de baja
# al contacto de prueba.
# Crea un topic y dos colas temporales y los borra al terminar, también si algo falla. Necesita una
# identidad con permisos de administración de SNS y SQS (no la de plunk-ses).

R = "__REGION__"
EXPECTED_ACCOUNT = "__ACCOUNT_ID__"
EMAIL_ID = "__EMAIL_ID__"
PROJECT_ID = "__PROJECT_ID__"
SENDER = "__FROM__"
RECIPIENT = "success@simulator.amazonses.com"
DLQ = "plunk-ses-events-dlq"
PREFIX = "plunk-lite-dlqtest"
log = []

ident = await call_boto3(service_name="sts", operation_name="GetCallerIdentity")
acct = ident["Account"]
if acct != EXPECTED_ACCOUNT:
    raise Exception(f"Cuenta inesperada {acct}")
real_dlq = f"https://sqs.{R}.amazonaws.com/{acct}/{DLQ}"
await call_boto3(service_name="sqs", operation_name="GetQueueAttributes", region_name=R,
    params={"QueueUrl": real_dlq, "AttributeNames": ["QueueArn"]})

# Un evento de SES como los que publica la configuration set: el webhook encuentra el email por sus
# etiquetas (el messageId es inventado) y, con más de 30 minutos, no espera a que se registre el envío
now = datetime.datetime.now(datetime.timezone.utc)
stamp = (now - datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
event = {
    "eventType": "Bounce",
    "bounce": {
        "bounceType": "Permanent", "bounceSubType": "General", "timestamp": stamp,
        "feedbackId": f"{PREFIX}-{now.strftime('%Y%m%d%H%M%S')}",
        "bouncedRecipients": [{"emailAddress": RECIPIENT, "action": "failed", "status": "5.1.1",
                               "diagnosticCode": "smtp; 550 5.1.1 prueba del vaciado de la DLQ de Plunk Lite"}],
    },
    "mail": {
        "timestamp": stamp, "source": SENDER, "destination": [RECIPIENT],
        "messageId": f"{PREFIX}-{EMAIL_ID}-{now.strftime('%Y%m%d%H%M%S')}",
        "tags": {"plunk_email_id": [EMAIL_ID], "plunk_project_id": [PROJECT_ID], "plunk_kind": ["email"]},
    },
}

topic_arn = None
target_url = None
probe_url = None
try:
    # SNS solo firma lo que publica: un topic temporal de la misma cuenta, cuya suscripción falla siempre
    # (una cola sin política, donde SNS no puede escribir) y deja el mensaje firmado en una DLQ temporal
    topic_arn = (await call_boto3(service_name="sns", operation_name="CreateTopic", region_name=R,
        params={"Name": f"{PREFIX}-topic"}))["TopicArn"]
    target_url = (await call_boto3(service_name="sqs", operation_name="CreateQueue", region_name=R,
        params={"QueueName": f"{PREFIX}-target"}))["QueueUrl"]
    probe_url = (await call_boto3(service_name="sqs", operation_name="CreateQueue", region_name=R,
        params={"QueueName": f"{PREFIX}-dlq", "Attributes": {"SqsManagedSseEnabled": "true"}}))["QueueUrl"]
    target_arn = f"arn:aws:sqs:{R}:{acct}:{PREFIX}-target"
    probe_arn = f"arn:aws:sqs:{R}:{acct}:{PREFIX}-dlq"
    await call_boto3(service_name="sqs", operation_name="SetQueueAttributes", region_name=R,
        params={"QueueUrl": probe_url, "Attributes": {"Policy": json.dumps({"Version": "2012-10-17", "Statement": [{
            "Effect": "Allow", "Principal": {"Service": "sns.amazonaws.com"}, "Action": "sqs:SendMessage",
            "Resource": probe_arn, "Condition": {"ArnEquals": {"aws:SourceArn": topic_arn}}}]})}})
    await call_boto3(service_name="sns", operation_name="Subscribe", region_name=R,
        params={"TopicArn": topic_arn, "Protocol": "sqs", "Endpoint": target_arn,
                "Attributes": {"RedrivePolicy": json.dumps({"deadLetterTargetArn": probe_arn})}})
    await asyncio.sleep(5)
    await call_boto3(service_name="sns", operation_name="Publish", region_name=R,
        params={"TopicArn": topic_arn, "Message": json.dumps(event)})
    log.append("rebote publicado en el topic temporal")

    body = None
    for _ in range(6):
        got = await call_boto3(service_name="sqs", operation_name="ReceiveMessage", region_name=R,
            params={"QueueUrl": probe_url, "WaitTimeSeconds": 10, "MaxNumberOfMessages": 1})
        if got.get("Messages"):
            body = got["Messages"][0]["Body"]
            break
    if not body:
        raise Exception("SNS no dejó el rebote en la DLQ temporal en un minuto")
    envelope = json.loads(body)
    if envelope.get("Type") != "Notification" or "Signature" not in envelope:
        raise Exception("El mensaje de la DLQ temporal no es un sobre firmado de SNS")
    log.append("sobre firmado recibido en la DLQ temporal")

    sent = await call_boto3(service_name="sqs", operation_name="SendMessage", region_name=R,
        params={"QueueUrl": real_dlq, "MessageBody": body})
    log.append(f"rebote firmado en {DLQ}: {sent['MessageId']} a las {datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M:%S')} UTC")
finally:
    if topic_arn:
        subs = await call_boto3(service_name="sns", operation_name="ListSubscriptionsByTopic", region_name=R,
            params={"TopicArn": topic_arn})
        for sub in subs.get("Subscriptions", []):
            if sub["SubscriptionArn"].startswith("arn:"):
                await call_boto3(service_name="sns", operation_name="Unsubscribe", region_name=R,
                    params={"SubscriptionArn": sub["SubscriptionArn"]})
        await call_boto3(service_name="sns", operation_name="DeleteTopic", region_name=R,
            params={"TopicArn": topic_arn})
    for url in (target_url, probe_url):
        if url:
            await call_boto3(service_name="sqs", operation_name="DeleteQueue", region_name=R,
                params={"QueueUrl": url})
    # SQS tarda hasta un minuto en dejar de listar una cola borrada
    log.append("recursos temporales borrados")

result = {"log": log, "next": "En unos 3 min (alarma ses-eventos-dlq) o en la próxima comprobación de 15 min: "
          "mira el log de plunk y la ficha del contacto (references/plunk-lite.md §4)."}
result
