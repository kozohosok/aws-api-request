# aws-api-request

## awsreq.py
tiny Python3 script to send api request with AWS v4 signature (via proxy).

normal https response returns after authorized by AWS,
simple enough to utlize AWS services in your Python3 scripts.

AWS credentials to be supplied by csv file (accessKeys.csv) or environment variables (AWS_ACCESS_KEYS, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY).

default region could be specified by environment variable (AWS_DEFAULT_REGION).

proxy credentials to be supplied, if any, by environment variable (HTTPS_PROXY_B64) with Base64 encoded.

**parameters:**
- region

**methods:**
- `send(service, host='', path='/', method='POST', body='', header=None)`
- `show(*args, silent=False, xml=False, **karg)`
  -- show aws response in format
  * silent: True to show status only (suppress message body), or 'keep' to return message body
  * xml: True to indent in case of xml
- `tree(*args, silent=False, namespace='A', **karg)`
  -- parse aws response as xml and retrieve namespace
  * silent: True to return http error and suppress raise

**reference:**
  [Signature Version 4 signing process](https://docs.aws.amazon.com/general/latest/gr/signature-version-4.html)

## awsstack.py
tiny Python3 script to control (create,delete,watch) CloudFormation stack,
just as sample usage of awsreq.py.

**methods:**
- `exists(name)`
- `create(name, src, host='', update=False, confirm=True, watch=0, params='')`
  * host: S3 bucket to upload source
  * update: True to update instead of create, or -1 to update only if existent
  * confirm: False to skip confirmation on update
  * watch: <0 to show operation progress
  * params: dict to specify stack parameters
- `delete(name, confirm=True, watch=0)`
- `describeEvents(name, watch=0, delay=0, keep=False)`
  * watch: interval in seconds between repeating requests
  * delay: waiting period in seconds before initial request
  * keep: True to save successful result in local file

**reference:**
  [API reference of AWS CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/Welcome.html)
