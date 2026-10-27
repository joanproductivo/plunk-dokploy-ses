# Estado de AWS SES para Plunk. Solo lectura: no cambia nada.
# Formato "snippet": código con await en el nivel superior y `result` como última expresión.
#  - Con el MCP oficial de AWS: sustituye los __MARCADORES__ y pásalo tal cual a run_script.
#  - Sin él: python3 run_snippet.py ses_check.snippet.py --profile PERFIL --set REGION=... --set ACCOUNT_ID=...
# Qué mirar en el resultado: ver references/aws-ses.md, sección "Comprobar el estado".

R = "__REGION__"
EXPECTED_ACCOUNT = "__ACCOUNT_ID__"
USER = "plunk-ses"
TOPIC = "plunk-ses-events"
CONFIG_SETS = ["plunk-configuration-set", "plunk-no-tracking-configuration-set"]

ident = await call_boto3(service_name="sts", operation_name="GetCallerIdentity")
acct = ident["Account"]
if acct != EXPECTED_ACCOUNT:
    raise Exception(f"Cuenta inesperada {acct}")

def err(e):
    return {"error": str(e)[:200]}

account = await call_boto3(service_name="sesv2", operation_name="GetAccount", region_name=R)
quota = account.get("SendQuota", {})
# El plan de precios es un campo reciente; se lee por nombre parcial porque algunos validadores aún no lo conocen
pricing = next((v for k, v in account.items() if "Pricing" in k), None) or {}
summary = {
    "production": account.get("ProductionAccessEnabled"),
    "review": account.get("Details", {}).get("ReviewDetails"),
    "mail_type": account.get("Details", {}).get("MailType"),
    "website": account.get("Details", {}).get("WebsiteURL"),
    "enforcement": account.get("EnforcementStatus"),
    "sending_enabled": account.get("SendingEnabled"),
    "quota_24h": quota.get("Max24HourSend"),
    "rate_per_second": quota.get("MaxSendRate"),
    "sent_last_24h": quota.get("SentLast24Hours"),
    "pricing_plan": pricing.get("CurrentPlan"),
    "suppressed_reasons": account.get("SuppressionAttributes", {}).get("SuppressedReasons"),
}

listed = await call_boto3(service_name="sesv2", operation_name="ListEmailIdentities", region_name=R)
names = [i["IdentityName"] for i in listed.get("EmailIdentities", [])]
details = await asyncio.gather(*[
    call_boto3(service_name="sesv2", operation_name="GetEmailIdentity", region_name=R, params={"EmailIdentity": n})
    for n in names], return_exceptions=True)
identities = {}
for n, d in zip(names, details):
    if isinstance(d, Exception):
        identities[n] = err(d)
        continue
    identities[n] = {
        "type": d.get("IdentityType"),
        "verified_for_sending": d.get("VerifiedForSendingStatus"),
        "dkim": d.get("DkimAttributes", {}).get("Status"),
        "dkim_tokens": d.get("DkimAttributes", {}).get("Tokens"),
        "mail_from": d.get("MailFromAttributes", {}).get("MailFromDomain"),
        "mail_from_status": d.get("MailFromAttributes", {}).get("MailFromDomainStatus"),
    }

dests = await asyncio.gather(*[
    call_boto3(service_name="sesv2", operation_name="GetConfigurationSetEventDestinations", region_name=R,
               params={"ConfigurationSetName": cs})
    for cs in CONFIG_SETS], return_exceptions=True)
config_sets = {}
for cs, d in zip(CONFIG_SETS, dests):
    if isinstance(d, Exception):
        config_sets[cs] = err(d)
        continue
    config_sets[cs] = [{"name": x.get("Name"), "enabled": x.get("Enabled"),
                        "events": x.get("MatchingEventTypes"),
                        "sns": x.get("SnsDestination", {}).get("TopicArn")}
                       for x in d.get("EventDestinations", [])]

topic_arn = f"arn:aws:sns:{R}:{acct}:{TOPIC}"
try:
    subs = await call_boto3(service_name="sns", operation_name="ListSubscriptionsByTopic", region_name=R,
                            params={"TopicArn": topic_arn})
    subscriptions = [{"endpoint": s.get("Endpoint"), "protocol": s.get("Protocol"),
                      "arn": s.get("SubscriptionArn"),
                      "confirmed": s.get("SubscriptionArn") not in ("PendingConfirmation", "Deleted")}
                     for s in subs.get("Subscriptions", [])]
    for sub in subscriptions:
        if not sub["confirmed"]:
            continue
        attrs = (await call_boto3(service_name="sns", operation_name="GetSubscriptionAttributes", region_name=R,
                                  params={"SubscriptionArn": sub.pop("arn")})).get("Attributes", {})
        effective = json.loads(attrs.get("EffectiveDeliveryPolicy") or "{}")
        sub["retries"] = effective.get("healthyRetryPolicy", {}).get("numRetries")
        sub["dlq"] = json.loads(attrs["RedrivePolicy"]).get("deadLetterTargetArn") if attrs.get("RedrivePolicy") else None
    for sub in subscriptions:
        sub.pop("arn", None)
except Exception as e:
    subscriptions = err(e)

iam_user, keys, policy = await asyncio.gather(
    call_boto3(service_name="iam", operation_name="GetUser", params={"UserName": USER}),
    call_boto3(service_name="iam", operation_name="ListAccessKeys", params={"UserName": USER}),
    call_boto3(service_name="iam", operation_name="GetUserPolicy", params={"UserName": USER, "PolicyName": "plunk-ses-sending"}),
    return_exceptions=True)
iam = {"user_exists": not isinstance(iam_user, Exception)}
if not isinstance(keys, Exception):
    # Solo metadatos: el final del id para que la persona reconozca su clave, nunca el secreto
    iam["access_keys"] = [{"id_ends_with": k["AccessKeyId"][-4:], "status": k["Status"],
                           "created": str(k.get("CreateDate"))} for k in keys.get("AccessKeyMetadata", [])]
if not isinstance(policy, Exception):
    doc = policy["PolicyDocument"]
    try:
        if isinstance(doc, str):
            doc = json.loads(doc)
        cond = doc["Statement"][0].get("Condition", {})
        iam["allowed_ip"] = cond.get("IpAddress", {}).get("aws:SourceIp")
        iam["allowed_region"] = cond.get("StringEquals", {}).get("aws:RequestedRegion")
    except Exception as e:
        iam["policy"] = {"present": True, "unparsed": str(e)[:100]}
else:
    iam["policy"] = err(policy)

result = {"account": acct, "region": R, "ses": summary, "identities": identities,
          "config_sets": config_sets, "sns_subscriptions": subscriptions, "iam": iam}
result
