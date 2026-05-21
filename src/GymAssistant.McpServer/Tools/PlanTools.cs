using System.ComponentModel;
using GymAssistant.Client;
using ModelContextProtocol.Server;

namespace GymAssistant.McpServer.Tools;

[McpServerToolType]
public static class PlanTools
{
    [McpServerTool(Name = "list_plans", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Список тренировочных планов пользователя с пагинацией (его персональные планы, форки и опубликованные). Scope: plans:read.")]
    public static Task<PlanViewModelPaged> ListPlansAsync(
        GymClient client,
        CancellationToken ct,
        [Description("Offset для пагинации (0 по умолчанию)")] int offset = 0,
        [Description("Limit (по умолчанию 50)")] int limit = 50)
        => client.GetPlansAsync(offset, limit, null, null, ct);

    [McpServerTool(Name = "get_plan", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Получить тренировочный план по id со всеми упражнениями (Exercises) и шаблонами тренировок (Templates). Scope: plans:read.")]
    public static Task<PlanViewModel> GetPlanAsync(
        GymClient client,
        [Description("ID плана")] Guid id,
        CancellationToken ct)
        => client.GetPlanByIdAsync(id, ct);

    [McpServerTool(Name = "create_plan", Destructive = true),
     Description("Создать или обновить тренировочный план (Save по Id). Передаётся полный PlanViewModel: Name, Description, RestDefaults, Exercises, Templates и пр. Scope: plans:write.")]
    public static Task CreatePlanAsync(
        GymClient client,
        [Description("Полный объект плана (PlanViewModel). Сервер выполняет upsert по Id, увеличивая Revision.")]
        PlanViewModel body,
        CancellationToken ct)
        => client.SavePlanAsync(body, ct);

    [McpServerTool(Name = "delete_plan", Destructive = true),
     Description("Удалить тренировочный план по id (soft delete на сервере). Scope: plans:delete.")]
    public static Task DeletePlanAsync(
        GymClient client,
        [Description("ID плана, который нужно удалить")] Guid id,
        CancellationToken ct)
        => client.DeletePlanAsync(id, ct);

    [McpServerTool(Name = "list_plan_catalog", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Каталог опубликованных тренировочных планов (доступных для форка) с пагинацией и текстовым поиском. Scope: plans:read.")]
    public static Task<PlanViewModelPaged> ListPlanCatalogAsync(
        GymClient client,
        CancellationToken ct,
        [Description("Offset для пагинации (0 по умолчанию)")] int offset = 0,
        [Description("Limit (по умолчанию 50)")] int limit = 50,
        [Description("Текстовый поиск по названию плана (null — без фильтра)")] string? search = null)
        => client.GetPlanCatalogAsync(offset, limit, search!, ct);

    [McpServerTool(Name = "get_plan_from_catalog", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Получить опубликованный план из каталога по его id (без форка — только просмотр). Scope: plans:read.")]
    public static Task<PlanViewModel> GetPlanFromCatalogAsync(
        GymClient client,
        [Description("ID плана в каталоге")] Guid id,
        CancellationToken ct)
        => client.GetCatalogPlanByIdAsync(id, ct);

    [McpServerTool(Name = "fork_plan", Destructive = true),
     Description("Сделать форк опубликованного плана из каталога — создаётся собственная копия пользователя со ссылкой ForkedFromPlanId/ForkedFromRevision. Scope: plans:write.")]
    public static Task<PlanViewModel> ForkPlanAsync(
        GymClient client,
        [Description("ID плана в каталоге, который нужно форкнуть")] Guid id,
        CancellationToken ct)
        => client.ForkPlanAsync(id, ct);

    [McpServerTool(Name = "publish_plan", Destructive = true),
     Description("Опубликовать собственный план в каталог (IsPublished = true). После публикации план становится доступен другим пользователям для форка. Scope: plans:write.")]
    public static Task PublishPlanAsync(
        GymClient client,
        [Description("ID плана, который нужно опубликовать")] Guid id,
        CancellationToken ct)
        => client.PublishPlanAsync(id, ct);

    [McpServerTool(Name = "unpublish_plan", Destructive = true),
     Description("Снять план с публикации в каталоге (IsPublished = false). Существующие форки сохраняются. Scope: plans:write.")]
    public static Task UnpublishPlanAsync(
        GymClient client,
        [Description("ID плана, который нужно снять с публикации")] Guid id,
        CancellationToken ct)
        => client.UnpublishPlanAsync(id, ct);

    [McpServerTool(Name = "check_plan_updates", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Проверить наличие обновлений для форка плана — HTTP 200, если у исходного плана появилась новая ревизия (тело клиент не возвращает). Scope: plans:read.")]
    public static Task CheckPlanUpdatesAsync(
        GymClient client,
        [Description("ID собственного форкнутого плана, для которого проверяются обновления")] Guid id,
        CancellationToken ct)
        => client.CheckPlanUpdatesAsync(id, ct);

    [McpServerTool(Name = "pull_plan_updates", Destructive = true),
     Description("Подтянуть обновления исходного плана в форк (синхронизировать с актуальной ревизией ForkedFromPlanId). Scope: plans:write.")]
    public static Task PullPlanUpdatesAsync(
        GymClient client,
        [Description("ID собственного форкнутого плана, в который нужно подтянуть обновления")] Guid id,
        CancellationToken ct)
        => client.PullPlanUpdatesAsync(id, ct);

    [McpServerTool(Name = "detach_plan", Destructive = true),
     Description("Отвязать форк от исходного плана (сбрасывает ForkedFromPlanId/ForkedFromRevision) — после этого обновления подтягиваться не будут. Scope: plans:write.")]
    public static Task DetachPlanAsync(
        GymClient client,
        [Description("ID собственного форкнутого плана, который нужно отвязать от исходника")] Guid id,
        CancellationToken ct)
        => client.DetachPlanAsync(id, ct);
}
