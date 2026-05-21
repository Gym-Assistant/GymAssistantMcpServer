using GymAssistant.McpServer.Infra;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using ModelContextProtocol.Server;

EnvConfig config;
try
{
    config = EnvConfig.Build(Environment.GetEnvironmentVariable);
}
catch (InvalidOperationException ex)
{
    Console.Error.WriteLine($"FATAL: {ex.Message}");
    return 1;
}

var builder = Host.CreateApplicationBuilder(args);

builder.Logging.ClearProviders();
builder.Logging.AddConsole(o =>
{
    o.LogToStandardErrorThreshold = LogLevel.Trace; // stdout зарезервирован для MCP
});
if (Enum.TryParse<LogLevel>(config.LogLevel, ignoreCase: true, out var lvl))
{
    builder.Logging.SetMinimumLevel(lvl);
}
else
{
    Console.Error.WriteLine($"WARNING: GYM_LOG_LEVEL='{config.LogLevel}' is not a valid LogLevel; using default.");
}

builder.Services.AddSingleton(config);
builder.Services.AddGymClient();

builder.Services
    .AddMcpServer()
    .WithStdioServerTransport()
    .WithToolsFromAssembly(typeof(Program).Assembly);

await builder.Build().RunAsync();
return 0;
