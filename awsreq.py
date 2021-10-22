'''
  AWS request with v4 signature via proxy
'''

import hmac
import json
import os
from datetime import datetime
from hashlib import sha256
from logging import getLogger
from urllib.error import HTTPError
from urllib.request import Request, urlopen

region = os.getenv('AWS_DEFAULT_REGION', 'ap-northeast-1')
hashMethod, logger = 'AWS4-HMAC-SHA256', getLogger(__name__)
try:
    with open('accessKeys.csv') as f:
        kId = [ s for s in f if ',' in s ][-1].rstrip().split(',', 1)
    logger.debug('using accessKeys.csv')
    print('accessKey:', kId[0])
except FileNotFoundError:
    kId = os.getenv('AWS_ACCESS_KEYS')
    logger.debug('using env:AWS_ACCESS_%s', 'KEYS' if kId else 'KEY_ID')
    kId = kId.split(',', 1) if kId else list(map(os.getenv,
      ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY')))
kId, kSecret = kId[0], b'AWS4' + kId[1].encode('ascii')
logger.debug('accessKeyId: %s', kId)


def _prep(body, host, header, service):
    if isinstance(body, str):
        body = body.encode('utf8')
    elif not isinstance(body, bytes):
        body = json.dumps(body, ensure_ascii=False).encode('utf8')
        header.setdefault('content-type', 'application/x-amz-json-1.0')
    payloadHash = sha256(body).hexdigest()
    _region = 'us-east-1' if service in 'iam cloudfront wafv2' else region
    logger.debug('region: %s', _region)
    if service == 's3':
        if '.s3' not in host:
            host += '.s3'
        header.setdefault('content-type', 'text/plain')
        header['x-amz-content-sha256'] = payloadHash
    elif not host:
        host = f"{service}.{_region}"
    header.setdefault('content-type', 'application/x-www-form-urlencoded')
    return payloadHash, body or None, f"{host}.amazonaws.com", _region


def _hash(method, path, header, payloadHash):
    path, query = (path + '?').split('?', 1)
    if query:
        query = '&'.join(sorted(query[:-1].split('&')))
    keys = sorted(header)
    signedHeaders = ';'.join(keys)
    s = '\n'.join( f"{k}:{header[k]}" for k in keys )
    s = '\n'.join([method, path, query, s, '', signedHeaders, payloadHash])
    logger.debug('CanonicalRequest:\n%s\n--', s)
    requestHash = sha256(s.encode('ascii')).hexdigest()
    return requestHash, f"SignedHeaders={signedHeaders}"


def _sign(tok, ts, requestHash):
    sig, scope = kSecret, '/'.join(tok)
    tok.append('\n'.join([hashMethod, ts, scope, requestHash]))
    logger.debug('StringToSign:\n%s\n--', '\n'.join(tok))
    for s in tok:
        sig = hmac.new(sig, s.encode('ascii'), sha256).digest()
    sig = sig.hex()
    logger.debug('Signature:\n%s\n--', sig)
    return f"Signature={sig}", f"Credential={kId}/{scope}"


# send aws4 request
def send(service, host='', path='/', method='POST', body='', header=None):
    header = { k.lower(): header[k] for k in header or [] }
    payloadHash, body, host, region = _prep(body, host, header, service)
    header['host'] = host
    header['x-amz-date'] = ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    requestHash, signedHeaders = _hash(method, path, header, payloadHash)
    tok = [ts[:8], region, service, 'aws4_request']
    sig, cred = _sign(tok, ts, requestHash)
    header['Authorization'] = f"{hashMethod} {cred}, {signedHeaders}, {sig}"
    logger.debug('url: https://%s%s', host, path)
    req = Request(f"https://{host}{path}", body, header, method=method)
    return urlopen(req)


# show aws4 response in format
def show(*args, silent=False, format='json', **kwds):
    try:
        err, res = None, send(*args, **kwds)
    except HTTPError as e:
        err = res = e
    print('STATUS ', res.code, res.msg)
    ct = res.info().get('Content-Type', '')
    if format == 'json' and 'json' in ct:
        body = json.load(res)
        body = json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False)
    elif format == 'xml' and 'xml' in ct:
        from xml.dom.minidom import parse
        body = parse(res).toprettyxml(indent='  ')
    else:
        body = (ct and f"Content-Type: {ct}\n") + res.read().decode('utf8')
    logger.debug('STATUS  %s %s\n%s', res.code, res.msg, body)
    if silent:
        return (res.code, body) if silent == 'keep' else res.code
    print(body)
    if err:
        raise err
    return res.code


# parse aws4 response as xml
def tree(*args, silent=False, namespace='A', **kwds):
    try:
        res = send(*args, **kwds)
    except HTTPError as e:
        if silent:
            return e, None
        body = e.read().decode('ascii')
        print('STATUS ', e.code, e.msg, '\n' + body)
        logger.debug('STATUS  %s %s\n%s', e.code, e.msg, body)
        raise
    import xml.etree.ElementTree as ET
    xml = ET.parse(res).getroot()
    return xml, {namespace: xml.tag[1:xml.tag.find('}')]}
