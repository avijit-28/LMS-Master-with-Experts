# Cloudflare Zero-Cost Edge Defense & Turnstile Integration Guide

This guide documents the setup of **Cloudflare Free Tier Edge Protection** and **Cloudflare Tunnel (`cloudflared`)** for **EduPlatform LMS**. This architecture requires **$0 cloud expenditure** while providing enterprise-grade security, DDoS neutralization, Universal SSL, and bot mitigation.

---

## 1. Cloudflare Tunnel (`cloudflared`) Architecture

```
[ Student / Browser ]
        │ (HTTPS / Universal SSL)
        ▼
[ Cloudflare Global Edge ]
   ├── WAF Rate Limiting
   ├── Bot Fight Mode
   └── Cloudflare Turnstile
        │
        │ (Outbound Encrypted TLS Tunnel - Zero Open Inbound Router Ports)
        ▼
[ cloudflared Windows Service ]
        │ (Localhost Loopback http://127.0.0.1:80)
        ▼
[ Windows IIS 10.0 / MVC 5 ]
   ├── ClientIpResolver (CF-Connecting-IP extraction)
   └── ChatBotStreamController (X-Accel-Buffering: no)
```

### Why Cloudflare Tunnel?
1. **Zero Open Ports**: No router port forwarding (80/443) required. Shields home or institutional networks from direct-to-IP scanning and brute-force attacks.
2. **Dynamic IP Immunity**: Reconnects instantly across ISP IP changes.
3. **Loopback IP Flattening Fixed**: Requests arrive via tunnel with `CF-Connecting-IP` preserved and resolved by `ClientIpResolver`.

---

## 2. Step-by-Step Tunnel Provisioning

### Step 2.1: Authenticate cloudflared
In PowerShell:
```powershell
cloudflared tunnel login
```
A browser window opens. Select your free domain zone registered or proxied in Cloudflare.

### Step 2.2: Create the Tunnel
```powershell
cloudflared tunnel create eduplatform-lms
```
This generates:
- A unique Tunnel UUID (e.g., `d41d8cd9-8f00-4b20-8025-a4b7f43b679a`)
- A credentials JSON file in `%USERPROFILE%\.cloudflared\<UUID>.json`

### Step 2.3: Configure Ingress Rules
Update `infra/cloudflared-config.yml` with your Tunnel UUID and credentials file path:
```yaml
tunnel: d41d8cd9-8f00-4b20-8025-a4b7f43b679a
credentials-file: C:\Users\Username\.cloudflared\d41d8cd9-8f00-4b20-8025-a4b7f43b679a.json

ingress:
  - hostname: lms.yourdomain.com
    service: http://127.0.0.1:80
    originRequest:
      connectTimeout: 30s
      httpHostHeader: lms.yourdomain.com
      keepAliveConnections: 100
      keepAliveTimeout: 90s
  - service: http_status:404
```

### Step 2.4: Route DNS to Tunnel
```powershell
cloudflared tunnel route dns eduplatform-lms lms.yourdomain.com
```
This automatically creates a CNAME record at Cloudflare's edge pointing `lms.yourdomain.com` to `<UUID>.cfargotunnel.com`.

### Step 2.5: Register Auto-Starting Windows Service
To ensure the tunnel restarts automatically on system boot:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup-cloudflare-tunnel.ps1 -Action ServiceInstall
```

---

## 3. Cloudflare Turnstile Integration (Free Bot Deterrence)

Cloudflare Turnstile replaces annoying image CAPTCHAs with seamless, privacy-preserving cryptographic browser challenges.

### Step 3.1: Create Turnstile Widget in Cloudflare Dashboard
1. Go to **Cloudflare Dashboard** -> **Turnstile** -> **Add Widget**.
2. Widget Name: `EduPlatform Auth Gateway`.
3. Domain: `lms.yourdomain.com`.
4. Widget Mode: **Managed** (Invisible for normal users, challenges suspicious bots).
5. Copy your **Site Key** and **Secret Key**.

### Step 3.2: Add Client Widget to Views
In `Views/Account/Login.cshtml` or `Views/Account/ForgotPassword.cshtml`:
```html
<!-- Load Turnstile Script -->
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>

<!-- Render Widget Inside Form -->
<div class="cf-turnstile" data-sitekey="YOUR_TURNSTILE_SITE_KEY" data-theme="light"></div>
```

### Step 3.3: Server-Side Token Validation
When the user submits the form, Turnstile sends `Request.Form["cf-turnstile-response"]`.
Validate the token server-side:
```csharp
public static async Task<bool> VerifyTurnstileAsync(string token, string remoteIp)
{
    using (var client = new HttpClient())
    {
        var values = new Dictionary<string, string>
        {
            { "secret", ConfigurationManager.AppSettings["Cloudflare:TurnstileSecret"] },
            { "response", token },
            { "remoteip", remoteIp }
        };

        var content = new FormUrlEncodedContent(values);
        var response = await client.PostAsync("https://challenges.cloudflare.com/turnstile/v0/siteverify", content);
        var json = await response.Content.ReadAsStringAsync();
        return json.Contains("\"success\":true");
    }
}
```

---

## 4. Free Tier Edge Security Hardening Rules

Configure the following under **Security** -> **WAF** in Cloudflare Dashboard:

1. **Bot Fight Mode**:
   - Turn **ON** under *Security -> Bots*. Automatically challenges malicious scrapers and credential stuffers.
2. **Rate Limiting Rule (Free Tier allows 1 rule)**:
   - Target: `http.request.uri.path eq "/Account/Login"`
   - Condition: Requests per 10 seconds > 5 from same IP.
   - Action: **Managed Challenge**.
3. **SSL/TLS Encryption Mode**:
   - Set to **Full (Strict)** under *SSL/TLS -> Overview*.
4. **Always Use HTTPS**:
   - Enable under *SSL/TLS -> Edge Certificates*.
5. **Minimum TLS Version**:
   - Set to **TLS 1.2** or **TLS 1.3**.
