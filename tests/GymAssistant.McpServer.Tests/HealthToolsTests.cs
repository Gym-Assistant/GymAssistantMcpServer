using System.Net;
using System.Text;
using GymAssistant.McpServer.Tools;
using Xunit;

namespace GymAssistant.McpServer.Tests;
public sealed class HealthToolsTests
{
    [Fact]
    public async Task Catalog_and_extended_values_are_forwarded_without_aggregation_or_losing_metadata()
    {
        using var handler = new HealthHandler();
        using var http = new HttpClient(handler);
        var client = new GymAssistant.Client.Client("https://example.test", http);
        var catalog = await HealthTools.GetAppleHealthMetricsAsync(client, default);
        Assert.Equal("hrvSDNN", Assert.Single(catalog.Metrics).Key);
        var daily = await HealthTools.GetAppleHealthDailyAsync(client, "2026-10-17", "2026-10-18", default);
        var day = Assert.Single(daily);
        Assert.Equal(55, day.Snapshot.Values["hrvSDNN"]);
        Assert.Null(day.Snapshot.Values["protein"]);
        Assert.True(day.Snapshot.ValueReadAt.ContainsKey("hrvSDNN"));
        Assert.True(day.Snapshot.ValueDeviceIds.ContainsKey("hrvSDNN"));
        Assert.Equal(2, handler.Calls.Count);
        Assert.EndsWith("/api/health/apple/metrics", handler.Calls[0]);
        Assert.Contains("from=2026-10-17", handler.Calls[1]);
    }
    private sealed class HealthHandler : HttpMessageHandler
    {
        public List<string> Calls { get; } = [];
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Assert.Equal(HttpMethod.Get, request.Method);
            Calls.Add(request.RequestUri!.ToString());
            var json = request.RequestUri.AbsolutePath.EndsWith("/metrics")
                ? """{"version":2,"metrics":[{"key":"hrvSDNN","source":"heart_rate_variability","label":"HRV","group":"recovery","unit":"ms","displayUnit":"мс","aggregation":"average","minimum":0,"maximum":2000,"minimumIOS":"11.0"}]}"""
                : """[{"snapshot":{"day":"2026-10-18","timeZone":"Asia/Krasnoyarsk","readAt":"2026-10-18T10:00:00Z","values":{"hrvSDNN":55,"protein":null},"valueReadAt":{"hrvSDNN":"2026-10-18T09:00:00Z"},"valueDeviceIds":{"hrvSDNN":"11111111-1111-1111-1111-111111111111"}},"deviceId":"11111111-1111-1111-1111-111111111111","receivedAt":"2026-10-18T10:01:00Z"}]""";
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(json, Encoding.UTF8, "application/json") });
        }
    }
}
