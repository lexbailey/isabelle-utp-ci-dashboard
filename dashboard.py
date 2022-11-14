#!/usr/bin/env python3
import json
import flask
import hmac
import sqlite3
import yaml

app = flask.Flask(__name__, template_folder='html')

config = json.load(open('config.json'))
host=config.get('host', 'localhost')
port=config.get('port', 8080)

hmac_secret = config.get('secret').encode()

internal_url_base = f'http://{host}:{port}'
url_base = config.get('ext_url', internal_url_base)
db_name = config.get('db', 'build_data.db')

def get_db():
    global db_name
    db = sqlite3.connect(db_name)
    return db

def init_db():
    db = get_db()
    cur = db.cursor()
    cur.execute('create table if not exists builds (id integer primary key autoincrement, reponame text, datetime text, result integer, config blob, builder_version text, isabelle_version text)')
    cur.close()
    cur = None
    db.commit()

init_db()

print(f'Listening via {internal_url_base}')
print(f'Accesible via {url_base}')

def build_details(yaml_text):
    yobj = yaml.safe_load(yaml_text)
    version = 'unknown_version'
    isa_ver = 'unknown_version'
    if isinstance(yobj, dict):
        for name, job in yobj.get('jobs', {}).items():
            for step in job.get('steps', []):
                uses = step.get('uses', '')
                if 'isabelle-theory-build-github-action' in uses:
                    try:
                        version = uses.split('@')[-1]
                    except:
                        version = 'unknown_version'
                    with_ = step.get('with', {})
                    isa_ver = with_.get('isabelle-version', 'unknown_version')
    return {
        'build_script_ver': version,
        'isabelle_ver': isa_ver,
    }

class DataError(Exception):
    pass

def insert_data(json):
    db = get_db()
    cur = db.cursor()
    extra = build_details(json.get('config', {}))
    json.update(extra)
    data = tuple(json.get(k,'?') for k in ['reponame', 'datetime', 'result', 'config', 'build_script_ver', 'isabelle_ver'])
    cur.execute('insert into builds (reponame, datetime, result, config, builder_version, isabelle_version) values (?,?,?,?,?,?)', data)
    cur.close()
    db.commit()

def handle_log_submission(data):
    try:
        j = json.loads(data)
    except Exception as e:
        raise DataError("Invalid json")
    date = j.get('datetime')
    ref = j.get('reponame')
    result = j.get('result')
    config = j.get('config')
    if date is None or ref is None or result is None or config is None:
        raise DataError("Missing fields")
    try:
        insert_data(j)
    except Exception as e:
        raise DataError("Unknown failure: " + str(e))
    
def result_text(result_id):
    return {
        0: 'Success',
        1: 'Fail',
    }.get(result_id, "Unknown")



app.jinja_env.globals.update(result_text=result_text)

def fetch_current_data():
    db = get_db()
    cur = db.cursor()
    cur.execute('select * from builds where (reponame, isabelle_version, datetime) in (select reponame, isabelle_version, max(datetime) over (partition by reponame, isabelle_version) as datetime from builds) order by datetime desc;')
    cols = [n[0] for n in cur.description]
    rows = cur.fetchall()
    return [{name:key for name,key in zip(cols, row)} for row in rows]

def fetch_current_data_for_version(v):
    db = get_db()
    cur = db.cursor()
    cur.execute('select * from builds where (reponame, isabelle_version, datetime) in (select reponame, isabelle_version, max(datetime) over (partition by reponame, isabelle_version) as datetime from builds) and isabelle_version is ? order by datetime desc;', (v,))
    cols = [n[0] for n in cur.description]
    rows = cur.fetchall()
    return [{name:key for name,key in zip(cols, row)} for row in rows]

def fetch_builds_for_repo(r):
    db = get_db()
    cur = db.cursor()
    cur.execute('select * from builds where reponame is ? order by datetime desc;', (r,))
    cols = [n[0] for n in cur.description]
    rows = cur.fetchall()
    return [{name:key for name,key in zip(cols, row)} for row in rows]

def fetch_builds_for_user(u):
    db = get_db()
    cur = db.cursor()
    cur.execute('select * from builds where (reponame, isabelle_version, datetime) in (select reponame, isabelle_version, max(datetime) over (partition by reponame, isabelle_version) as datetime from builds) and reponame like ? order by datetime desc;', (f'{u}%',))
    cols = [n[0] for n in cur.description]
    rows = cur.fetchall()
    return [{name:key for name,key in zip(cols, row)} for row in rows]

def fetch_builds_for_user_and_version(u, v):
    db = get_db()
    cur = db.cursor()
    cur.execute('select * from builds where (reponame, isabelle_version, datetime) in (select reponame, isabelle_version, max(datetime) over (partition by reponame, isabelle_version) as datetime from builds) and reponame like ? and isabelle_version is ? order by datetime desc;', (f'{u}%',v))
    cols = [n[0] for n in cur.description]
    rows = cur.fetchall()
    return [{name:key for name,key in zip(cols, row)} for row in rows]

def augment(data):
    for x in data:
        x['username'] = x.get('reponame','').split('/')[0]
    return data

@app.route('/')
def root():
    name = "Latest builds"
    data = augment(fetch_current_data())
    return flask.render_template('index.html', name=name, data=data)

@app.route('/by_version/<version>')
def by_version(version):
    name = f"Latest builds (filtered by isabelle version: {version})"
    data = augment(fetch_current_data_for_version(version))
    return flask.render_template('index.html', name=name, data=data)

@app.route('/repo/<repo>')
@app.route('/repo/<owner>/<repo>')
def by_repo(owner='', repo=''):
    if owner != '':
        repo = f'{owner}/{repo}'
    name = f"Build log for repo: {repo}"
    data = augment(fetch_builds_for_repo(repo))
    return flask.render_template('index.html', name=name, data=data)

@app.route('/user/<owner>')
def by_user(owner):
    name = f"Latest builds for repos by user: {owner}"
    data = augment(fetch_builds_for_user(owner))
    version_prefix = f'/by_user_and_version/{owner}/'
    return flask.render_template('index.html', name=name, data=data, version_prefix=version_prefix)

@app.route('/by_user_and_version/<owner>/<version>')
def by_user_and_version(owner, version):
    name = f"Latest builds for repos by user: {owner} for isabelle version: {version}"
    data = augment(fetch_builds_for_user_and_version(owner, version))
    return flask.render_template('index.html', name=name, data=data)

@app.route('/raw_recent_data')
def recent_raw():
    data = fetch_current_data()
    return json.dumps(data)

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
