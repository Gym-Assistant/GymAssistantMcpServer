using System.ComponentModel;
using GymAssistant.Client;
using ModelContextProtocol.Server;

namespace GymAssistant.McpServer.Tools;

[McpServerToolType]
public static class HealthTools
{
    [McpServerTool(Name = "get_apple_health_daily", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Дневные итоги Apple Health владельца аккаунта за период до 31 дня. Scope: health:read. " +
                 "Шаги — количество; сон — минуты; съеденная, активная и базовая энергия — ккал; БЖУ — граммы; вес — кг. " +
                 "Возвращает часовой пояс, время чтения iPhone и получения сервером. null — нет данных, не ноль. " +
                 "Сегодняшний день может быть неполным; время получения не гарантирует полноту. Устройства не суммируются.")]
    public static Task<ICollection<HealthDailyRecord>> GetAppleHealthDailyAsync(
        GymClient client,
        [Description("Начальная локальная дата YYYY-MM-DD включительно")] string from,
        [Description("Конечная локальная дата YYYY-MM-DD включительно; период не более 31 дня")] string to,
        CancellationToken ct)
        => client.GetAppleHealthDailyAsync(from, to, ct);
}
