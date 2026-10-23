using System.Net;
using System.Text;
using GymAssistant.Client;
using GymAssistant.McpServer.Tools;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Xunit;

namespace GymAssistant.McpServer.Tests;

public sealed class MeasurementToolsTests
{
    private static readonly Guid Id = Guid.Parse("11111111-1111-1111-1111-111111111111");
    private const string MeasurementJson = """{"trackingType":"cardio","durationSeconds":120,"distanceMeters":500.0,"inclinePercent":3.0,"resistanceLevel":"4"}""";
    private const string PlanJson = """{"id":"11111111-1111-1111-1111-111111111111","updatedAt":"2026-10-22T09:00:00Z","templates":[{"title":"Бег","exercises":[{"sets":[{"number":1,"measurement":{"trackingType":"cardio","durationSeconds":120,"distanceMeters":500,"inclinePercent":3,"resistanceLevel":"4"}},{"number":2,"reps":10,"targetWeight":80}]}]}]}""";
    private const string WorkoutJson = """{"id":"11111111-1111-1111-1111-111111111111","trainSessions":[{"sets":[{"number":1,"measurement":{"trackingType":"cardio","durationSeconds":120,"distanceMeters":500,"inclinePercent":3,"resistanceLevel":"4"}},{"number":2,"reps":10,"weight":80}]}]}""";

    [Fact]
    public async Task Workout_and_set_comments_are_returned_and_patch_sends_only_comment()
    {
        using var handler = new Handler("""{"comment":"Самочувствие","trainSessions":[{"sets":[{"comment":"Тяжёлый повтор","weight":80,"reps":8}]}]}""");
        using var http = new HttpClient(handler);
        var client = new GymAssistant.Client.Client("https://example.test", http);
        var workout = await WorkoutTools.GetWorkoutAsync(client, Id, default);
        Assert.Equal("Самочувствие", workout.Comment);
        Assert.Equal("Тяжёлый повтор", Assert.Single(Assert.Single(workout.TrainSessions).Sets).Comment);
        await WorkoutTools.UpdateSetAsync(client, Id, Id, Id, new SetPatchViewModel { Comment = "" }, default);
        Assert.Equal("", (string?)handler.Calls[1].Body!["comment"]);
        Assert.Null(handler.Calls[1].Body!["weight"]);
        Assert.Null(handler.Calls[1].Body!["reps"]);
    }

    [Fact]
    public async Task Read_and_save_workout_preserves_measurement_and_legacy_values()
    {
        using var handler = new Handler(WorkoutJson);
        using var http = new HttpClient(handler);
        var client = new GymAssistant.Client.Client("https://example.test", http);
        var workout = await WorkoutTools.GetWorkoutAsync(client, Id, default);
        var sets = Assert.Single(workout.TrainSessions).Sets.ToArray();
        Assert.Equal(120, sets[0].Measurement.DurationSeconds);
        Assert.Equal(500, sets[0].Measurement.DistanceMeters);
        Assert.Null(sets[1].Measurement);
        Assert.Equal(80, sets[1].Weight);
        Assert.Equal(10, sets[1].Reps);
        await WorkoutTools.CreateWorkoutAsync(client, workout, default);
        Assert.Equal(HttpMethod.Post, handler.Calls[1].Method);
        var sentSets = handler.Calls[1].Body!["trainSessions"]![0]!["sets"]!;
        Assert.True(JToken.DeepEquals(JObject.Parse(MeasurementJson), sentSets[0]!["measurement"]), sentSets[0]!["measurement"]!.ToString());
        Assert.Equal(10, (int)sentSets[1]!["reps"]!);
        Assert.Equal(80, (double)sentSets[1]!["weight"]!);
        Assert.Null(sentSets[1]!["measurement"]);
    }

