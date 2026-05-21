using System.ComponentModel;
using System.Reflection;
using ModelContextProtocol.Server;
using Xunit;

namespace GymAssistant.McpServer.Tests;

public class ToolRegistrationTests
{
    private static readonly Assembly ServerAsm =
        typeof(GymAssistant.McpServer.Infra.EnvConfig).Assembly;

    private static IEnumerable<MethodInfo> GetToolMethods()
    {
        return ServerAsm.GetTypes()
            .Where(t => t.Namespace?.EndsWith(".Tools") == true)
            .SelectMany(t => t.GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.Instance))
            .Where(m => m.GetCustomAttribute<McpServerToolAttribute>() is not null);
    }

    [Fact]
    public void EveryToolMethod_HasDescription()
    {
        var missing = GetToolMethods()
            .Where(m => string.IsNullOrWhiteSpace(m.GetCustomAttribute<DescriptionAttribute>()?.Description))
            .Select(m => $"{m.DeclaringType?.FullName}.{m.Name}")
            .ToArray();

        Assert.True(missing.Length == 0,
            $"Tool methods missing [Description]: {string.Join(", ", missing)}");
    }

    [Fact]
    public void ToolNames_AreUnique()
    {
        var names = GetToolMethods()
            .Select(m => m.GetCustomAttribute<McpServerToolAttribute>()!.Name ?? m.Name)
            .ToArray();

        var dupes = names
            .GroupBy(n => n)
            .Where(g => g.Count() > 1)
            .Select(g => g.Key)
            .ToArray();

        Assert.True(dupes.Length == 0,
            $"Duplicate tool names: {string.Join(", ", dupes)}");
    }

    [Fact]
    public void ToolClasses_LiveInToolsNamespace()
    {
        var bad = ServerAsm.GetTypes()
            .Where(t => t.GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.Instance)
                .Any(m => m.GetCustomAttribute<McpServerToolAttribute>() is not null))
            .Where(t => t.Namespace?.EndsWith(".Tools") != true)
            .Select(t => t.FullName)
            .ToArray();

        Assert.True(bad.Length == 0,
            $"Types with [McpServerTool] outside *.Tools namespace: {string.Join(", ", bad)}");
    }
}
