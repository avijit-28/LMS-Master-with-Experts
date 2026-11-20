using System;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using System.Web;
using System.Web.Mvc;
using LMS.Services;

namespace LMS.Controllers
{
    /// <summary>
    /// Real-time Server-Sent Events (SSE) Streaming Controller for AI Assistant.
    /// Hardened for Cloudflare Tunnel and IIS 10.0 pipeline:
    /// 1. Sets BufferOutput = false and Buffer = false to bypass IIS internal 4 KB accumulator.
    /// 2. Injects 'X-Accel-Buffering: no' to prevent Cloudflare edge proxies from buffering token chunks.
    /// 3. Injects 'Cache-Control: no-cache, no-transform' to avoid intermediate compression and cache delays.
    /// 4. Flushes every incoming chunk immediately over the live TCP socket.
    /// </summary>
    public class ChatBotStreamController : Controller
    {
        private static readonly HttpClient _aiClient = new HttpClient { Timeout = TimeSpan.FromSeconds(60) };

        // GET: /ChatBotStream/StreamMessage?prompt=...&courseId=1
        [HttpGet]
        public async Task StreamMessage(string prompt, int? courseId = null)
        {
            var response = HttpContext.Response;

            // 1. Disable IIS Output Buffering
            response.BufferOutput = false;
            response.Buffer = false;
            response.ContentType = "text/event-stream";
            response.Headers.Add("Cache-Control", "no-cache, no-transform");
            response.Headers.Add("X-Accel-Buffering", "no"); // Prevents Cloudflare / Nginx proxy buffering
            response.Headers.Add("Connection", "keep-alive");

            if (string.IsNullOrWhiteSpace(prompt))
            {
                response.Write("data: [DONE]\n\n");
                response.Flush();
                return;
            }

            try
            {
                var payloadObj = new
                {
                    query = prompt,
                    course_id = courseId,
                    user_id = User.Identity.IsAuthenticated ? User.Identity.Name : "guest"
                };

                var jsonPayload = Newtonsoft.Json.JsonConvert.SerializeObject(payloadObj);
                var requestPayload = new StringContent(jsonPayload, Encoding.UTF8, "application/json");

                var aiBaseUrl = EnvConfig.AiServiceBaseUrl?.TrimEnd('/') ?? "http://localhost:8000";
                var aiUrl = $"{aiBaseUrl}/api/v1/chat/stream";

                using (var upstreamRequest = new HttpRequestMessage(HttpMethod.Post, aiUrl))
                {
                    upstreamRequest.Content = requestPayload;
                    if (!string.IsNullOrEmpty(EnvConfig.AiServiceInternalApiKey))
                    {
                        upstreamRequest.Headers.Add("X-Internal-API-Key", EnvConfig.AiServiceInternalApiKey);
                    }

                    using (var upstreamResponse = await _aiClient.SendAsync(upstreamRequest, HttpCompletionOption.ResponseHeadersRead))
                    {
                        if (!upstreamResponse.IsSuccessStatusCode)
                        {
                            response.Write($"data: [ERROR: AI Service returned status {(int)upstreamResponse.StatusCode}]\n\n");
                            response.Flush();
                            return;
                        }

                        using (var stream = await upstreamResponse.Content.ReadAsStreamAsync())
                        using (var reader = new StreamReader(stream))
                        {
                            while (!reader.EndOfStream)
                            {
                                var line = await reader.ReadLineAsync();
                                if (line != null)
                                {
                                    response.Write($"{line}\n\n");
                                    response.Flush(); // Push immediately to Cloudflare and client browser
                                }
                            }
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                response.Write($"data: [ERROR: {ex.Message}]\n\n");
                response.Flush();
            }
        }
    }
}
