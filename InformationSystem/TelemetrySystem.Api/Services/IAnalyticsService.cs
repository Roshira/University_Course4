using Microsoft.EntityFrameworkCore;
using TelemetrySystem.Api.Data;
using TelemetrySystem.Api.Models;

namespace TelemetrySystem.Api.Services;

public interface IAnalyticsService
{
    Task<object> GetGeneralStatsAsync(Guid appId);
    Task<object> GetDailyStatsAsync(Guid appId, DateTime from, DateTime to);
    Task<object> GetFunnelAsync(Guid appId);
    Task<object> GetClickStatsAsync(Guid appId);

    Task<object> CalculateCustomFunnelAsync(Guid appId, Guid funnelId, string mode);
    Task<CustomFunnel> SaveFunnelAsync(CustomFunnel funnel);
    Task<List<CustomFunnel>> GetFunnelsByAppIdAsync(Guid appId);

    Task<object> GetUrlStatsAsync(Guid appId);

}

public class AnalyticsService : IAnalyticsService
{
    private readonly AppDbContext _dbContext;

    public AnalyticsService(AppDbContext dbContext)
    {
        _dbContext = dbContext;
    }

    public async Task<object> GetGeneralStatsAsync(Guid appId)
    {
        var query = _dbContext.Events.Where(e => e.AppId == appId);
        var totalEvents = await query.CountAsync();
        var eventsByType = await query.GroupBy(e => e.EventType)
            .Select(g => new { EventType = g.Key, Count = g.Count() }).ToListAsync();
        var uniqueUsers = await query.Select(e => e.SessionId).Distinct().CountAsync();

        return new { TotalEvents = totalEvents, UniqueUsers = uniqueUsers, EventsByType = eventsByType };
    }

    public async Task<object> GetDailyStatsAsync(Guid appId, DateTime from, DateTime to)
    {
        var startDate = DateTime.SpecifyKind(from.Date, DateTimeKind.Utc);
        var endDate = DateTime.SpecifyKind(to.Date, DateTimeKind.Utc);

        var statsRaw = await _dbContext.Events
            .Where(e => e.AppId == appId && e.Timestamp.Date >= startDate && e.Timestamp.Date <= endDate)
            .GroupBy(e => e.Timestamp.Date)
            .Select(g => new
            {
                Date = g.Key,
                TotalEvents = g.Count(),
                UniqueSessions = g.Select(e => e.SessionId).Distinct().Count()
            })
            .OrderBy(x => x.Date)
            .ToListAsync();

        return statsRaw.Select(x => new
        {
            Date = x.Date.ToString("dd.MM"),
            TotalEvents = x.TotalEvents,
            UniqueSessions = x.UniqueSessions
        }).ToList();
    }

    public async Task<object> GetFunnelAsync(Guid appId)
    {
        var totalHome = await _dbContext.Events.Where(e => e.AppId == appId && e.Url == "/").Select(e => e.SessionId).Distinct().CountAsync();
        var totalRegister = await _dbContext.Events.Where(e => e.AppId == appId && e.Url == "/register").Select(e => e.SessionId).Distinct().CountAsync();
        var totalSuccess = await _dbContext.Events.Where(e => e.AppId == appId && e.Url == "/dashboard").Select(e => e.SessionId).Distinct().CountAsync();

        return new[] {
            new { Step = "Відвідали сайт", Count = totalHome },
            new { Step = "Перейшли до реєстрації", Count = totalRegister },
            new { Step = "Стали клієнтами", Count = totalSuccess }
        };
    }

    public async Task<object> GetClickStatsAsync(Guid appId)
    {
        return await _dbContext.Events
            .Where(e => e.AppId == appId && e.EventType == "click" && e.ElementTag != null)
            .GroupBy(e => new { e.ElementTag, e.Url })
            .Select(g => new { Element = g.Key.ElementTag, Url = g.Key.Url, Clicks = g.Count() })
            .OrderByDescending(x => x.Clicks)
            .Take(20)
            .ToListAsync();
    }


    public async Task<CustomFunnel> SaveFunnelAsync(CustomFunnel funnel)
    {
        _dbContext.Funnels.Add(funnel);
        await _dbContext.SaveChangesAsync();
        return funnel;
    }

    public async Task<List<CustomFunnel>> GetFunnelsByAppIdAsync(Guid appId)
    {
        return await _dbContext.Funnels.Where(f => f.AppId == appId).ToListAsync();
    }

    public async Task<object> CalculateCustomFunnelAsync(Guid appId, Guid funnelId, string mode)
    {
        var funnel = await _dbContext.Funnels.FirstOrDefaultAsync(f => f.Id == funnelId);
        if (funnel == null) return null;

        var results = new List<object>();
        foreach (var stepLabel in funnel.Steps)
        {
            var baseQuery = _dbContext.Events.Where(e => e.AppId == appId && e.ElementTag == stepLabel);

            int count;
            if (mode == "total")
            {
                count = await baseQuery.CountAsync();
            }
            else
            {
                count = await baseQuery.Select(e => e.SessionId).Distinct().CountAsync();
            }

            results.Add(new { StepName = stepLabel, Count = count });
        }
        return new { FunnelName = funnel.Name, Data = results };
    }

    public async Task<object> GetUrlStatsAsync(Guid appId)
    {
        return await _dbContext.Events
            .Where(e => e.AppId == appId)
            .GroupBy(e => e.Url)
            .Select(g => new { Url = g.Key, Count = g.Count() })
            .OrderByDescending(x => x.Count)
            .Take(5)
            .ToListAsync();
    }

    public Task<object> GetFunnelAsync(string s1, string s2) => Task.FromResult<object>(null!);
}