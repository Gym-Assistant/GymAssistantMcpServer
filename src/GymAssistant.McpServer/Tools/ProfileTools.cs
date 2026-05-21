using System.ComponentModel;
using GymAssistant.Client;
using ModelContextProtocol.Server;

namespace GymAssistant.McpServer.Tools;

[McpServerToolType]
public static class ProfileTools
{
    [McpServerTool(Name = "get_me", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Профиль текущего пользователя GymAssistant (id, username, имя, дата регистрации). Scope: profile:read.")]
    public static Task<UserViewModel> GetMeAsync(GymClient client, CancellationToken ct)
        => client.GetMeAsync(ct);

    [McpServerTool(Name = "get_user_settings", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Настройки пользователя (язык, единицы измерения, временная зона, день начала недели и пр.). Scope: profile:read.")]
    public static Task<UserSettingsViewModel> GetUserSettingsAsync(GymClient client, CancellationToken ct)
        => client.GetUserSettingsAsync(ct);

    [McpServerTool(Name = "update_user_settings", Destructive = true),
     Description("Обновить настройки пользователя (PUT, не PATCH — передавать целиком). Поля: DisplayName, Email, PhoneNumber, Language, TimeZoneId, UnitSystem, WeekStartsOn. Scope: profile:write.")]
    public static Task<UserSettingsViewModel> UpdateUserSettingsAsync(
        GymClient client,
        [Description("Полный объект настроек пользователя (UserSettingsViewModel). Сервер выполняет PUT — нужно передавать все поля.")]
        UserSettingsViewModel body,
        CancellationToken ct)
        => client.UpdateUserSettingsAsync(body, ct);

    [McpServerTool(Name = "get_active_plan", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Активный тренировочный план пользователя (PlanId, дата активации, индекс последней использованной недели). Scope: plans:read.")]
    public static Task<UserActivePlanViewModel> GetActivePlanAsync(GymClient client, CancellationToken ct)
        => client.GetActivePlanAsync(ct);

    [McpServerTool(Name = "set_active_plan", Destructive = true),
     Description("Установить активный план пользователя по его id (или передать null для сброса активного плана). Scope: plans:write.")]
    public static Task SetActivePlanAsync(
        GymClient client,
        [Description("ID плана, который сделать активным; null — сбросить активный план")]
        Guid? planId,
        CancellationToken ct)
        => client.SetActivePlanAsync(new SetActivePlanRequest { PlanId = planId }, ct);
}
