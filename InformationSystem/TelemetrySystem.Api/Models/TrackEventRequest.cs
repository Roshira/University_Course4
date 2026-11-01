namespace TelemetrySystem.Api.Models;

public class TrackEventRequest
{
    public string SessionId { get; set; } = string.Empty;
    public string EventType { get; set; } = string.Empty;
    public string Url { get; set; } = string.Empty;
    public string? ElementTag { get; set; }

    public Guid AppId { get; set; }
}