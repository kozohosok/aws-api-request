'''
  AWS utility for CloudFormation stack
'''
import awsreq as req
import os
import sys
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote


def _resources(xml, name, wr, put):
    lim, xml = 3, ET.fromstring(xml)
    ns = dict(A=xml.tag[1:xml.tag.find('}')])
    for el in xml.findall('.//A:StackEvents/A:member', ns):
        key, stat, ts = [ el.find(f"A:{k}", ns).text
          for k in ('LogicalResourceId', 'ResourceStatus', 'Timestamp') ]
        if key != name:
            yield key, stat, ts
        elif '_CLEANUP_' not in stat:
            put(stat)
            wr(f"  ----  {ts}  {stat}")
            lim -= stat.endswith('_IN_PROGRESS'):
            if not lim:
                return
    put('lots_IN_PROGRESS')


def _events(name, stamp, buf):
    try:
        res = req.send('cloudformation',
          body=f"Action=DescribeStackEvents&StackName={name}")
    except req.HTTPError as e:
        print('\n'.join(buf) + '\nstatus ', e.code, e.msg)
        return 0, e.read().decode('ascii'), e.code // 100 == 4 and '!'
    wr, s = buf.append, f"status  {res.code} {res.msg} "
    wr(s + name.rjust(79 - len(s)))
    busy = 2 if buf[0][1] == '#' else 1
    fin, ok, body = [], True, res.read().decode('ascii')
    for key,stat,ts in _resources(body, name, wr, fin.append):
        hms = ts[11:19]
        if stat.endswith('_FAILED'):
            ok, _ = ok and len(fin), wr(f"{stat}  {hms}\t{key}")
        elif stamp.get(key, '') < ts:
            busy, stamp[key], _ = 1, ts, wr(f"    {hms}  {stat}\t{key}")
    if '</NextToken>' in body:
        wr('  ...')
    busy = fin[0].endswith('_IN_PROGRESS') and busy
    print(buf[0] if busy == 2 else '\n'.join(buf))
    return busy, body, ok and not fin[0].startswith('ROLLBACK')


def describeEvents(name, watch=0, delay=0, keep=False):
    print('_' * 79 if delay else f"StackName: {name}\n")
    time.sleep(delay)
    stamp, file = {}, sys.argv[0] + '.dat'
    busy, body, ok = _events(name, stamp, [])
    while busy and watch:
        time.sleep(watch * busy)
        busy, body, ok = _events(name, stamp, ['\n'[busy-1:] + '#' * 79])
    if ok == '!':
        return print(body)
    if watch:
        print('\nStackName:', name, '(done)\n' + '=' * 79)
    if keep:
        with open(file, 'w') as f:
            f.write(body)
    if ok:
        return 200
    if os.path.isfile(file):
        os.remove(file)
    sys.stderr.write(body)


def delete(name, confirm=True, watch=0):
    if confirm:
        print(end=f"StackName: {name}\nStackName? ", flush=True)
        if name != sys.stdin.readline().rstrip():
            return print('bye')
    else:
        print(f"StackName: {name}\n")
    i = req.show('cloudformation',
      body=f"Action=DeleteStack&StackName={name}", silent=True)
    return describeEvents(name, watch, 5) if watch and i // 100 == 2 else i


def exists(name):
    xml, ns = req.tree('cloudformation',
      body=f"Action=DescribeStacks&StackName={name}", silent=True)
    return ns and xml.find('.//A:Stacks/A:member/A:StackStatus', ns).text


def newer(file, ref):
    return os.stat(ref).st_mtime < os.stat(file).st_mtime


def escape(s):
    return quote(s, safe="!'()*-._~")


def _template(host, src, update):
    act = 'Update' if update else 'Create'
    if not host:
        with open(src, encoding='utf8') as f:
            return act, 'Body=' + escape(f.read())
    print('---------- upload template ----------')
    stamp = f"{src}.stamp"
    bucket, path = f"{host}/{src}".split('/', 1)  
    if not os.path.isfile(stamp) or newer(src, stamp):
        print('host:', host)
        with open(src, 'rb') as f:
            req.show('s3', bucket, f"/{path}", 'PUT', f.read(), silent=True)
        open(stamp, 'w').close()
    print('----------', act.lower(), 'stack ----------')
    return act, f"URL=https://{bucket}.s3.amazonaws.com/{path}"


def _parameter(params):
    if not isinstance(params, dict):
        return ''
    print('params:', params)
    return ''.join( f"&Parameters.member{i}.Parameter{x}"
      for i,k in enumerate(params)
      for x in ('Key=' + k, 'Value=' + escape(params[k])) )


def _reset(name, update):
    print('reset', update)
    delete(name, False)
    while exists(name):
        time.sleep(10)


def create(name, src, host='', update=False, confirm=True, watch=0, params=''):
    if update == -1:
        update = exists(name) or ''
        if update.endswith('_IN_PROGRESS'):
            return print(name, update, '...')
    if update == 'ROLLBACK_COMPLETE':
        update = _reset(name, update)
    elif update and confirm:
        print(end=f"StackName: {name} ({src} UP)\nStackName? ", flush=True)
        if name != sys.stdin.readline().rstrip():
            return print('bye')
    else:
        print(f"StackName: {name} ({src}{' UP' if update else ''})\n")
    act, conf = _template(host, src, update)
    i, msg = req.show('cloudformation', body='&'.join([
      f"Action={act}Stack&StackName={name}",
      'Capabilities.member.1=CAPABILITY_NAMED_IAM',
    ]) + _parameter(params) + f"&Template{conf}", silent='keep')
    if i // 100 == 2:
        return describeEvents(name, watch, 5) if watch else i
    if update and 'No update' in msg:
        i, msg = 200, 'status  200\tno update\n'
    print(msg)
    return i
