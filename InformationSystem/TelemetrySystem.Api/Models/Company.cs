namespace TelemetrySystem.Api.Models;

public class Company : BaseEntity
{
    public string Name { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
    public string PasswordHash { get; set; } = string.Empty;

    public Guid AppId { get; set; } = Guid.NewGuid();
}