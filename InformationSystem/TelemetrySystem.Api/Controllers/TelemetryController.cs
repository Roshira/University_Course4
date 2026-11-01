using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using System.Threading.Channels;
using TelemetrySystem.Api.Models;
using TelemetrySystem.Api.Observability;
using TelemetrySystem.Api.Services;

namespace TelemetrySystem.Api.Controllers;

[ApiController]
[Route("api/[controller]")]
public class TelemetryController : ControllerBase
{
    private readonly Channel<EventData> _channel;
    private readonly IAnalyticsService _analyticsService;

    public TelemetryController(Channel<EventData> channel, IAnalyticsService analyticsService)
    {
        _channel = channel;
        _analyticsService = analyticsService;
    }

    [HttpPost("track")]
    public async Task<IActionResult> TrackEvent([FromBody] TrackEventRequest request)
    {
        var newEvent = new EventData
        {
            AppId = request.AppId,
            SessionId = request.SessionId,
            EventType = request.EventType,
            Url = request.Url,
            ElementTag = request.ElementTag,
            UserAgent = Request.Headers.UserAgent.ToString(),
            Timestamp = DateTime.UtcNow
        };
        await _channel.Writer.WriteAsync(newEvent);
        AppMetrics.EventsReceived.WithLabels(string.IsNullOrEmpty(request.EventType) ? "unknown" : request.EventType).Inc();
        AppMetrics.ChannelBacklog.Set(_channel.Reader.Count);
        return Ok();
    }

    [Authorize]
    [HttpGet("stats")]
    public async Task<IActionResult> GetStats()
    {
        var appId = Guid.Parse(User.FindFirst("AppId")!.Value);
        return Ok(await _analyticsService.GetGeneralStatsAsync(appId));
    }

    [Authorize]
    [HttpGet("clicks")]
    public async Task<IActionResult> GetClicks()
    {
        var appId = Guid.Parse(User.FindFirst("AppId")!.Value);
        return Ok(await _analyticsService.GetClickStatsAsync(appId));
    }

    [Authorize]
    [HttpGet("daily")]
    public async Task<IActionResult> GetDailyStats([FromQuery] DateTime? from, [FromQuery] DateTime? to)
    {
        var appId = Guid.Parse(User.FindFirst("AppId")!.Value);

        var startDate = from.HasValue
            ? DateTime.SpecifyKind(from.Value, DateTimeKind.Utc)
            : DateTime.UtcNow.AddDays(-7);

        var endDate = to.HasValue
            ? DateTime.SpecifyKind(to.Value, DateTimeKind.Utc)
            : DateTime.UtcNow;

        return Ok(await _analyticsService.GetDailyStatsAsync(appId, startDate, endDate));
    }

    [Authorize]
    [HttpGet("available-elements")]
    public async Task<IActionResult> GetAvailableElements()
    {
        var appId = Guid.Parse(User.FindFirst("AppId")!.Value);
        var elements = await _analyticsService.GetClickStatsAsync(appId);
        return Ok(elements);
    }

    [Authorize]
    [HttpPost("funnels")]
    public async Task<IActionResult> CreateFunnel([FromBody] CustomFunnel funnel)
    {
        var appId = Guid.Parse(User.FindFirst("AppId")!.Value);
        funnel.AppId = appId;
        var saved = await _analyticsService.SaveFunnelAsync(funnel);
        return Ok(saved);
    }

    [Authorize]
    [HttpGet("custom-funnels")]
    public async Task<IActionResult> GetCustomFunnels([FromQuery] string mode = "unique")
    {
        var claim = User.FindFirst("AppId");
        if (claim == null) return Unauthorized();
        var appId = Guid.Parse(claim.Value);

        var funnels = await _analyticsService.GetFunnelsByAppIdAsync(appId);

        var results = new List<object>();
        foreach (var f in funnels)
        {
            var data = await _analyticsService.CalculateCustomFunnelAsync(appId, f.Id, mode);
            results.Add(data);
        }
        return Ok(results);
    }

    [Authorize]
    [HttpGet("url-stats")]
    public async Task<IActionResult> GetUrlStats()
    {
        var appId = Guid.Parse(User.FindFirst("AppId")!.Value);
        return Ok(await _analyticsService.GetUrlStatsAsync(appId));
    }

}