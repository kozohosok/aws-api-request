'''
  AWS utility for CloudFormation stack
'''
import awsreq as req
import os
import sys
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote


def _stackevents(xml, ns, *args):
    keys = ('LogicalResourceId', 'ResourceStatus', 'Timestamp') + args
    for el in xml.findall('.//A:StackEvents/A:member', ns):
        yield ( el.findtext(f"A:{k}", '', ns) for k in keys )

def _stackstatus(info, key, stat, ts):
    if '_CLEANUP_' in stat:
        return
    info['lim'] -= stat.endswith('_IN_PROGRESS')
    s = f"  ----  {ts}  {stat}"
    if 'fin' not in info:
        info['fin'], s = stat, s + '  ' + '-' * (75 - len(s))
    return s

def _resourcestatus(info, key, stat, ts):
    hms = ts[11:19]
    if stat.endswith('_FAILED'):
        info.setdefault('ok', 'fin' in info)
        return f"{stat}  {hms}\t{key}"
    if info['stamp'].get(key, '') < ts:
        info['busy'], info['stamp'][key] = 0, ts
        return f"    {hms}  {stat}\t{key}"

def _statuslines(xml, info):
    info['lim'], ns = 3, dict(A=xml.tag[1:xml.tag.find('}')])
    for key,stat,ts in _stackevents(xml, ns):
        f = _stackstatus if key == info['stack'] else _resourcestatus
        yield f(info, key, stat, ts)
        if not info['lim']:
            break
    if xml.find('.//A:NextToken', ns):
        yield '  ...'

def _parsebody(body, buf, **info):
    info['busy'] = buf[0][1] == '#'
    buf += filter(None, _statuslines(ET.fromstring(body), info))
    fin = info.get('fin', 'lots_IN_PROGRESS')
    busy = fin.endswith('_IN_PROGRESS') and info['busy'] + 1
    return busy, info.get('ok', 1) and not fin.startswith('ROLLBACK')

def _eventbody(name, buf):
    res = req.send('cloudformation',
      body=f"Action=DescribeStackEvents&StackName={name}")
    s = f"status  {res.code} {res.msg} "
    buf.append(s + name.rjust(79 - len(s)))
    return res.read().decode('ascii')

def _describe(name, stamp, sep=None):
    buf = [sep] if sep else []
    try:
        body = _eventbody(name, buf)
    except req.HTTPError as e:
        print('\n'.join(buf) + '\nstatus ', e.code, e.msg)
        return 0, e.read().decode('ascii'), e.code // 100 == 4 and '!'
    busy, ok = _parsebody(body, buf, stack=name, stamp=stamp)
    print(buf[0] if busy == 2 else '\n'.join(buf))
    return busy, body, ok

def _watch(name, interval):
    stamp = {}
    busy, body, ok = _describe(name, stamp)
    while busy:
        time.sleep(interval * busy)
        busy, body, ok = _describe(name, stamp, '\n'[busy-1:] + '#' * 79)
    if ok != '!':
        print(f"\nStackName: {name} (done)\n" + '=' * 79)
    return body, ok

def _writebody(body, failed, dst):
    if failed:
        return print(body)
    if dst:
        with open(dst, 'w') as f:
            f.write(body)
    return 200

def describeEvents(name, watch=0, delay=0, keep=False):
    print('_' * 79 if delay else f"StackName: {name}\n")
    time.sleep(delay)
    body, ok = _watch(name, watch) if 0 < watch else _describe(name, {})[1:]
    file = sys.argv[0] + '.dat'
    if ok:
        return _writebody(body, ok == '!', keep and file)
    if os.path.isfile(file):
        os.remove(file)
    sys.stderr.write(body)


def _resourcereason(info, key, stat, ts):
    msg = info['show'] in stat and info['msg']
    if msg and info['stamp'].setdefault(key, ts) == ts:
        return f"{stat}  {ts[11:19]}\t{key}\n{msg}\n"

