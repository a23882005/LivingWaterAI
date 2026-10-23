<?php
// Isolated B07 acceptance gateway. Private directory is bound by deployment.
// Production enrollment/OAuth publication is a separately tracked B07 step.
umask(0077);
header('Cache-Control: no-store');
header('Content-Type: application/json; charset=utf-8');
function fail_request($status,$code) {http_response_code($status);echo json_encode(['error'=>$code]);exit;}
$private=dirname(__DIR__,2).'/.family-b07-http-__RUN_ID__';
$config=json_decode(@file_get_contents($private.'/gateway.json'),true);
if (!is_array($config)) fail_request(503,'SERVICE_RETRY');
$testkey=$_SERVER['HTTP_X_FAMILY_TEST_KEY']??'';
if (strlen($testkey)>128 || !hash_equals($config['probe_key_hash'],hash('sha256',$testkey))) fail_request(401,'TEST_ACCESS_REQUIRED');
if (($_SERVER['HTTPS']??'')!=='on' && ($_SERVER['REQUEST_SCHEME']??'')!=='https') fail_request(400,'HTTPS_REQUIRED');
if (($_SERVER['QUERY_STRING']??'')!=='') fail_request(400,'QUERY_NOT_ALLOWED');
if ((int)($_SERVER['CONTENT_LENGTH']??0)>8192) fail_request(413,'BODY_TOO_LARGE');
$raw=file_get_contents('php://input',false,null,0,8193);
if (strlen($raw)>8192) fail_request(413,'BODY_TOO_LARGE');
$headers=['Host'=>$_SERVER['HTTP_HOST']??''];
foreach (['Origin'=>'HTTP_ORIGIN','Cookie'=>'HTTP_COOKIE','Content-Type'=>'CONTENT_TYPE','X-Family-CSRF'=>'HTTP_X_FAMILY_CSRF'] as $name=>$serverkey) {
    if(isset($_SERVER[$serverkey])) $headers[$name]=$_SERVER[$serverkey];
}
$frame=['method'=>$_SERVER['REQUEST_METHOD'],'path'=>($_SERVER['PATH_INFO']??'')?:'/',
    'headers'=>$headers,'body'=>$raw,'peer'=>$_SERVER['REMOTE_ADDR']??''];
function send_reply($reply) {
    if (!is_array($reply) || !isset($reply['status'],$reply['headers'],$reply['body'])) fail_request(503,'SERVICE_RETRY');
    http_response_code($reply['status']);
    foreach($reply['headers'] as $h) header($h[0].': '.$h[1],$h[0]!=='Set-Cookie');
    echo $reply['body'];exit;
}
$path=($_SERVER['PATH_INFO']??'')?:'/';
$jobs=$private.'/jobs';
if (preg_match('~^/_result/([a-f0-9]{48})$~D',$path,$match)) {
    if ($_SERVER['REQUEST_METHOD']!=='GET') fail_request(405,'METHOD_NOT_ALLOWED');
    $id=$match[1];$result=$jobs.'/'.$id.'.result.json';
    if (is_file($result)) send_reply(json_decode(file_get_contents($result),true));
    if (!is_file($jobs.'/'.$id.'.request.json')) fail_request(404,'NOT_FOUND');
    http_response_code(202);echo json_encode(['pending'=>$id]);exit;
}
try {
    if (!is_dir($jobs) && !mkdir($jobs,0700)) throw new Exception();
    if (count(glob($jobs.'/*.request.json'))>=32) fail_request(429,'TRY_LATER');
    $id=bin2hex(random_bytes(24));
    $request=$jobs.'/'.$id.'.request.json';
    if (file_put_contents($request,json_encode($frame),LOCK_EX)===false) throw new Exception();
    chmod($request,0600);
    $command='nohup python3 '.escapeshellarg($private.'/b07_http_worker.py').' job '.escapeshellarg($id).' </dev/null >/dev/null 2>&1 &';
    $p=proc_open(['/bin/sh','-c',$command],[0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes);
    if (!is_resource($p) || proc_close($p)!==0) throw new Exception();
    http_response_code(202);echo json_encode(['pending'=>$id]);
} catch(Throwable $e) {fail_request(503,'SERVICE_RETRY');}
