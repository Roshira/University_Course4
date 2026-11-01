namespace TelemetrySystem.Api.Models
{
    public abstract class AppScopedEntity : BaseEntity
    {
        public Guid AppId { get; set; }
    }
}