def _reasonlines(xml, ns, **info):
    info['lim'], info['fin'], info['stamp'] = 3, 1, {}
    for key,stat,ts,msg in _stackevents(xml, ns, 'ResourceStatusReason'):
        info['msg'] = msg
        f = _stackstatus if key == info['stack'] else _resourcereason
        yield f(info, key, stat, ts)
        if not info['lim']:
            break

def showStatusReasons(name, status_key='FAILED'):
    print(f"StackName: {name}\n")
    xml, ns = req.tree('cloudformation',
      body=f"Action=DescribeStackEvents&StackName={name}", silent=True)
    if not ns:
        return
    for s in filter(None, _reasonlines(xml, ns, stack=name, show=status_key)):
        print(s)


def exists(name):
    xml, ns = req.tree('cloudformation',
      body=f"Action=DescribeStacks&StackName={name}", silent='any')
    return ns and xml.find('.//A:Stacks/A:member/A:StackStatus', ns).text


def _accept(name, confirm, msg=''):
    if confirm:
        print(end=f"StackName: {name}{msg}\nStackName? ", flush=True)
        return name == input() or print('bye')
    print(f"StackName: {name}{msg}\n")
    return True

def delete(name, confirm=True, watch=0):
    if not _accept(name, confirm):
        return
    i = req.show('cloudformation',
      body=f"Action=DeleteStack&StackName={name}", silent=True)
    return describeEvents(name, watch, 5) if watch and i // 100 == 2 else i


def newer(file, ref):
    return os.stat(ref).st_mtime < os.stat(file).st_mtime

def escape(s):
    return quote(s, safe="!'()*-._~")

def _ensureurl(host, src):
    stamp = f"{src}.stamp"
    bucket, path = f"{host}/{src}".split('/', 1)
    if os.path.isfile(stamp) and newer(stamp, src):
        return bucket, path
    print('---------- upload template ----------\nhost:', host)
    with open(src, 'rb') as f:
        req.show('s3', bucket, f"/{path}", 'PUT', f.read(), silent=True)
    open(stamp, 'w').close()
    return bucket, path

def _template(host, src, act):
    if not host:
        with open(src, encoding='utf8') as f:
            return 'TemplateBody=' + escape(f.read())
    bucket, path = _ensureurl(host, src)
    print('----------', act.lower(), 'stack ----------')
    s3 = '' if '.s3' in bucket else '.s3'
    return f"TemplateURL=https://{bucket}{s3}.amazonaws.com/{path}"

def _parameter(params):
    if not isinstance(params, dict):
        return ''
    print('params:', params)
    return ''.join( f"&Parameters.member{i}.Parameter{x}"
      for i,k in enumerate(params)
      for x in ('Key=' + k, 'Value=' + escape(params[k])) )

def _resetrollback(name):
    print('reset ROLLBACK_COMPLETE')
    delete(name, False)
    while exists(name):
        time.sleep(10)

def _action(name, src, status, confirm):
    if status == -1:
        status = exists(name) or ''
        if status.endswith('_IN_PROGRESS'):
            return print(name, status, '...')
    if status == 'ROLLBACK_COMPLETE':
        _resetrollback(name)
    elif status:
        return _accept(name, confirm, f" ({src} UP)") and 'Update'
    print(f"StackName: {name} ({src})\n")
    return 'Create'

def _changestatus(msg):
    if 'No update' in msg:
        print('status  204\tno update\n')
        return 204
    print(msg)

def create(name, src, host='', update=False, confirm=True, watch=0, params=''):
    act = _action(name, src, update, confirm)
    if not act:
        return
    buf = [f"Action={act}Stack&StackName={name}" + _parameter(params),
      'Capabilities.member.1=CAPABILITY_NAMED_IAM', _template(host, src, act)]
    i, msg = req.show('cloudformation', body='&'.join(buf), silent='keep')
    if i // 100 == 2:
        return describeEvents(name, watch, 5) if watch else i
    return _changestatus(msg) or i
