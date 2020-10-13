# aws-api-request

## awsreq.py
tiny Python3 script to send api request with AWS v4 signature (via proxy),
simple enough to create your own utility scripts.

AWS credential to be supplied by csv file (accessKeys.csv) or environment variable (AWS_ACCESS_KEYS).

proxy credential to be supplied (if any) by environment variable (HTTPS_PROXY_B64) with Base64 encoded.

reference:
  [Signature Version 4 signing process](https://docs.aws.amazon.com/general/latest/gr/signature-version-4.html)

## awsstack.py
tiny Python3 script to control stack of AWS cloudformation,
just as sample usage of awsreq.py.
