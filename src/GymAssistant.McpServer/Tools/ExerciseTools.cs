using System.ComponentModel;
using GymAssistant.Client;
using ModelContextProtocol.Server;

namespace GymAssistant.McpServer.Tools;

[McpServerToolType]
public static class ExerciseTools
{
    [McpServerTool(Name = "list_exercises", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Личные упражнения пользователя с пагинацией: Id — личное упражнение, GlobalId — связь с общим шаблоном. TemplateRevision и TemplateOverrides описывают наследование метаданных; сохраняй их при последующей правке. Scope: exercises:read.")]
    public static Task<ExerciseViewModelPaged> ListExercisesAsync(
        GymClient client,
        CancellationToken ct,
        [Description("Offset для пагинации (0 по умолчанию)")] int offset = 0,
        [Description("Limit (по умолчанию 200)")] int limit = 200)
        => client.GetUserExercisesAsync(offset, limit, null, null, ct);

    [McpServerTool(Name = "list_default_exercises", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Общий каталог с поиском, метаданными, TemplateRevision и пагинацией. GlobalId обозначает шаблон, а не личное упражнение. Скрытые шаблоны исключены; includeHidden нужен для чтения ссылок истории. Scope не нужен: публичный справочник, backend не требует авторизации.")]
    public static Task<ExerciseDefaultViewModelPaged> ListDefaultExercisesAsync(
        GymClient client,
        CancellationToken ct,
        [Description("Offset для пагинации (0 по умолчанию)")] int offset = 0,
        [Description("Limit (по умолчанию 200)")] int limit = 200,
        [Description("Текстовый поиск по названию (null — без фильтра)")] string? search = null,
        [Description("Код мышцы для фильтрации (null — без фильтра)")] string? muscleCode = null,
        [Description("Код оборудования для фильтрации (null — без фильтра)")] string? equipmentCode = null,
        [Description("Включить скрытые шаблоны для чтения истории; по умолчанию false")] bool includeHidden = false)
        => client.GetDefaultExercisesAsync(offset, limit, search!, muscleCode!, equipmentCode!, includeHidden, ct);

    [McpServerTool(Name = "get_default_exercise", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Общий шаблон по globalId, включая скрытый: метаданные, TemplateRevision, isHidden и canonicalId без переназначения личных ID. Для чтения старых планов и истории. Scope не нужен: публичный справочник, backend не требует авторизации.")]
    public static Task<ExerciseDefaultViewModel> GetDefaultExerciseAsync(
        GymClient client,
        [Description("Реальный globalId шаблона упражнения")] Guid globalId,
        CancellationToken ct)
        => client.GetDefaultExerciseAsync(globalId, ct);

    [McpServerTool(Name = "list_exercise_catalogs", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Справочники для упражнений (Muscles + Equipments) одним вызовом — для построения фильтров и UI. Устаревший маршрут backend: предпочитай list_muscles и list_equipment. Scope не нужен: публичный справочник, backend не требует авторизации.")]
    public static Task<ExerciseCatalogsViewModel> ListExerciseCatalogsAsync(
        GymClient client,
        CancellationToken ct)
        => client.GetExerciseCatalogsAsync(ct);

    [McpServerTool(Name = "list_muscles", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Справочник мышц (ExerciseCatalogItemViewModel: Code, Name, ParentCode и пр.) для назначения нагрузок на упражнения. Scope не нужен: достаточно любого действующего PAT.")]
    public static Task<ICollection<ExerciseCatalogItemViewModel>> ListMusclesAsync(
        GymClient client,
        CancellationToken ct)
        => client.GetMusclesAsync(ct);

    [McpServerTool(Name = "list_equipment", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Справочник оборудования (ExerciseCatalogItemViewModel: Code, Name, ParentCode и пр.) для привязки к упражнениям. Scope не нужен: достаточно любого действующего PAT.")]
    public static Task<ICollection<ExerciseCatalogItemViewModel>> ListEquipmentAsync(
        GymClient client,
        CancellationToken ct)
        => client.GetEquipmentAsync(ct);

    [McpServerTool(Name = "create_exercise", Destructive = true),
     Description("Создать или обновить личное упражнение (Upsert по личному Id, не GlobalId шаблона). Перед правкой прочитай list_exercises и сохрани текущие TemplateRevision/TemplateOverrides. Для намеренной правки наследуемого поля добавь его camelCase-имя в TemplateOverrides; пустой список не сбрасывает прежние переопределения. TrackingType и LoadConvention не пересчитывают старые подходы. Общий каталог этим инструментом не редактируется. Scope: exercises:write.")]
    public static Task CreateExerciseAsync(
        GymClient client,
        [Description("Полный ExerciseViewModel с личным Id, именем, GymIds и метаданными. Для нового fork прочитай get_default_exercise, используй новый личный Id, GlobalId шаблона, его TemplateRevision и TemplateOverrides:[] (либо явные свои переопределения). Без TemplateRevision сервер защищает старые офлайн-режимы. Для существующего сохраняй идентичность и provenance из list_exercises.")]
        ExerciseViewModel body,
        CancellationToken ct)
        => client.SaveExerciseAsync(body, ct);

    [McpServerTool(Name = "delete_exercise", Destructive = true),
     Description("Удалить упражнение пользователя по id (soft delete на сервере). Scope: exercises:delete.")]
    public static Task DeleteExerciseAsync(
        GymClient client,
        [Description("Личный Id из list_exercises, не GlobalId общего шаблона")] Guid id,
        CancellationToken ct)
        => client.DeleteExerciseAsync(id, ct);
}
