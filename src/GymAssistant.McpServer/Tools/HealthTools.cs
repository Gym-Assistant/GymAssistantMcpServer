using System.ComponentModel;
using GymAssistant.Client;
using ModelContextProtocol.Server;

namespace GymAssistant.McpServer.Tools;

[McpServerToolType]
public static class HealthTools
{
    [McpServerTool(Name = "get_apple_health_daily", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Дневные итоги Apple Health владельца аккаунта за период до 31 дня. Scope: health:read. " +
                 "Ключи, единицы и агрегацию смотри в get_apple_health_metrics. " +
                 "ValueReadAt и ValueDeviceIds описывают свежесть и устройство каждой метрики; общий ReadAt не означает свежесть всех значений. null — нет данных, не ноль. " +
                 "Сегодняшний день может быть неполным; время получения не гарантирует полноту. Устройства не суммируются.")]
    public static Task<ICollection<HealthDailyRecord>> GetAppleHealthDailyAsync(
        GymClient client,
        [Description("Начальная локальная дата YYYY-MM-DD включительно")] string from,
        [Description("Конечная локальная дата YYYY-MM-DD включительно; период не более 31 дня")] string to,
        CancellationToken ct)
        => client.GetAppleHealthDailyAsync(from, to, ct);

    [McpServerTool(Name = "get_apple_health_metrics", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Каталог Apple Health: ключи, единицы и агрегация дневных показателей. Scope: health:read. " +
                 "Поддержка показателя не означает наличие измерений; значения и свежесть доступны через get_apple_health_daily.")]
    public static Task<HealthMetricCatalogDocument> GetAppleHealthMetricsAsync(GymClient client, CancellationToken ct)
        => client.GetAppleHealthMetricsAsync(ct);
}