    [Fact]
    public async Task Create_plan_and_append_only_new_days_preserve_typed_sets()
    {
        using var handler = new Handler(PlanJson);
        using var http = new HttpClient(handler);
        var client = new GymAssistant.Client.Client("https://example.test", http);
        var plan = await PlanTools.GetPlanAsync(client, Id, default);
        await PlanTools.CreatePlanAsync(client, plan, default);
        var body = JsonConvert.DeserializeObject<AppendPlanDaysRequest>("""{"expectedUpdatedAt":"2026-10-22T09:00:00Z","templates":[{"title":"Интервалы","exercises":[{"sets":[{"measurement":{"trackingType":"interval","rounds":5,"workSeconds":30,"recoverySeconds":60}}]}]}]}""")!;
        var result = await PlanTools.AppendPlanDaysAsync(client, Id, body, default);
        Assert.Equal(120, Assert.Single(Assert.Single(result.Templates).Exercises).Sets.First().Measurement.DurationSeconds);
        var createdSets = handler.Calls[1].Body!["templates"]![0]!["exercises"]![0]!["sets"]!;
        Assert.True(JToken.DeepEquals(JObject.Parse(MeasurementJson), createdSets[0]!["measurement"]), createdSets[0]!["measurement"]!.ToString());
        Assert.Null(createdSets[1]!["measurement"]);
        var append = handler.Calls[2];
        Assert.Equal(HttpMethod.Post, append.Method);
        Assert.Equal($"/api/plans/{Id}/days", append.Path);
        Assert.Single((JArray)append.Body!["templates"]!);
        Assert.Equal("Интервалы", (string?)append.Body["templates"]![0]!["title"]);
        Assert.NotNull(append.Body["expectedUpdatedAt"]);
        Assert.Equal(5, (int)append.Body["templates"]![0]!["exercises"]![0]!["sets"]![0]!["measurement"]!["rounds"]!);
    }

    [Fact]
    public async Task Patch_measurement_sends_only_explicit_fields_and_legacy_patch_does_not_send_measurement()
    {
        using var handler = new Handler("{\"measurement\":" + MeasurementJson + "}");
        using var http = new HttpClient(handler);
        var client = new GymAssistant.Client.Client("https://example.test", http);
        var patch = JsonConvert.DeserializeObject<SetPatchViewModel>("{\"measurement\":" + MeasurementJson + "}")!;
        var returned = await WorkoutTools.UpdateSetAsync(client, Id, Id, Id, patch, default);
        Assert.Equal("cardio", returned.Measurement.TrackingType);
        Assert.True(JToken.DeepEquals(JObject.Parse(MeasurementJson), handler.Calls[0].Body!["measurement"]), handler.Calls[0].Body!["measurement"]!.ToString());
        Assert.Null(handler.Calls[0].Body!["weight"]);
        Assert.Null(handler.Calls[0].Body!["reps"]);
        await WorkoutTools.UpdateSetAsync(client, Id, Id, Id, new SetPatchViewModel { Reps = 9 }, default);
        Assert.Null(handler.Calls[1].Body!["measurement"]);
        Assert.Equal(9, (int)handler.Calls[1].Body!["reps"]!);
        Assert.Equal(HttpMethod.Patch, handler.Calls[1].Method);
    }

    [Fact]
    public async Task Taxonomy_parent_and_exercise_tracking_type_are_forwarded()
    {
        using var handler = new Handler("""[{"code":"soleus","name":"Камбаловидная","parentCode":"calves"}]""");
        using var http = new HttpClient(handler);
        var client = new GymAssistant.Client.Client("https://example.test", http);
        var muscle = Assert.Single(await ExerciseTools.ListMusclesAsync(client, default));
        Assert.Equal("calves", muscle.ParentCode);
        await ExerciseTools.CreateExerciseAsync(client, new ExerciseViewModel { Id = Id, Name = "Бег", TrackingType = "cardio" }, default);
        Assert.Equal("cardio", (string?)handler.Calls[1].Body!["trackingType"]);
    }

    [Fact]
    public async Task Append_conflict_is_propagated_without_retry()
    {
        using var handler = new Handler("{}", HttpStatusCode.Conflict);
        using var http = new HttpClient(handler);
        var client = new GymAssistant.Client.Client("https://example.test", http);
        var exception = await Assert.ThrowsAsync<ApiException>(() => PlanTools.AppendPlanDaysAsync(client, Id, new AppendPlanDaysRequest(), default));
        Assert.Equal(409, exception.StatusCode);
        Assert.Single(handler.Calls);
    }

    private sealed class Handler(string response, HttpStatusCode status = HttpStatusCode.OK) : HttpMessageHandler
    {
        public List<(HttpMethod Method, string Path, JObject? Body)> Calls { get; } = [];
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            var text = request.Content is null ? null : await request.Content.ReadAsStringAsync(ct);
            Calls.Add((request.Method, request.RequestUri!.AbsolutePath, text is null ? null : JObject.Parse(text)));
            return new HttpResponseMessage(status) { Content = new StringContent(response, Encoding.UTF8, "application/json") };
        }
    }
}
