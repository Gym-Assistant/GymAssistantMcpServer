using GymAssistant.McpServer.Infra;
using Xunit;

namespace GymAssistant.McpServer.Tests;

public class EnvConfigTests
{
    [Fact]
    public void Build_ValidEnv_ReturnsConfig()
    {
        var env = new Dictionary<string, string?>
        {
            ["GYM_API_TOKEN"] = "gma_" + new string('a', 40),
            ["GYM_API_URL"] = "https://gym-assistant.ru/api",
        };

        var cfg = EnvConfig.Build(env.GetValueOrDefault);

        Assert.Equal("https://gym-assistant.ru/api", cfg.ApiUrl.ToString().TrimEnd('/'));
        Assert.StartsWith("gma_", cfg.ApiToken);
        Assert.Equal("Information", cfg.LogLevel);
    }

    [Fact]
    public void Build_DefaultsApiUrl_WhenNotSet()
    {
        var env = new Dictionary<string, string?>
        {
            ["GYM_API_TOKEN"] = "gma_" + new string('a', 40),
        };

        var cfg = EnvConfig.Build(env.GetValueOrDefault);

        Assert.Equal("https://gym-assistant.ru/api", cfg.ApiUrl.ToString().TrimEnd('/'));
    }

    [Fact]
    public void Build_MissingToken_Throws()
    {
        var env = new Dictionary<string, string?>();
        Assert.Throws<InvalidOperationException>(() => EnvConfig.Build(env.GetValueOrDefault));
    }

    [Theory]
    [InlineData("plain_token")]
    [InlineData("gma_")]
    [InlineData("gma_short")]
    [InlineData("")]
    public void Build_InvalidTokenShape_Throws(string token)
    {
        var env = new Dictionary<string, string?> { ["GYM_API_TOKEN"] = token };
        Assert.Throws<InvalidOperationException>(() => EnvConfig.Build(env.GetValueOrDefault));
    }

    [Fact]
    public void Build_MalformedUrl_Throws()
    {
        var env = new Dictionary<string, string?>
        {
            ["GYM_API_TOKEN"] = "gma_" + new string('a', 40),
            ["GYM_API_URL"] = "not a url",
        };
        Assert.Throws<InvalidOperationException>(() => EnvConfig.Build(env.GetValueOrDefault));
    }
}
