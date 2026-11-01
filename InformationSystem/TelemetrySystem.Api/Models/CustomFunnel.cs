using TelemetrySystem.Api.Models;

public class CustomFunnel : AppScopedEntity
{
    public string Name { get; set; } = string.Empty;
    public List<string> Steps { get; set; } = new();
}