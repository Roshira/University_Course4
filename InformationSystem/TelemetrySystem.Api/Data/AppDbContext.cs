using Microsoft.EntityFrameworkCore;
using TelemetrySystem.Api.Models;

namespace TelemetrySystem.Api.Data;

public class AppDbContext : DbContext
{
    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }

    public DbSet<EventData> Events { get; set; }
    public DbSet<Company> Companies { get; set; }
    public DbSet<CustomFunnel> Funnels { get; set; }

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        modelBuilder.Entity<EventData>().HasIndex(e => e.Timestamp);
        modelBuilder.Entity<EventData>().HasIndex(e => e.EventType);
        modelBuilder.Entity<EventData>().HasIndex(e => e.SessionId);
        modelBuilder.Entity<EventData>().HasIndex(e => e.AppId);
    }
}