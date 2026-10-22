using System.Collections;
using System.ComponentModel;
using System.Net;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using GymAssistant.McpServer.Infra;
using ModelContextProtocol.Server;
using GymClient = GymAssistant.Client.Client;

namespace GymAssistant.McpServer.Tests;

/// <summary>
/// Описание каждого инструмента должно называть ровно то право, которое требует backend.
/// Таблица ниже перенесена из GymBackendV2 (origin/develop: Program.cs, Health/HealthEndpoints.cs,
/// IntegrationTests/Features/ApiTokens/ScopeCoverageTest.cs): RequireScope по маршруту,
/// RequireAuthorization без scope (каталоги) или анонимный доступ.
/// При изменении backend обновить таблицу и описания вместе.
/// </summary>
public sealed class ToolAccessContractTests
{
    public const string AnonymousText = "Scope не нужен: публичный справочник, backend не требует авторизации.";
    public const string AuthenticatedText = "Scope не нужен: достаточно любого действующего PAT.";
    private const string Anonymous = "anonymous";
    private const string Authenticated = "authenticated";

    private static readonly Regex ScopePattern =
        new(@"\b(?:profile|body|workouts|exercises|plans|health):(?:read|write|delete)\b", RegexOptions.Compiled);

    private static readonly Regex GuidSegment =
        new("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", RegexOptions.Compiled);

    // tool -> (HTTP-метод и маршрут, который вызывает клиент; доступ на backend)
    private static readonly IReadOnlyDictionary<string, (string Route, string Access)> Backend =
        new Dictionary<string, (string, string)>
        {
            ["get_me"] = ("GET /api/auth/me", "profile:read"),
            ["get_user_settings"] = ("GET /api/user/settings", "profile:read"),
            ["update_user_settings"] = ("PUT /api/user/settings", "profile:write"),
            ["get_active_plan"] = ("GET /api/user/active-plan", "plans:read"),
            ["set_active_plan"] = ("PUT /api/user/active-plan", "plans:write"),

            ["list_body_characteristics"] = ("GET /api/body/characteristics", "body:read"),
            ["list_body_characteristics_with_latest"] = ("GET /api/body/characteristics/with-latest", "body:read"),
            ["list_default_body_characteristics"] = ("GET /api/body/default-characteristics", Anonymous),
            ["get_body_characteristic"] = ("GET /api/body/characteristics/{id}", "body:read"),
            ["create_body_characteristic"] = ("POST /api/body/characteristic", "body:write"),
            ["delete_body_characteristic"] = ("DELETE /api/body/characteristics/{id}", "body:delete"),
            ["list_body_stamps"] = ("GET /api/body/stamps", "body:read"),
            ["create_body_stamps"] = ("POST /api/body/stamps", "body:write"),
            ["delete_body_stamp"] = ("DELETE /api/body/stamps/{id}", "body:delete"),

            ["list_workouts"] = ("GET /api/workouts", "workouts:read"),
            ["get_workout"] = ("GET /api/workouts/{id}", "workouts:read"),
            ["get_workouts_report"] = ("GET /api/reports/workouts", "workouts:read"),
            ["create_workout"] = ("POST /api/workout", "workouts:write"),
            ["update_set"] = ("PATCH /api/workouts/{id}/sessions/{id}/sets/{id}", "workouts:write"),
            ["delete_workout"] = ("DELETE /api/workouts/{id}", "workouts:delete"),

            ["list_exercises"] = ("GET /api/exercises", "exercises:read"),
            ["list_default_exercises"] = ("GET /api/exercises/defaults", Anonymous),
            ["get_default_exercise"] = ("GET /api/exercises/defaults/{globalId}", Anonymous),
            ["list_exercise_catalogs"] = ("GET /api/exercises/catalogs", Anonymous),
            ["list_muscles"] = ("GET /api/muscles", Authenticated),
            ["list_equipment"] = ("GET /api/equipment", Authenticated),
            ["create_exercise"] = ("POST /api/exercises", "exercises:write"),
            ["delete_exercise"] = ("DELETE /api/exercises/{id}", "exercises:delete"),

            ["list_plans"] = ("GET /api/plans", "plans:read"),
            ["get_plan"] = ("GET /api/plans/{id}", "plans:read"),
            ["create_plan"] = ("POST /api/plans", "plans:write"),
            ["append_plan_days"] = ("POST /api/plans/{id}/days", "plans:write"),
            ["delete_plan"] = ("DELETE /api/plans/{id}", "plans:delete"),
            ["list_plan_catalog"] = ("GET /api/plans/catalog", Authenticated),
            ["get_plan_from_catalog"] = ("GET /api/plans/catalog/{id}", Authenticated),
            ["fork_plan"] = ("POST /api/plans/{id}/fork", "plans:write"),
            ["publish_plan"] = ("POST /api/plans/{id}/publish", "plans:write"),
            ["unpublish_plan"] = ("POST /api/plans/{id}/unpublish", "plans:write"),
            ["check_plan_updates"] = ("GET /api/plans/{id}/updates/available", "plans:read"),
            ["pull_plan_updates"] = ("POST /api/plans/{id}/pull", "plans:write"),
            ["detach_plan"] = ("POST /api/plans/{id}/detach", "plans:write"),

            ["get_apple_health_daily"] = ("GET /api/health/apple/daily", "health:read"),
            ["get_apple_health_metrics"] = ("GET /api/health/apple/metrics", "health:read"),

            ["health_check"] = ("GET /api/auth/me", "profile:read"),
        };

