# aws-api-request

## awsreq.py
tiny Python3 script to send api request with AWS v4 signature (via proxy).

normal https response returns after authorized by AWS,
simple enough to utlize AWS services in your tools.

AWS credentials to be supplied by csv file (accessKeys.csv) or environment variable (AWS_ACCESS_KEYS).

proxy credentials to be supplied (if any) by environment variable (HTTPS_PROXY_B64) with Base64 encoded.

reference:
  [Signature Version 4 signing process](https://docs.aws.amazon.com/general/latest/gr/signature-version-4.html)

methods:
- send(service, host='', path='/', method='POST', body='', header=None)
- show(*args, silent=False, xml=False, **karg)  show aws response in format
- tree(*args, silent=False, namespace='A', **karg)  parse aws response as xml

## awsstack.py
tiny Python3 script to control (create,delete,watch) CloudFormation stack,
just as sample usage of awsreq.py.

reference:
  [API reference of AWS CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/Welcome.html)

methods:
- exists(name)
- create(name, src, host='', update=False, confirm=True, watch=0, params='')
- delete(name, confirm=True, watch=0)
- describeEvents(name, watch=0, delay=0, keep=False)
