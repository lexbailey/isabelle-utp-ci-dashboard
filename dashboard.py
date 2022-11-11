#!/usr/bin/env python3
import json
import flask
import hmac

app = flask.Flask(__name__, template_folder='html')

config = json.load(open('config.json'))
host=config.get('host', 'localhost')
port=config.get('port', 8080)

hmac_secret = config.get('secret').encode()

internal_url_base = f'http://{host}:{port}'
url_base = config.get('ext_url', internal_url_base)

print(f'Listening via {internal_url_base}')
print(f'Accesible via {url_base}')

class DataError(Exception):
    pass

def handle_log_submission(data):
    try:
        j = json.loads(data)
    except Exception as e:
        raise DataError("Invalid json")
    date = j.get('date')
    ref = j.get('ref')
    result = j.get('result')
    if date is None or ref is None or result is None:
        raise DataError("Missing fields")
    

@app.route('/')
def root():
   return flask.render_template('index.html')

@app.route('/submit_job_log', methods=['POST'])
def log():
    if hmac_secret is None:
        return ("the job submission token is not set on this server", 403)
    f = flask.request.form
    payload = f.get('payload').encode()
    if payload is None:
        return ("payload missing", 400)
    provided_hmac = f.get('hmac')
    if provided_hmac is None:
        return ("hmac missing", 400)
    hmac_ = hmac.new(hmac_secret, payload, 'sha256')
    expected_hmac = hmac_.hexdigest()
    if provided_hmac != expected_hmac:
        return ("Message authentication code is incorrect", 403)
    data = payload.decode('utf-8')
    try:
        handle_log_submission(data)
    except DataError as e:
        return (f"Error in submission data: {e}", 400)
    except Exception as e:
        return ("Unknown error", 500)
    return "success"

if __name__ == '__main__':
    app.run(host=host, port=port)
