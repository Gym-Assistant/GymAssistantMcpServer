using System.ComponentModel;
using GymAssistant.Client;
using ModelContextProtocol.Server;

namespace GymAssistant.McpServer.Tools;

[McpServerToolType]
public static class WorkoutTools
{
    [McpServerTool(Name = "list_workouts", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Список тренировок пользователя с пагинацией (новые сверху). Каждая тренировка содержит TrainSessions с подходами. Scope: workouts:read.")]
    public static Task<WorkoutViewModelPaged> ListWorkoutsAsync(
        GymClient client,
        CancellationToken ct,
        [Description("Offset для пагинации (0 по умолчанию)")] int offset = 0,
        [Description("Limit (по умолчанию 30, рекомендуется не более 200)")] int limit = 30)
        => client.GetUserWorkoutsAsync(offset, limit, null, null, ct);

    [McpServerTool(Name = "get_workout", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Получить тренировку по id со всеми тренировочными сессиями (TrainSessions) и подходами (Sets). Scope: workouts:read.")]
    public static Task<WorkoutViewModel> GetWorkoutAsync(
        GymClient client,
        [Description("ID тренировки")] Guid id,
        CancellationToken ct)
        => client.GetWorkoutByIdAsync(id, ct);

    [McpServerTool(Name = "get_workouts_report", ReadOnly = true, Idempotent = true, Destructive = false),
     Description("Сводный отчёт по тренировкам пользователя за период (HTTP 200 при успехе; тело — экспортируемый отчёт, MCP его не возвращает). Scope: workouts:read.")]
    public static Task GetWorkoutsReportAsync(
        GymClient client,
        CancellationToken ct,
        [Description("Начало периода (ISO 8601); null — без нижней границы")] DateTimeOffset? from = null,
        [Description("Конец периода (ISO 8601); null — без верхней границы")] DateTimeOffset? to = null,
        [Description("Формат экспорта (например, json/csv); null — по умолчанию сервера")] string? format = null)
        => client.ExportWorkoutsReportAsync(from, to, format!, ct);

    [McpServerTool(Name = "create_workout", Destructive = true),
     Description("Создать или обновить тренировку (Upsert по Id). Передаётся полный WorkoutViewModel со списком TrainSessions и Sets. Scope: workouts:write.")]
    public static Task CreateWorkoutAsync(
        GymClient client,
        [Description("Полный объект тренировки (WorkoutViewModel). Сервер выполняет upsert по Id.")]
        WorkoutViewModel body,
        CancellationToken ct)
        => client.SaveWorkoutAsync(body, ct);

    [McpServerTool(Name = "update_set", Destructive = true),
     Description("Обновить один подход (Set) внутри тренировочной сессии — частичный patch полей Reps, Weight, IsDone, Number. Scope: workouts:write.")]
    public static Task<SetViewModel> UpdateSetAsync(
        GymClient client,
        [Description("ID тренировки (workoutId)")] Guid workoutId,
        [Description("ID тренировочной сессии (trainSessionId)")] Guid sessionId,
        [Description("ID подхода (setId)")] Guid setId,
        [Description("Частичные изменения подхода (SetPatchViewModel): Reps, Weight, IsDone, Number — любые из полей")]
        SetPatchViewModel body,
        CancellationToken ct)
        => client.PatchSetAsync(workoutId, sessionId, setId, body, ct);

    [McpServerTool(Name = "delete_workout", Destructive = true),
     Description("Удалить тренировку по id (soft delete на сервере). Scope: workouts:delete.")]
    public static Task DeleteWorkoutAsync(
        GymClient client,
        [Description("ID тренировки, которую нужно удалить")] Guid id,
        CancellationToken ct)
        => client.DeleteWorkoutAsync(id, ct);
}
