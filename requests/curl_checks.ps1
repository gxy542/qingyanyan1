# ============================================================================
# curl_checks.ps1 — 用 curl 走一遍任务三的关键链路（Windows PowerShell）
# 用法：先 docker compose up，再运行  .\requests\curl_checks.ps1
# 覆盖：注册 -> 登录 -> 当前用户 -> 错误密码(应401) -> 登出吊销 -> 401复验
# ============================================================================
$base = "http://localhost:8000/api/v1/auth"

# 1) 注册（若已存在会 409，属正常）
Write-Host "== 注册 new@test.edu =="
curl.exe -s -X POST "$base/register" -H "Content-Type: application/json" `
  -d '{"email":"new@test.edu","password":"Newpass!123"}'

# 2) 登录，提取令牌
Write-Host "`n== 登录 student =="
$login = curl.exe -s -X POST "$base/token" -H "Content-Type: application/json" `
  -d '{"email":"student@test.edu","password":"Student!123"}'
Write-Host $login
$token = ($login | ConvertFrom-Json).access_token

# 3) 当前用户（令牌有效）
Write-Host "`n== GET /me（有效令牌）=="
curl.exe -s "$base/me" -H "Authorization: Bearer $token"

# 4) 错误密码 -> 应 401
Write-Host "`n== 登录（错误密码，应401）=="
curl.exe -s -w "`nHTTP %{http_code}`n" -X POST "$base/token" -H "Content-Type: application/json" `
  -d '{"email":"student@test.edu","password":"WrongPass!"}'

# 5) 登出（吊销令牌）
Write-Host "`n== 登出 =="
curl.exe -s -o $null -w "HTTP %{http_code}`n" -X POST "$base/logout" -H "Authorization: Bearer $token"

# 6) 用已吊销令牌访问 -> 应 401
Write-Host "== 吊销后访问 /me（应401）=="
curl.exe -s -w "`nHTTP %{http_code}`n" "$base/me" -H "Authorization: Bearer $token"
