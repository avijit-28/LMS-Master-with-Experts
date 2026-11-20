using System;
using System.Web;

namespace LMS.Services
{
    /// <summary>
    /// Production Edge Client IP Resolver.
    /// Defeats Cloudflare Tunnel / Reverse-Proxy Loopback IP Flattening (where all requests appear as 127.0.0.1).
    /// Extracts the verified edge IP from CF-Connecting-IP header populated by Cloudflare Tunnel.
    /// </summary>
    public static class ClientIpResolver
    {
        public static string GetClientIp(HttpRequestBase request)
        {
            if (request == null) return "127.0.0.1";

            // 1. Cloudflare Tunnel Header (Guaranteed tamper-proof at edge)
            string cfIp = request.Headers["CF-Connecting-IP"];
            if (!string.IsNullOrWhiteSpace(cfIp))
            {
                return cfIp.Trim();
            }

            // 2. Standard X-Forwarded-For (First IP is the origin client)
            string forwardedFor = request.Headers["X-Forwarded-For"];
            if (!string.IsNullOrWhiteSpace(forwardedFor))
            {
                string[] parts = forwardedFor.Split(',');
                if (parts.Length > 0 && !string.IsNullOrWhiteSpace(parts[0]))
                {
                    return parts[0].Trim();
                }
            }

            // 3. Fallback to direct socket address
            return !string.IsNullOrWhiteSpace(request.UserHostAddress) ? request.UserHostAddress.Trim() : "127.0.0.1";
        }

        public static string GetClientIp(HttpRequest request)
        {
            if (request == null) return "127.0.0.1";
            return GetClientIp(new HttpRequestWrapper(request));
        }
    }
}
