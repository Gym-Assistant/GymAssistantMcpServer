using System.ComponentModel;
using GymAssistant.Client;
using ModelContextProtocol.Server;

namespace GymAssistant.McpServer.Tools;

[McpServerToolType]
public static class ExerciseTools
{
    [McpServerTool(Name = "list_exercises", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Список упражнений пользователя (его персональные/кастомные упражнения и подключённые из дефолтов) с пагинацией. Scope: exercises:read.")]
    public static Task<ExerciseViewModelPaged> ListExercisesAsync(
        GymClient client,
        CancellationToken ct,
        [Description("Offset для пагинации (0 по умолчанию)")] int offset = 0,
        [Description("Limit (по умолчанию 200)")] int limit = 200)
        => client.GetUserExercisesAsync(offset, limit, null, null, ct);

    [McpServerTool(Name = "list_default_exercises", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Глобальный каталог дефолтных упражнений (с поиском и фильтрами по мышце/оборудованию) с пагинацией. Scope: exercises:read.")]
    public static Task<ExerciseDefaultViewModelPaged> ListDefaultExercisesAsync(
        GymClient client,
        CancellationToken ct,
        [Description("Offset для пагинации (0 по умолчанию)")] int offset = 0,
        [Description("Limit (по умолчанию 200)")] int limit = 200,
        [Description("Текстовый поиск по названию (null — без фильтра)")] string? search = null,
        [Description("Код мышцы для фильтрации (null — без фильтра)")] string? muscleCode = null,
        [Description("Код оборудования для фильтрации (null — без фильтра)")] string? equipmentCode = null)
        => client.GetDefaultExercisesAsync(offset, limit, search!, muscleCode!, equipmentCode!, ct);

    [McpServerTool(Name = "list_exercise_catalogs", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Справочники для упражнений (Muscles + Equipments) одним вызовом — для построения фильтров и UI. Scope: exercises:read.")]
    public static Task<ExerciseCatalogsViewModel> ListExerciseCatalogsAsync(
        GymClient client,
        CancellationToken ct)
        => client.GetExerciseCatalogsAsync(ct);

    [McpServerTool(Name = "list_muscles", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Справочник мышц (ExerciseCatalogItemViewModel: Code, Name и пр.) для назначения нагрузок на упражнения. Scope: exercises:read.")]
    public static Task<ICollection<ExerciseCatalogItemViewModel>> ListMusclesAsync(
        GymClient client,
        CancellationToken ct)
        => client.GetMusclesAsync(ct);

    [McpServerTool(Name = "list_equipment", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Справочник оборудования (ExerciseCatalogItemViewModel: Code, Name и пр.) для привязки к упражнениям. Scope: exercises:read.")]
    public static Task<ICollection<ExerciseCatalogItemViewModel>> ListEquipmentAsync(
        GymClient client,
        CancellationToken ct)
        => client.GetEquipmentAsync(ct);

    [McpServerTool(Name = "create_exercise", Destructive = true),
     Description("Создать или обновить упражнение пользователя (Upsert по Id). Передаётся полный ExerciseViewModel с Muscles/Equipment. Scope: exercises:write.")]
    public static Task CreateExerciseAsync(
        GymClient client,
        [Description("Полный объект упражнения (ExerciseViewModel). Сервер выполняет upsert по Id.")]
        ExerciseViewModel body,
        CancellationToken ct)
        => client.SaveExerciseAsync(body, ct);

    [McpServerTool(Name = "delete_exercise", Destructive = true),
     Description("Удалить упражнение пользователя по id (soft delete на сервере). Scope: exercises:delete.")]
    public static Task DeleteExerciseAsync(
        GymClient client,
        [Description("ID упражнения, которое нужно удалить")] Guid id,
        CancellationToken ct)
        => client.DeleteExerciseAsync(id, ct);
}
