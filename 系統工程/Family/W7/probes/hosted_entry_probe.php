<?php
// B04 temporary synthetic endpoint. Build replaces these two placeholders.
$principals = json_decode('__PRINCIPALS_JSON__', true);
$run = '__RUN_ID__';
header('Content-Type: application/json');
header('Cache-Control: no-store');
umask(0077);
function respond($code, $value) {
    http_response_code($code);
    echo json_encode($value);
    exit;
}
function reject($code, $error) { respond($code, ['error'=>$error]); }
$auth = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
if (!str_starts_with($auth, 'Bearer ') || strlen($auth) > 520) reject(401, 'AUTH_REQUIRED');
$digest = hash('sha256', substr($auth, 7));
$principal = null;
foreach ($principals as $expected=>$identity) {
    if (hash_equals($expected, $digest)) $principal=$identity;
}
if ($principal === null) reject(401, 'AUTH_REQUIRED');
if ($_SERVER['REQUEST_METHOD'] !== 'POST') reject(405, 'POST_REQUIRED');
if ((int)($_SERVER['CONTENT_LENGTH'] ?? 0) > 8192) reject(413, 'BODY_TOO_LARGE');
$raw = file_get_contents('php://input', false, null, 0, 8193);
if (strlen($raw) > 8192) reject(413, 'BODY_TOO_LARGE');
$body = json_decode($raw, true);
if (!is_array($body) || !str_starts_with(trim($raw), '{')) reject(400, 'INVALID_JSON');
$op = $_GET['op'] ?? '';
$fields=['login'=>[], 'resume'=>[], 'logout'=>[], 'read'=>[], 'drain'=>[],
         'submit'=>['delta','request_id'], 'status'=>['request_id']];
if (!array_key_exists($op,$fields)) reject(404,'UNKNOWN_OPERATION');
$keys=array_keys($body); sort($keys);
if ($keys !== $fields[$op]) reject(400,'INVALID_FIELDS');
if ($principal['kind']==='action' && in_array($op,['login','logout'],true)) reject(403,'CHAT_LOGIN_REQUIRED');
if (in_array($op,['submit','status'],true) &&
    (!is_string($body['request_id']) || strlen($body['request_id'])<1 || strlen($body['request_id'])>128)) reject(400,'INVALID_REQUEST_ID');
if ($op==='submit' && (!is_int($body['delta']) || abs($body['delta'])>1000)) reject(400,'INVALID_DELTA');
$account=$principal['account'];
if (!str_starts_with($account,'synthetic-') || !preg_match('/^[0-9]+-[0-9]+$/',$run)) reject(500,'INVALID_PROBE_CONFIG');
$db=null;
try {
    // Exactly one unique probe state file, outside public_html.
    $db=new PDO('sqlite:'.dirname(__DIR__,2).'/.family-w7-probe-'.$run.'.sqlite');
    $db->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);
    $db->exec('PRAGMA busy_timeout=15000');
    $db->exec('PRAGMA synchronous=FULL');
    $db->exec('CREATE TABLE IF NOT EXISTS sessions(account TEXT PRIMARY KEY,issued INTEGER,expires INTEGER,generation TEXT)');
    $db->exec("CREATE TABLE IF NOT EXISTS jobs(seq INTEGER PRIMARY KEY,account TEXT,request_id TEXT,delta INTEGER,state TEXT DEFAULT 'QUEUED',result INTEGER,UNIQUE(account,request_id))");
    $db->exec('CREATE TABLE IF NOT EXISTS counters(account TEXT PRIMARY KEY,value INTEGER)');
    $db->exec('BEGIN IMMEDIATE');
    $query=function($sql,$args=[])use($db){$s=$db->prepare($sql);$s->execute($args);return $s;};
    $s=$query('SELECT issued,expires,generation FROM sessions WHERE account=?',[$account])->fetch(PDO::FETCH_ASSOC);
    $now=time();
    $valid=$s && $now >= $s['issued'] && $now < $s['expires'] && $s['expires']-$s['issued']===14400;
    if ($op==='login') {
        if (!$valid) {
            $query("UPDATE jobs SET state='CANCELLED' WHERE account=? AND state='QUEUED'",[$account]);
            $query('INSERT OR REPLACE INTO sessions VALUES(?,?,?,?)',[$account,$now,$now+14400,bin2hex(random_bytes(16))]);
        }
        $result=$query('SELECT account,issued,expires,generation FROM sessions WHERE account=?',[$account])->fetch(PDO::FETCH_ASSOC);
    } else {
        if (!$valid) {$db->exec('ROLLBACK');reject(401,'LOGIN_REQUIRED');}
        if ($op==='resume') $result=array_merge(['account'=>$account],$s);
        elseif ($op==='logout') {
            $query('DELETE FROM sessions WHERE account=?',[$account]);
            $query("UPDATE jobs SET state='CANCELLED' WHERE account=? AND state='QUEUED'",[$account]);
            $result=['logged_out'=>true];
        } else {
            if ($op==='submit') {
                $old=$query('SELECT delta FROM jobs WHERE account=? AND request_id=?',[$account,$body['request_id']])->fetch(PDO::FETCH_ASSOC);
                if ($old && (int)$old['delta']!==$body['delta']) {$db->exec('ROLLBACK');reject(409,'REQUEST_ID_COLLISION');}
                $query('INSERT OR IGNORE INTO jobs(account,request_id,delta) VALUES(?,?,?)',[$account,$body['request_id'],$body['delta']]);
            }
            if ($op==='drain') {
                $query('INSERT OR IGNORE INTO counters VALUES(?,0)',[$account]);
                $pending=$query("SELECT seq,delta FROM jobs WHERE account=? AND state='QUEUED' ORDER BY seq",[$account])->fetchAll(PDO::FETCH_ASSOC);
                foreach($pending as $job) {
                    $query('UPDATE counters SET value=value+? WHERE account=?',[$job['delta'],$account]);
                    $v=$query('SELECT value FROM counters WHERE account=?',[$account])->fetchColumn();
                    $query("UPDATE jobs SET state='DONE',result=? WHERE seq=?",[$v,$job['seq']]);
                }
            }
            if (in_array($op,['submit','status'],true)) {
                $result=$query('SELECT request_id,seq,state,result FROM jobs WHERE account=? AND request_id=?',[$account,$body['request_id']])->fetch(PDO::FETCH_ASSOC);
                if (!$result) {$db->exec('ROLLBACK');reject(404,'REQUEST_NOT_FOUND');}
            } else {
                $v=$query('SELECT value FROM counters WHERE account=?',[$account])->fetchColumn();
                $result=['account'=>$account,'value'=>$v===false?0:(int)$v,
                    'pending'=>(int)$query("SELECT count(*) FROM jobs WHERE account=? AND state='QUEUED'",[$account])->fetchColumn()];
            }
        }
    }
    $db->exec('COMMIT');
    respond(200,['scope'=>'SYNTHETIC_ONLY','result'=>$result]);
} catch(Throwable $e) {
    if ($db) {try {$db->exec('ROLLBACK');}catch(Throwable $ignored){}}
    reject(503,'RETRY_SAME_REQUEST_ID');
}
