using Microsoft.Extensions.DependencyInjection;

namespace GymAssistant.McpServer.Infra;

public static class GymClientFactory
{
    /// <summary>
    /// Регистрирует NSwag-сгенерированный <c>GymAssistant.Client.Client</c> и
    /// <see cref="ApiTokenHandler"/> со связкой через <c>IHttpClientFactory</c>.
    /// Базовый URL и токен берутся из <see cref="EnvConfig"/>; токен прокидывается
    /// в заголовок <c>Authorization</c> на каждый запрос.
    /// </summary>
    public static IServiceCollection AddGymClient(this IServiceCollection services)
    {
        services.AddTransient<ApiTokenHandler>();
        services
            .AddHttpClient<GymClient>((sp, http) =>
            {
                var cfg = sp.GetRequiredService<EnvConfig>();
                http.BaseAddress = cfg.ApiUrl;
                http.Timeout = TimeSpan.FromSeconds(30);
            })
            .AddTypedClient((http, sp) =>
            {
                var cfg = sp.GetRequiredService<EnvConfig>();
                // NSwag routes already include /api; accept the documented API-root URL
                // without adding that prefix twice.
                var backendUrl = cfg.ApiUrl.ToString().TrimEnd('/');
                if (backendUrl.EndsWith("/api", StringComparison.OrdinalIgnoreCase))
                    backendUrl = backendUrl[..^4];
                return new GymClient(backendUrl, http);
            })
            .AddHttpMessageHandler<ApiTokenHandler>();
        return services;
    }
}
