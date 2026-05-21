using System.ComponentModel;
using GymAssistant.Client;
using ModelContextProtocol.Server;

namespace GymAssistant.McpServer.Tools;

[McpServerToolType]
public static class BodyTools
{
    [McpServerTool(Name = "list_body_characteristics", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Список характеристик тела пользователя (метрик: вес, талия, бицепс и т.п.) с пагинацией. Scope: body:read.")]
    public static Task<UserCharacteristicViewModelPaged> ListBodyCharacteristicsAsync(
        GymClient client,
        [Description("Offset для пагинации (0 по умолчанию)")] int offset,
        [Description("Limit (по умолчанию 100, рекомендуется не более 200)")] int limit,
        CancellationToken ct)
        => client.GetBodyCharacteristicsAsync(offset, limit, null, null, ct);

    [McpServerTool(Name = "list_body_characteristics_with_latest", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Список характеристик тела вместе с последним замером (stamp) для каждой на момент asOf. Scope: body:read.")]
    public static Task<ICollection<CharacteristicWithLatestViewModel>> ListBodyCharacteristicsWithLatestAsync(
        GymClient client,
        [Description("Момент, на который запрашивается последний замер по каждой характеристике (ISO 8601)")]
        DateTimeOffset asOf,
        CancellationToken ct)
        => client.GetBodyCharacteristicsWithLatestAsync(asOf, ct);

    [McpServerTool(Name = "list_default_body_characteristics", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Глобальный справочник стандартных характеристик тела (вес, рост, талия и пр.), которые можно подключить пользователю. Scope: body:read.")]
    public static Task<ICollection<BodyDefaultCharacteristicViewModel>> ListDefaultBodyCharacteristicsAsync(
        GymClient client,
        CancellationToken ct)
        => client.GetBodyDefaultCharacteristicsAsync(ct);

    [McpServerTool(Name = "get_body_characteristic", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Детальная информация о характеристике тела пользователя по её id (включая историю замеров). Scope: body:read.")]
    public static Task<CharacteristicDetailsViewModel> GetBodyCharacteristicAsync(
        GymClient client,
        [Description("ID характеристики тела пользователя")] Guid id,
        CancellationToken ct)
        => client.GetBodyCharacteristicDetailsAsync(id, ct);

    [McpServerTool(Name = "create_body_characteristic", Destructive = true),
     Description("Создать или обновить характеристику тела пользователя (Upsert по Id/GlobalId). Поля: Id, GlobalId, Name, Unit, IsActive, IsDual, IsDeleted и пр. Scope: body:write.")]
    public static Task<UserCharacteristicViewModel> CreateBodyCharacteristicAsync(
        GymClient client,
        [Description("Полный объект характеристики тела пользователя (UserCharacteristicViewModel). Сервер выполняет upsert.")]
        UserCharacteristicViewModel body,
        CancellationToken ct)
        => client.UpsertBodyCharacteristicAsync(body, ct);

    [McpServerTool(Name = "delete_body_characteristic", Destructive = true),
     Description("Удалить характеристику тела пользователя по id (soft delete на сервере). Scope: body:delete.")]
    public static Task DeleteBodyCharacteristicAsync(
        GymClient client,
        [Description("ID характеристики тела пользователя, которую нужно удалить")] Guid id,
        CancellationToken ct)
        => client.DeleteBodyCharacteristicAsync(id, ct);

    [McpServerTool(Name = "list_body_stamps", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("История замеров (stamps) пользователя по всем характеристикам тела с пагинацией. Scope: body:read.")]
    public static Task<CharacteristicStampViewModelPaged> ListBodyStampsAsync(
        GymClient client,
        [Description("Offset для пагинации (0 по умолчанию)")] int offset,
        [Description("Limit (по умолчанию 200)")] int limit,
        CancellationToken ct)
        => client.GetBodyStampsAsync(offset, limit, null, null, ct);

    [McpServerTool(Name = "create_body_stamp", Destructive = true),
     Description("Создать или обновить один или несколько замеров (stamps) по характеристикам тела пользователя (batch upsert). Каждый элемент содержит StampId, UserCharacteristicId или CharacteristicName, MeasuredAt, Value, Side, Unit и пр. Scope: body:write.")]
    public static Task CreateBodyStampAsync(
        GymClient client,
        [Description("Список замеров (UpsertStampItemViewModel) для batch-апсёрта. Каждый элемент — отдельный замер с MeasuredAt и Value.")]
        IEnumerable<UpsertStampItemViewModel> body,
        CancellationToken ct)
        => client.UpsertBodyStampsAsync(body, ct);

    [McpServerTool(Name = "delete_body_stamp", Destructive = true),
     Description("Удалить замер (stamp) пользователя по id. Scope: body:delete.")]
    public static Task DeleteBodyStampAsync(
        GymClient client,
        [Description("ID замера (stamp), который нужно удалить")] Guid id,
        CancellationToken ct)
        => client.DeleteBodyStampAsync(id, ct);
}
