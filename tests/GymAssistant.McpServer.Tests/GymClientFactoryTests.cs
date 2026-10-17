using System.Net;
using System.Text;
using GymAssistant.McpServer.Infra;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace GymAssistant.McpServer.Tests;

public class GymClientFactoryTests
{
    [Theory]
    [InlineData("https://example.test/api", "https://example.test/api/auth/me")]
    [InlineData("https://example.test/api/", "https://example.test/api/auth/me")]
    [InlineData("https://example.test/", "https://example.test/api/auth/me")]
    [InlineData("https://example.test/gym/api", "https://example.test/gym/api/auth/me")]
    public async Task Health_request_uses_one_api_prefix_and_forwards_pat(string apiUrl, string expected)
    {
        var services = new ServiceCollection();
        var token = "gma_" + new string('a',40);
        services.AddSingleton(new EnvConfig(token,new Uri(apiUrl),"Warning"));
        services.AddGymClient();
        using var handler = new ProfileHandler();
        services.AddHttpClient("Client").ConfigurePrimaryHttpMessageHandler(() => handler);
        using var provider = services.BuildServiceProvider();
        var client = provider.GetRequiredService<GymAssistant.Client.Client>();
        var me = await client.GetMeAsync();
        Assert.Equal("factory-fixture",me.Username);
        Assert.Equal(expected,handler.Url);
        Assert.Equal("Bearer " + token,handler.Authorization);
    }

    private sealed class ProfileHandler : HttpMessageHandler
    {
        public string? Url { get; private set; }
        public string? Authorization { get; private set; }
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken ct)
        {
            Url = request.RequestUri?.ToString();
            Authorization = request.Headers.Authorization?.ToString();
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("{\"id\":\"11111111-1111-1111-1111-111111111111\",\"username\":\"factory-fixture\"}",Encoding.UTF8,"application/json")
            });
        }
    }
}
