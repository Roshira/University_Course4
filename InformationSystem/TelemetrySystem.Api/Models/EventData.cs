namespace TelemetrySystem.Api.Models;

public class EventData : AppScopedEntity
{

    public string SessionId { get; set; } = string.Empty;
    public string EventType { get; set; } = string.Empty;
    public string Url { get; set; } = string.Empty;
    public string? ElementTag { get; set; }
    public string? UserAgent { get; set; }
    public DateTime Timestamp { get; set; } = DateTime.UtcNow;
}