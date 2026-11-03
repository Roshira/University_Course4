using System.Diagnostics;
using System.Runtime.CompilerServices;
using TelemetrySystem.Api.Models;

namespace TelemetrySystem.Api.Observability;

/// <summary>
/// Передає контекст трейсу від HTTP-запиту /api/telemetry/track до фонового TelemetryWriterService.
/// Подія йде через Channel, тому Activity.Current там уже інший; без цього спан telemetry.write
/// і SQL INSERT потрапляли б в окремий трейс, а не в наскрізний generator -> RabbitMQ -> worker -> API -> БД.
/// ConditionalWeakTable не змінює модель EventData і не тримає подію в пам'яті після запису.
/// </summary>
public static class EventTraceContext
{
    private static readonly ConditionalWeakTable<EventData, object> Contexts = new();

    public static void Remember(EventData eventData)
    {
        if (Activity.Current is { } current)
            Contexts.AddOrUpdate(eventData, current.Context);
    }

    public static ActivityContext Take(EventData eventData)
    {
        if (Contexts.TryGetValue(eventData, out var boxed))
        {
            Contexts.Remove(eventData);
            return (ActivityContext)boxed;
        }
        return default;
    }
}
