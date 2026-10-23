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
try {
    set_time_limit(300);
    $pipes=[];
    $p=proc_open(['python3',$private.'/b07_http_worker.py','call'],[0=>['pipe','r'],1=>['pipe','w'],2=>['file','/dev/null','a']],$pipes);
    if (!is_resource($p)) throw new Exception();
    fwrite($pipes[0],json_encode($frame));fclose($pipes[0]);
    $out=stream_get_contents($pipes[1],32768);fclose($pipes[1]);$exit=proc_close($p);
    $reply=json_decode($out,true);
    if($exit!==0 || !is_array($reply) || !isset($reply['status'],$reply['headers'],$reply['body'])) throw new Exception();
    http_response_code($reply['status']);
    foreach($reply['headers'] as $h) header($h[0].': '.$h[1],$h[0]!=='Set-Cookie');
    echo $reply['body'];
} catch(Throwable $e) {fail_request(503,'SERVICE_RETRY');}
