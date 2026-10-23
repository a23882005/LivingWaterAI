<?php
// B07 discovery-only bootstrap. No account store, credentials or worker access.
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: no-referrer');
function reply($status, $body) { http_response_code($status); echo json_encode($body, JSON_UNESCAPED_SLASHES); exit; }
if (($_SERVER['HTTPS'] ?? '') !== 'on') reply(400, ['error'=>'https_required']);
if (($_SERVER['HTTP_HOST'] ?? '') !== 'www.happihelp.com') reply(403, ['error'=>'invalid_host']);
if (isset($_SERVER['HTTP_ORIGIN']) && $_SERVER['HTTP_ORIGIN'] !== 'https://www.happihelp.com') reply(403, ['error'=>'invalid_origin']);
$uri = $_SERVER['REQUEST_URI'] ?? '';
if (strlen($uri)>2048 || strpos($uri, '?')!==false || strpos($uri, '%')!==false) reply(400, ['error'=>'invalid_request']);
$base='https://www.happihelp.com/family-connect';
$method=$_SERVER['REQUEST_METHOD'] ?? '';
if ($method==='GET' && $uri==='/family-connect/oauth/.well-known/oauth-authorization-server') {
    reply(200, ['issuer'=>$base.'/oauth', 'authorization_endpoint'=>$base.'/oauth/authorize',
        'token_endpoint'=>$base.'/oauth/token','response_types_supported'=>['code'],
        'grant_types_supported'=>['authorization_code','refresh_token'],
        'token_endpoint_auth_methods_supported'=>['none'],'code_challenge_methods_supported'=>['S256'],
        'scopes_supported'=>['family:session'],'authorization_response_iss_parameter_supported'=>true]);
}
if ($method==='GET' && $uri==='/family-connect/mcp/.well-known/oauth-protected-resource') {
    reply(200, ['resource'=>$base.'/mcp','authorization_servers'=>[$base.'/oauth'],
        'scopes_supported'=>['family:session'],'bearer_methods_supported'=>['header']]);
}
if ($uri==='/family-connect/mcp' && in_array($method,['GET','POST'],true)) {
    header('WWW-Authenticate: Bearer resource_metadata="'.$base.'/mcp/.well-known/oauth-protected-resource"');
    reply(401, ['error'=>'authorization_required']);
}
if (in_array($uri,['/family-connect/oauth/authorize','/family-connect/oauth/token'],true)) {
    header('Retry-After: 300'); reply(503, ['error'=>'temporarily_unavailable']);
}
reply(404, ['error'=>'not_found']);
