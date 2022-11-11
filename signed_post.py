#!/usr/bin/python3
import sys
import argparse
import hmac
import http
import urllib
from urllib import parse
from http import client as httpclient

parser = argparse.ArgumentParser()
parser.add_argument('url')
parser.add_argument('secret')
args = parser.parse_args()

payload = sys.stdin.read().encode()

secret = args.secret.encode()
url = args.url

hmac_ = hmac.new(secret, payload, 'sha256')
digest= hmac_.hexdigest()

p = parse.urlparse(url)
Connection = httpclient.HTTPConnection if p.scheme == 'http' else http.client.HTTPSConnection 
params = parse.urlencode({'payload':payload, 'hmac': digest})
headers = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain"}
c = Connection(p.hostname, p.port)
try:
    c.request('POST', p.path, params, headers)
    r = c.getresponse()
    if r.status != 200:
        print(f"Failed: {r.status} {r.reason}\n{r.read().decode()}")
        sys.exit(2)
except Exception as e:
    print(f"Failed: {e}")
    sys.exit(1)

print(f"Successfully submitted job details to {url}")
