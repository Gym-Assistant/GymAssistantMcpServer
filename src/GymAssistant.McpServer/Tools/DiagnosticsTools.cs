using System.ComponentModel;
using GymAssistant.McpServer.Infra;
using ModelContextProtocol.Server;

namespace GymAssistant.McpServer.Tools;

[McpServerToolType]
public static class DiagnosticsTools
{
    [McpServerTool(Name = "health_check", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Проверка соединения с backend GymAssistant (требует scope profile:read). Возвращает API URL, имя пользователя и подтверждение валидности PAT.")]
    public static async Task<object> HealthCheckAsync(
        GymClient client,
        EnvConfig config,
        CancellationToken ct)
    {
        var me = await client.GetMeAsync(ct);
        return new
        {
            ok = true,
            api = config.ApiUrl.ToString(),
            user = me.Username,
        };
    }
}
