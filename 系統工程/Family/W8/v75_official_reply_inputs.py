"""Track a closed issuer inquiry separately from missing financial data."""
from email.utils import parsedate_to_datetime, parseaddr
from hashlib import sha256
import json

from v75_ready_data_inputs import manifest_files
from v75_remaining_inputs import time


def read(source, evaluation_at):
    if source is None: return None
    files = manifest_files(source, evaluation_at, schema='Family.W8.V75OfficialReplySource.v1',
        manifest_name='manifest.json', size_field='bytes')
    message = json.loads(files['SSGA_reply.json'])
    headers = {r['name'].lower(): r['value'] for r in message['headers']}
    responded = parsedate_to_datetime(headers['date'])
    # Quoted questions about fees/access are not a new offer from the issuer.
    body = message['body_plain'].replace('\r\n', '\n').split('\nFrom:', 1)[0]
    if (parseaddr(headers['from'])[1].lower() != 'fund_inquiry@ssga.com'
            or 'SPSB' not in headers['subject']
            or 'we are unable to provide the requested information' not in body
            or message['attachments'] != [] or responded > time(source['ingested_at'])):
        raise PermissionError('OFFICIAL_REPLY_IDENTITY_OR_DISPOSITION_MISMATCH')
    authentication = headers.get('authentication-results', '')
    return {'schema_version': 'Family.W8.VerifiedOfficialReplyStatus.v1',
        'source_reference': source['source_reference'], 'manifest_sha256': source['manifest_sha256'],
        'source_available_at': source['ingested_at'], 'raw_files_verified': len(files),
        'state_street': {'status': 'CLOSED_UNAVAILABLE', 'responded_at': responded.isoformat(),
            'awaiting_data_delivery': False, 'attachments_count': 0, 'paid_offer_in_reply': False,
            'scope': 'THIS_INQUIRY_ONLY__OTHER_SOURCES_NOT_RULED_OUT',
            'message_sha256': sha256(files['SSGA_reply.json']).hexdigest(),
            'delivered_header_checks': {k: k+'=pass' in authentication for k in ('dkim','spf','dmarc')},
            'authentication_basis': 'DELIVERED_GMAIL_AUTHENTICATION_RESULTS__NOT_INDEPENDENT_SIGNATURE_VERIFICATION'},
        'interactive_brokers': {'status': 'USER_REPORTED_SUBMITTED_AWAITING_REPLY',
            'ticket_id': None, 'reply_received': False,
            'evidence_basis': 'OWNER_INSTRUCTION_AND_HANDOFF_START_HERE__NO_TICKET_RECEIPT_OR_REPLY_ATTACHED',
            'earlier_plugin_feedback_is_same_ticket': False},
        'new_yield_ROC_or_NBBO_data_supplied': False,
        'financial_rules_changed': False, 'outreach_authorized': False, 'trade_action': 'NO_TRADE'}


def extend(pool, source, evaluation_at):
    status = read(source, evaluation_at)
    if status is None: return pool
    pool['official_reply_status'] = status
    pool['auxiliary_evidence_available_at'] = max(
        (pool.get('auxiliary_evidence_available_at', source['ingested_at']), source['ingested_at']), key=time)
    pool.setdefault('auxiliary_source_proofs', {})['OFFICIAL_REPLY_STATUS'] = {
        'source_reference': source['source_reference'], 'source_sha256': source['manifest_sha256'],
        'available_at': source['ingested_at']}
    return pool
