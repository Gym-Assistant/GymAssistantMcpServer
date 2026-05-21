using System.Net.Http.Headers;

namespace GymAssistant.McpServer.Infra;

public sealed class ApiTokenHandler : DelegatingHandler
{
    private readonly AuthenticationHeaderValue _header;

    public ApiTokenHandler(EnvConfig config)
    {
        _header = new AuthenticationHeaderValue("Bearer", config.ApiToken);
    }

    protected override Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        request.Headers.Authorization = _header;
        return base.SendAsync(request, cancellationToken);
    }
}
