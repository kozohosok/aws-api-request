'''
  AWS request with v4 signature
'''

import json
import os
from datetime import datetime
from hashlib import sha256
from hmac import digest
from logging import getLogger
from urllib.error import HTTPError
from urllib.request import Request, urlopen

region = os.getenv('AWS_DEFAULT_REGION', 'ap-northeast-1')
hashMethod, logger = 'AWS4-HMAC-SHA256', getLogger(__name__)

def _credfile(src):
    with open(src) as f:
        keys = [ s for s in f if ',' in s ][-1].rstrip().split(',', 2)
    logger.debug('using %s', src)
    print('accessKey:', keys[0])
    return keys

def _credenv():
    ks = os.getenv('AWS_ACCESS_KEYS')
    logger.debug('using env:AWS_ACCESS_%s', 'KEYS' if ks else 'KEY_ID')
    if ks:
        return ks.split(',', 1)
    return list(map(os.getenv, ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY')))

def _cred(src):
    try:
        keys = _credfile(src)
    except FileNotFoundError:
        keys = _credenv()
    logger.debug('accessKeyId: %s', keys[0])
    return keys[0], b'AWS4' + keys[1].encode('ascii')
    
kId, kSecret = _cred('accessKeys.csv')


def _encode(body, header):
    header = { k.lower(): header[k] for k in header or [] }
    if isinstance(body, str):
        body = body.encode('utf8')
    elif not isinstance(body, bytes):
        body = json.dumps(body, ensure_ascii=False).encode('utf8')
        header.setdefault('content-type', 'application/x-amz-json-1.0')
    return body, header

def _region(service):
    x = 'us-east-1' if service in 'iam cloudfront wafv2' else region
    logger.debug('region: %s', x)
    return x

def _prep(service, host, header, body):
    payloadHash, region = sha256(body).hexdigest(), _region(service)
    if service == 's3':
        host += '' if '.s3' in host else '.s3'
        header['x-amz-content-sha256'] = payloadHash
        header.setdefault('content-type', 'text/plain')
    elif not host:
        host = f"{service}.{region}"
    header.setdefault('content-type', 'application/x-www-form-urlencoded')
    header['x-amz-date'] = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    return region, f"{host}.amazonaws.com", payloadHash

def _normalize(header):
    keys = sorted(header)
    signedHeaders = ';'.join(keys)
    normalizedHeaders = '\n'.join( f"{k}:{header[k]}" for k in keys )
    return normalizedHeaders, signedHeaders

def _hash(method, path, header, payloadHash):
    path, query = (path + '?').split('?', 1)
    if query:
        query = '&'.join(sorted(query[:-1].split('&')))
    s, signedHeaders = _normalize(header)
    s = '\n'.join([method, path, query, s, '', signedHeaders, payloadHash])
    logger.debug('CanonicalRequest:\n%s\n--', s)
    requestHash = sha256(s.encode('ascii')).hexdigest()
    return requestHash, f"SignedHeaders={signedHeaders}"

def _sign(tok, timestamp, requestHash):
    key, scope = kSecret, '/'.join(tok)
    tok.append('\n'.join([hashMethod, timestamp, scope, requestHash]))
    logger.debug('StringToSign:\n%s\n--', '\n'.join(tok))
    for s in tok:
        key = digest(key, s.encode('ascii'), sha256)
    sig = key.hex()
    logger.debug('Signature:\n%s\n--', sig)
    return f"Signature={sig}", f"Credential={kId}/{scope}"

# send aws4 request
def send(service, host='', path='/', method='POST', body='', header=None):
    body, header = _encode(body, header)
    region, host, hash = _prep(service, host, header, body)
    header['host'], ts = host, header['x-amz-date']
    hash, signedHeaders = _hash(method, path, header, hash)
    sig, cred = _sign([ts[:8], region, service, 'aws4_request'], ts, hash)
    header['Authorization'] = f"{hashMethod} {cred}, {signedHeaders}, {sig}"
    url = f"https://{host}{path}"
    logger.debug('url: %s', url)
    return urlopen(Request(url, body or None, header, method=method))


def _status(res, body=None):
    print('STATUS ', res.code, res.msg)
    if body is None:
        body = res.read().decode('ascii')
        print(body)
    logger.debug('STATUS  %s %s\n%s', res.code, res.msg, body)
    return body

def _readjson(res):
    x = json.load(res)
    return json.dumps(x, indent=2, sort_keys=True, ensure_ascii=False)

def _readxml(res):
    from xml.dom.minidom import parse
    return parse(res).toprettyxml(indent='  ')

def _read(res, format):
    ct = res.info().get('Content-Type', '')
    for k,f in [('json', _readjson), ('xml', _readxml)] if format else []:
        if k in ct:
            return f(res)
    return (ct and f"Content-Type: {ct}\n") + res.read().decode('utf8')

# show aws4 response in format
def show(*args, silent=False, format=True, **kwds):
    try:
        err, res = None, send(*args, **kwds)
    except HTTPError as e:
        err = res = e
    body = _status(res, _read(res, format))
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
        if silent != 'any':
            _status(e)
        if silent:
            return e, None
        raise
    import xml.etree.ElementTree as ET
    xml = ET.parse(res).getroot()
    return xml, {namespace: xml.tag[1:xml.tag.find('}')]}
