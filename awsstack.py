'''
  AWS utility for CloudFormation stack
'''
import awsreq as req
import os
import sys
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote


def _resources(body, name, wr, put):
    lim, xml = 3, ET.fromstring(body)
    ns = dict(A=xml.tag[1:xml.tag.find('}')])
    for el in xml.findall('.//A:StackEvents/A:member', ns):
        key, stat, ts = ( el.find(f"A:{k}", ns).text
          for k in ('LogicalResourceId', 'ResourceStatus', 'Timestamp') )
        if key != name:
            yield key, stat, ts, ts[11:19]
        elif '_CLEANUP_' not in stat:
            put(stat)
            wr(f"  ----  {ts}  {stat}")
            lim -= stat.endswith('_IN_PROGRESS')
            if not lim:
                break
    else:
        put('lots_IN_PROGRESS')
    if xml.find('.//A:NextToken', ns):
        wr('  ...')


def _events(name, stamp, buf):
    try:
        res = req.send('cloudformation',
          body=f"Action=DescribeStackEvents&StackName={name}")
    except req.HTTPError as e:
        print('\n'.join(buf) + '\nstatus ', e.code, e.msg)
        return 0, e.read().decode('ascii'), e.code // 100 == 4 and '!'
    ok, wr, s = True, buf.append, f"status  {res.code} {res.msg} "
    wr(s + name.rjust(79 - len(s)))
    fin, busy, body = [], buf[0][1] == '#', res.read().decode('ascii')
    for key,stat,ts,hms in _resources(body, name, wr, fin.append):
        if stat.endswith('_FAILED'):
            ok, _ = ok and len(fin), wr(f"{stat}  {hms}\t{key}")
        elif stamp.get(key, '') < ts:
            busy, stamp[key], _ = 0, ts, wr(f"    {hms}  {stat}\t{key}")
    busy = fin[0].endswith('_IN_PROGRESS') and busy + 1
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
        print(f"\nStackName: {name} (done)\n" + '=' * 79)
    if keep:
        with open(file, 'w') as f:
            f.write(body)
    if ok:
        return 200
    if os.path.isfile(file):
        os.remove(file)
    sys.stderr.write(body)


def showStatusReason(name, status_key='FAILED'):
    print(f"StackName: {name}\n")
    lim, stamp = 3, {}
    xml, ns = req.tree('cloudformation',
      body=f"Action=DescribeStackEvents&StackName={name}", silent=True)
    for el in xml.findall('.//A:StackEvents/A:member', ns) if ns else []:
        key, stat, ts = ( el.find(f"A:{k}", ns).text
          for k in ('LogicalResourceId', 'ResourceStatus', 'Timestamp') )
        if key == name:
            print(f"  ----  {ts}  {stat}")
            lim -= stat.endswith('_IN_PROGRESS')
            if not lim:
                return
        elif status_key in stat and stamp.setdefault(key, ts) == ts:
            s = el.findtext('A:ResourceStatusReason', '', ns)
            if s:
                print(f"{stat}  {ts[11:19]}\t{key}\n{s}\n")


def _input(s):
    print(end=s, flush=True)
    return input()


def delete(name, confirm=True, watch=0):
    if not confirm:
        print(f"StackName: {name}\n")
    elif name != _input(f"StackName: {name}\nStackName? "):
        return print('bye')
    i = req.show('cloudformation',
      body=f"Action=DeleteStack&StackName={name}", silent=True)
    return describeEvents(name, watch, 5) if watch and i // 100 == 2 else i


def exists(name):
    xml, ns = req.tree('cloudformation',
      body=f"Action=DescribeStacks&StackName={name}", silent='any')
    return ns and xml.find('.//A:Stacks/A:member/A:StackStatus', ns).text


def newer(file, ref):
    return os.stat(ref).st_mtime < os.stat(file).st_mtime


def escape(s):
    return quote(s, safe="!'()*-._~")


def _template(host, src, act):
    if not host:
        with open(src, encoding='utf8') as f:
            return 'TemplateBody=' + escape(f.read())
    print('---------- upload template ----------')
    stamp = f"{src}.stamp"
    bucket, path = f"{host}/{src}".split('/', 1)
    if not os.path.isfile(stamp) or newer(src, stamp):
        print('host:', host)
        with open(src, 'rb') as f:
            req.show('s3', bucket, f"/{path}", 'PUT', f.read(), silent=True)
        open(stamp, 'w').close()
    print('----------', act.lower(), 'stack ----------')
    return f"TemplateURL=https://{bucket}.s3.amazonaws.com/{path}"


def _parameter(params):
    if not isinstance(params, dict):
        return ''
    print('params:', params)
    return ''.join( f"&Parameters.member{i}.Parameter{x}"
      for i,k in enumerate(params)
      for x in ('Key=' + k, 'Value=' + escape(params[k])) )


def _action(name, status):
    if status == -1:
        status = exists(name) or ''
        if status.endswith('_IN_PROGRESS'):
            return None, print(name, status, '...')
    if status == 'ROLLBACK_COMPLETE':
        print('reset', status)
        delete(name, False)
        while exists(name):
            time.sleep(10)
    elif status:
        return ' UP', 'Update'
    return '', 'Create'


def create(name, src, host='', update=False, confirm=True, watch=0, params=''):
    update, act = _action(name, update)
    if not act:
        return
    if not update or not confirm:
        print(f"StackName: {name} ({src}{update})\n")
    elif name != _input(f"StackName: {name} ({src} UP)\nStackName? "):
        return print('bye')
    buf = [f"Action={act}Stack&StackName={name}" + _parameter(params),
      'Capabilities.member.1=CAPABILITY_NAMED_IAM', _template(host, src, act)]
    i, msg = req.show('cloudformation', body='&'.join(buf), silent='keep')
    if i // 100 == 2:
        return describeEvents(name, watch, 5) if watch else i
    if update and 'No update' in msg:
        i, msg = 204, 'status  204\tno update\n'
    print(msg)
    return i