    public static IEnumerable<object[]> ToolNames() => Backend.Keys.Select(name => new object[] { name });

    private static readonly IReadOnlyDictionary<string, MethodInfo> Tools =
        typeof(EnvConfig).Assembly.GetTypes()
            .Where(t => t.Namespace?.EndsWith(".Tools") == true)
            .SelectMany(t => t.GetMethods(BindingFlags.Public | BindingFlags.Static))
            .Where(m => m.GetCustomAttribute<McpServerToolAttribute>() is not null)
            .ToDictionary(m => m.GetCustomAttribute<McpServerToolAttribute>()!.Name ?? m.Name);

    [Fact]
    public void Every_tool_has_a_backend_mapping_and_there_are_44()
    {
        Assert.Equal(44, Tools.Count);
        Assert.Equal(Backend.Keys.Order(), Tools.Keys.Order());
    }

    [Fact]
    public void Readme_lists_every_tool_and_the_current_count()
    {
        var root = new DirectoryInfo(AppContext.BaseDirectory);
        while (root is not null && !File.Exists(Path.Combine(root.FullName, "GymAssistantMcpServer.slnx")))
            root = root.Parent;
        Assert.NotNull(root);
        var readme = File.ReadAllText(Path.Combine(root.FullName, "README.md"));
        Assert.Contains($"{Tools.Count} инструмента", readme);
        var missing = Tools.Keys.Where(name => !readme.Contains($"`{name}`")).ToArray();
        Assert.True(missing.Length == 0, "README не упоминает: " + string.Join(", ", missing));
    }

    [Theory]
    [MemberData(nameof(ToolNames))]
    public void Description_names_exactly_the_access_the_backend_requires(string tool)
    {
        var description = Tools[tool].GetCustomAttribute<DescriptionAttribute>()!.Description;
        var named = ScopePattern.Matches(description).Select(m => m.Value).Distinct().ToArray();
        var access = Backend[tool].Access;
        switch (access)
        {
            case Anonymous:
                Assert.Empty(named);
                Assert.Contains(AnonymousText, description);
                break;
            case Authenticated:
                Assert.Empty(named);
                Assert.Contains(AuthenticatedText, description);
                break;
            default:
                Assert.Equal(new[] { access }, named);
                Assert.Contains($"Scope: {access}.", description);
                break;
        }
    }

    [Theory]
    [MemberData(nameof(ToolNames))]
    public async Task Tool_calls_the_backend_route_the_mapping_describes(string tool)
    {
        var handler = new RecordingHandler();
        using var http = new HttpClient(handler);
        var client = new GymClient("https://backend.test", http);
        var method = Tools[tool];
        var arguments = method.GetParameters().Select(p => Argument(p, client)).ToArray();
        try
        {
            await (Task)method.Invoke(null, arguments)!;
        }
        catch (Exception)
        {
            // Пустой синтетический ответ может не десериализоваться: проверяется только запрос.
        }
        var request = Assert.Single(handler.Requests);
        Assert.Equal(Backend[tool].Route.Replace("{globalId}", "{id}"), request);
    }

    private static object? Argument(ParameterInfo parameter, GymClient client)
    {
        var type = parameter.ParameterType;
        if (type == typeof(GymClient)) return client;
        if (type == typeof(CancellationToken)) return CancellationToken.None;
        if (type == typeof(EnvConfig))
            return EnvConfig.Build(name => name == "GYM_API_TOKEN" ? "gma_" + new string('a', 40) : null);
        if (type == typeof(Guid)) return Guid.NewGuid();
        if (type == typeof(Guid?)) return Guid.NewGuid();
        if (type == typeof(string)) return "2026-10-20";
        if (type == typeof(DateTimeOffset)) return DateTimeOffset.UnixEpoch;
        if (parameter.HasDefaultValue) return parameter.DefaultValue;
        if (type.IsGenericType && typeof(IEnumerable).IsAssignableFrom(type))
            return Activator.CreateInstance(typeof(List<>).MakeGenericType(type.GetGenericArguments()[0]));
        return Activator.CreateInstance(type);
    }

    private sealed class RecordingHandler : HttpMessageHandler
    {
        public List<string> Requests { get; } = [];

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            var path = GuidSegment.Replace(request.RequestUri!.AbsolutePath, "{id}");
            Requests.Add($"{request.Method.Method} {path}");
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("{}", Encoding.UTF8, "application/json"),
            });
        }
    }
}
