# aws-api-request

## awsreq.py
tiny Python3 script to send api request with AWS v4 signature (via proxy).

AWS credentials to be supplied by csv file (accessKeys.csv) or environment variable (AWS_ACCESS_KEYS).

reference:
  [Signature Version 4 signing process](https://docs.aws.amazon.com/ja_jp/general/latest/gr/signature-version-4.html)

## awsstack.py
tiny Python3 script to control stack of AWS cloudformation,
just as sample usage of awsreq.py.
