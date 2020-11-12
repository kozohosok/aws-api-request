'''
  AWS request with v4 signature via proxy
'''

import base64
import hmac
import json
import os
import urllib.request as urlreq
from hashlib import sha256
from datetime import datetime
from logging import getLogger
from urllib.error import HTTPError

region = 'ap-northeast-1'
hashMethod, logger = 'AWS4-HMAC-SHA256', getLogger(__name__)
try:
    with open('accessKeys.csv') as f:
        authId = [ s for s in f if ',' in s ][-1].rstrip().split(',', 1)
    print('accessKey:', authId[0])
    logger.debug('accessKey: %s', authId[0])
except FileNotFoundError:
    authId = os.getenv('AWS_ACCESS_KEYS').split(',', 1)
authId, authKey = authId[0], authId[1].encode('ascii')


def _proxy(host, cred=None):
    logger.debug('proxy: %s', host)
    cred = base64.b64decode(cred).decode('ascii') + '@' if cred else ''
    urlreq.install_opener(urlreq.build_opener(urlreq.ProxyHandler({
      'https': f"http://{cred}{host}"})))
_proxy('YOUR_PROXY_HOST:PORT', os.getenv('HTTPS_PROXY_B64'))


def _prep(body, host, header, service):
    if isinstance(body, dict):
        body = json.dumps(body, separators=(',', ':'))
        header.setdefault('content-type', 'application/x-amz-json-1.0')
    if not isinstance(body, bytes):
        body = body.encode('ascii')
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
    s = '\n'.join([ f"{k}:{header[k]}" for k in keys ])
    s = '\n'.join([method, path, query, s, '', signedHeaders, payloadHash])
    logger.debug('CanonicalRequest:\n%s\n--', s)
    requestHash = sha256(s.encode('ascii')).hexdigest()
    return requestHash, f"SignedHeaders={signedHeaders}"


def _sign(tok, ts, requestHash):
    sig, scope = b'AWS4' + authKey, '/'.join(tok)
    tok.append('\n'.join([hashMethod, ts, scope, requestHash]))
    logger.debug('StringToSign:\n%s\n--', '\n'.join(tok))
    for s in tok:
        sig = hmac.new(sig, s.encode('ascii'), sha256).digest()
    sig = sig.hex()
    logger.debug('Signature:\n%s\n--', sig)
    return f"Signature={sig}", f"Credential={authId}/{scope}"


# send aws4 request
def send(service, host='', path='/', method='POST', body='', header=None):
    header = { k.lower(): header[k] for k in header or {} }
    payloadHash, body, host, region = _prep(body, host, header, service)
    header['host'] = host
    header['x-amz-date'] = ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    requestHash, signedHeaders = _hash(method, path, header, payloadHash)
    tok = [ts[:8], region, service, 'aws4_request']
    sig, cred = _sign(tok, ts, requestHash)
    header['Authorization'] = f"{hashMethod} {cred}, {signedHeaders}, {sig}"
    req = urlreq.Request(f"https://{host}{path}", body, header, method=method)
    return urlreq.urlopen(req)


# show aws4 response in format
def show(*args, silent=False, xml=False, **karg):
    try:
        res = send(*args, **karg)
    except HTTPError as e:
        res = e
    print('STATUS ', res.code, res.msg)
    ct = res.info().get('Content-Type', '')
    if 'json' in ct:
        body = json.dumps(json.load(res), sort_keys=True, indent=2)
    elif xml and 'xml' in ct:
        from xml.dom.minidom import parse
        body = parse(res).toprettyxml(indent='  ')
    else:
        body = (ct and f"Content-Type: {ct}\n") + res.read().decode('ascii')
    if silent:
        return (res.code, body) if silent == 'keep' else res.code
    print(body)
    if not isinstance(res, HTTPError):
        return res.code
    logger.debug('STATUS  %s %s\n%s', res.code, res.msg, body)
    raise res


# parse aws4 response as xml
def tree(*args, silent=False, namespace='A', **karg):
    try:
        res = send(*args, **karg)
    except HTTPError as e:
        if silent:
            return e, None
        body = e.read().decode('ascii')
        print('STATUS ', e.code, e.msg, '\n' + body)
        logger.debug('STATUS  %s %s\n%s', e.code, e.msg, body)
        raise
    import xml.etree.cElementTree as ET
    xml = ET.parse(res).getroot()
    return xml, {namespace: xml.tag[1:xml.tag.find('}')]}
