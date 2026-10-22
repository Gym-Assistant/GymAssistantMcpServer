using System.Net;
using System.Text;
using GymAssistant.Client;
using GymAssistant.McpServer.Tools;
using Newtonsoft.Json.Linq;
using Xunit;

namespace GymAssistant.McpServer.Tests;

public sealed class CatalogMetadataToolsTests
{
    private static readonly Guid Id = Guid.Parse("11111111-1111-1111-1111-111111111111");
    private const string Metadata = """
        {"id":"11111111-1111-1111-1111-111111111111","globalId":"22222222-2222-2222-2222-222222222222",
        "name":"Мой жим","nameEn":"Bench press","descriptionEn":"Controlled movement","aliasesEn":["Barbell bench press"],
        "groupCode":"chest","trackingType":"weight_reps","loadConvention":"per_implement","isUnilateral":false,
        "muscles":[{"muscleCode":"chest","loadPercent":70,"role":"primary","priority":0}],
        "media":[{"kind":"image","url":"https://example.test/bench.webp","frames":["https://example.test/start.webp"],
        "sourceUrl":"https://example.test/source","license":"CC0","gender":"male","style":"detailed","view":"side",
        "altRu":"Жим","altEn":"Bench press"}]}
        """;

    [Fact]
    public async Task Read_and_save_personal_exercise_preserves_all_metadata_and_identity()
    {
        using var handler = new Handler("{\"items\":[" + Metadata + "],\"total\":1}");
        using var http = new HttpClient(handler);
        var client = new GymAssistant.Client.Client("https://example.test", http);
        var exercise = Assert.Single((await ExerciseTools.ListExercisesAsync(client, default)).Items);
        await ExerciseTools.CreateExerciseAsync(client, exercise, default);
        var expected = JObject.Parse(Metadata);
        var sent = handler.Calls[1].Body!;
        foreach (var property in expected.Properties())
            Assert.True(JToken.DeepEquals(property.Value, sent[property.Name]), property.Name + ": " + sent[property.Name]);
        Assert.Null(sent["canonicalId"]);
        Assert.Null(sent["isHidden"]);
        Assert.Equal(HttpMethod.Post, handler.Calls[1].Method);
    }

    [Fact]
    public async Task Default_read_by_id_returns_hidden_template_without_relinking()
    {
        var item = JObject.Parse(Metadata);
        item["globalId"] = Id.ToString();
        item["canonicalId"] = "33333333-3333-3333-3333-333333333333";
        item["isHidden"] = true;
        using var handler = new Handler(item.ToString());
        using var http = new HttpClient(handler);
        var client = new GymAssistant.Client.Client("https://example.test", http);
        var exercise = await ExerciseTools.GetDefaultExerciseAsync(client, Id, default);
        Assert.Equal(Id, exercise.GlobalId);
        Assert.True(exercise.IsHidden);
        Assert.Equal(Guid.Parse((string)item["canonicalId"]!), exercise.CanonicalId);
        Assert.Equal("Bench press", exercise.NameEn);
        Assert.Equal("primary", Assert.Single(exercise.Muscles).Role);
        Assert.Equal($"/api/exercises/defaults/{Id}", handler.Calls[0].Uri.AbsolutePath);
        Assert.Single(handler.Calls);
    }

    [Fact]
    public async Task Include_hidden_is_explicit_and_legacy_personal_payload_omits_new_metadata()
    {
        using var handler = new Handler("{\"items\":[],\"total\":0}");
        using var http = new HttpClient(handler);
        var client = new GymAssistant.Client.Client("https://example.test", http);
        await ExerciseTools.ListDefaultExercisesAsync(client, default);
        Assert.Contains("includeHidden=false", handler.Calls[0].Uri.Query);
        await ExerciseTools.ListDefaultExercisesAsync(client, default, includeHidden: true);
        Assert.Contains("includeHidden=true", handler.Calls[1].Uri.Query);
        await ExerciseTools.CreateExerciseAsync(client, new ExerciseViewModel { Id = Id, Name = "Мой жим" }, default);
        var sent = handler.Calls[2].Body!;
        foreach (var property in new[] { "nameEn", "descriptionEn", "aliasesEn", "groupCode", "media", "loadConvention", "isUnilateral" })
            Assert.Null(sent[property]);
    }

    private sealed class Handler(string response) : HttpMessageHandler
    {
        public List<(HttpMethod Method, Uri Uri, JObject? Body)> Calls { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            var text = request.Content is null ? null : await request.Content.ReadAsStringAsync(ct);
            Calls.Add((request.Method, request.RequestUri!, text is null ? null : JObject.Parse(text)));
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(response, Encoding.UTF8, "application/json")
            };
        }
    }
}
