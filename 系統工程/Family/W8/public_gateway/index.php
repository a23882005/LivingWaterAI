<?php
// W8 official HTTPS gateway. Only invokes the vetted private Python router.
// Never logs HTTP body/cookies/authorization or reads a family DB directly.
declare(strict_types=1);
ini_set('display_errors','0');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: no-referrer');
function fail_service(int $code): void {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    echo '{"error":"SERVICE_RETRY"}';
    exit;
}
if (($_SERVER['HTTPS'] ?? '') !== 'on') fail_service(400);
if (($_SERVER['HTTP_HOST'] ?? '') !== 'www.happihelp.com') fail_service(403);
$method = $_SERVER['REQUEST_METHOD'] ?? '';
$path = $_SERVER['REQUEST_URI'] ?? '';
if (!in_array($method, ['GET','POST'],true) || !is_string($path)
    || strlen($path) > 10000 || !str_starts_with($path, '/family-connect')
    || preg_match('/[\r\n\x00]/', $path)) fail_service(400);
$body = file_get_contents('php://input', false, null, 0, 8193);
if (!is_string($body) || strlen($body) > 8192) fail_service(413);
$parent = dirname(dirname(__DIR__));
$script = $parent . '/.family-w8-app/Family/W8/cgi_request.py';
if (!is_file($script) || is_link($script) || !is_readable($script)) fail_service(503);
$allowed = [
    'host'=>'HTTP_HOST','origin'=>'HTTP_ORIGIN',
    'content-type'=>'CONTENT_TYPE','authorization'=>'HTTP_AUTHORIZATION',
    'cookie'=>'HTTP_COOKIE','x-family-csrf'=>'HTTP_X_FAMILY_CSRF',
    'accept'=>'HTTP_ACCEPT','user-agent'=>'HTTP_USER_AGENT'
];
$headers=[];
foreach($allowed as $key=>$serverKey) {
    $value=$_SERVER[$serverKey] ?? null;
    if(is_string($value) && strlen($value) <= 8192 && !preg_match('/[\r\n\x00]/', $value)) {
        $headers[$key]=$value;
    }
}
$request=json_encode([
    'method'=>$method,'path'=>$path,'headers'=>$headers,
    'body'=>base64_encode($body),
    'peer'=>substr($_SERVER['REMOTE_ADDR'] ?? '',0,80)
],JSON_UNESCAPED_SLASHES|JSON_INVALID_UTF8_SUBSTITUTE);
if(!is_string($request) || strlen($request)>16384) fail_service(413);
$desc=[0=>['pipe','r'],1=>['pipe','w'],2=>['pipe','w']];
$env=['PATH'=>'/usr/local/bin:/usr/bin:/bin','PYTHONDONTWRITEBYTECODE'=>'1'];
$proc=@proc_open(['python3',$script],$desc,$pipes,$parent,$env);
if(!is_resource($proc)) fail_service(503);
fwrite($pipes[0],$request);
fclose($pipes[0]);
// The Python router has a bounded response; cap output to avoid memory spikes.
$out=stream_get_contents($pipes[1],2097153);
fclose($pipes[1]);
// Suppress details that may contain provider responses or private paths.
stream_get_contents($pipes[2],4096);
fclose($pipes[2]);
$status=proc_close($proc);
if($status!==0 || !is_string($out) || strlen($out)>2097152) fail_service(503);
$response=json_decode($out,true);
if(!is_array($response) || !isset($response['status'],$response['headers'],$response['body'])
   || !is_int($response['status']) || $response['status']<100 || $response['status']>599
   || !is_array($response['headers']) || !is_string($response['body'])) fail_service(503);
$payload=base64_decode($response['body'],true);
if($payload===false) fail_service(503);
http_response_code($response['status']);
$allowHeaders=['content-type','cache-control','pragma','x-content-type-options',
    'referrer-policy','x-frame-options','content-security-policy','set-cookie',
    'location','www-authenticate','retry-after'];
foreach($response['headers'] as $header) {
    if(!is_array($header) || count($header)!==2 ||
       !is_string($header[0]) || !is_string($header[1])) continue;
    $key=strtolower($header[0]);
    if(!in_array($key,$allowHeaders,true) || preg_match('/[\r\n\x00]/',$header[1])) continue;
    header($header[0].': '.$header[1],false);
}
echo $payload;
