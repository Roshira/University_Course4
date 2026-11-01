using FluentAssertions;
using Microsoft.EntityFrameworkCore;
using TelemetrySystem.Api.Data;
using TelemetrySystem.Api.Models;
using TelemetrySystem.Api.Services;
using System.Reflection;
using Xunit;

namespace TelemetrySystem.Api.Tests;

/// <summary>
/// Unit tests for the AnalyticsService business logic.
/// </summary>
public class AnalyticsServiceTests
{
    /// <summary>
    /// Creates an isolated EF Core In-Memory database instance for each test.
    /// </summary>
    private AppDbContext GetDbContext()
    {
        var options = new DbContextOptionsBuilder<AppDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;
        return new AppDbContext(options);
    }

    /// <summary>
    /// Helper method to access properties of anonymous types using Reflection.
    /// </summary>
    private object GetProp(object obj, string name)
    {
        return obj.GetType().GetProperty(name)?.GetValue(obj, null);
    }

    /// <summary>
    /// Verifies that general statistics correctly calculate total events and unique user counts.
    /// </summary>
    [Fact]
    public async Task GetGeneralStatsAsync_ShouldReturnCorrectCounts()
    {
        var db = GetDbContext();
        var appId = Guid.NewGuid();
        db.Events.AddRange(new List<EventData>
        {
            new() { AppId = appId, SessionId = "s1", EventType = "page_view" },
            new() { AppId = appId, SessionId = "s1", EventType = "click" },
            new() { AppId = appId, SessionId = "s2", EventType = "click" }
        });
        await db.SaveChangesAsync();

        var service = new AnalyticsService(db);
        var result = await service.GetGeneralStatsAsync(appId);

        GetProp(result, "TotalEvents").Should().Be(3);
        GetProp(result, "UniqueUsers").Should().Be(2);
    }

    /// <summary>
    /// Ensures that daily stats are properly filtered within the requested date range.
    /// </summary>
    [Fact]
    public async Task GetDailyStatsAsync_ShouldFilterByDateCorrectly()
    {
        var db = GetDbContext();
        var appId = Guid.NewGuid();
        var today = DateTime.SpecifyKind(DateTime.UtcNow.Date, DateTimeKind.Utc);

        db.Events.Add(new EventData { AppId = appId, Timestamp = today, SessionId = "1" });
        await db.SaveChangesAsync();

        var service = new AnalyticsService(db);
        var result = (IEnumerable<object>)await service.GetDailyStatsAsync(appId, today.AddDays(-1), today.AddDays(1));

        var firstDay = result.First();
        GetProp(firstDay, "TotalEvents").Should().Be(1);
    }

    /// <summary>
    /// Validates that URL-based statistics return correctly aggregated and sorted results.
    /// </summary>
    [Fact]
    public async Task GetUrlStatsAsync_ShouldReturnTopUrlsSorted()
    {
        var db = GetDbContext();
        var appId = Guid.NewGuid();
        db.Events.AddRange(new List<EventData>
        {
            new() { AppId = appId, Url = "/home" },
            new() { AppId = appId, Url = "/home" },
            new() { AppId = appId, Url = "/contact" }
        });
        await db.SaveChangesAsync();

        var service = new AnalyticsService(db);
        var result = (IEnumerable<object>)await service.GetUrlStatsAsync(appId);

        var top = result.First();
        GetProp(top, "Url").Should().Be("/home");
        GetProp(top, "Count").Should().Be(2);
    }
}