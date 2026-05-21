using System.Text.RegularExpressions;

namespace GymAssistant.McpServer.Infra;

public sealed record EnvConfig(string ApiToken, Uri ApiUrl, string LogLevel)
{
    private static readonly Regex TokenShape = new("^gma_[A-Za-z0-9_-]{40,80}$", RegexOptions.Compiled);
    private const string DefaultApiUrl = "https://gym-assistant.ru/api";
    private const string DefaultLogLevel = "Information";

    public static EnvConfig Build(Func<string, string?> read)
    {
        var token = read("GYM_API_TOKEN");
        if (string.IsNullOrWhiteSpace(token))
            throw new InvalidOperationException(
                "GYM_API_TOKEN is required. Set it to a Personal API Token (gma_...) issued via Telegram bot.");
        if (!TokenShape.IsMatch(token))
            throw new InvalidOperationException(
                $"GYM_API_TOKEN has invalid shape. Expected 'gma_' followed by 40-80 url-safe chars; got '{token[..Math.Min(token.Length, 12)]}...'.");

        var urlRaw = read("GYM_API_URL") ?? DefaultApiUrl;
        if (!Uri.TryCreate(urlRaw, UriKind.Absolute, out var url) ||
            (url.Scheme != Uri.UriSchemeHttp && url.Scheme != Uri.UriSchemeHttps))
            throw new InvalidOperationException($"GYM_API_URL is not a valid http(s) URL: '{urlRaw}'.");

        var logLevel = read("GYM_LOG_LEVEL") ?? DefaultLogLevel;
        return new EnvConfig(token, url, logLevel);
    }
}
