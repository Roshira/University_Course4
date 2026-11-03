using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using Prometheus;
using System.Text;
using System.Threading.Channels;
using TelemetrySystem.Api.BackgroundTasks;
using TelemetrySystem.Api.Data;
using TelemetrySystem.Api.Models;
using TelemetrySystem.Api.Observability;
using TelemetrySystem.Api.Services;

var builder = WebApplication.CreateBuilder(args);

// ---------- Логи: JSON у stdout -> Grafana Alloy -> Loki ----------
// IncludeScopes додає TraceId/SpanId у кожен рядок, тож з логу в Loki можна перейти до трейсу в Tempo.
builder.Logging.ClearProviders();
builder.Logging.AddJsonConsole(o =>
{
    o.IncludeScopes = true;
    o.TimestampFormat = "yyyy-MM-ddTHH:mm:ss.fffZ";
    o.UseUtcTimestamp = true;
});

// ---------- Трейси: OpenTelemetry -> OTLP -> Grafana Tempo ----------
// Адреса колектора береться зі змінної OTEL_EXPORTER_OTLP_ENDPOINT (див. docker-compose.yml).
var otlpEnabled = !string.IsNullOrEmpty(builder.Configuration["OTEL_EXPORTER_OTLP_ENDPOINT"]);
builder.Services.AddOpenTelemetry()
    .ConfigureResource(r => r.AddService(
        serviceName: builder.Configuration["OTEL_SERVICE_NAME"] ?? AppMetrics.ServiceName))
    .WithTracing(t =>
    {
        t.AddAspNetCoreInstrumentation(o =>
            {
                // не засмічуємо Tempo запитами Prometheus до /metrics
                o.Filter = ctx => !ctx.Request.Path.StartsWithSegments("/metrics")
                               && !ctx.Request.Path.StartsWithSegments("/health");
            })
         .AddHttpClientInstrumentation()
         .AddSource("Npgsql")                 // вбудований ActivitySource драйвера Npgsql -> SQL-спани
         .AddSource(AppMetrics.Tracer.Name);  // власні спани (telemetry.write)
        if (otlpEnabled) t.AddOtlpExporter();
    });

builder.Services.AddDbContext<AppDbContext>(options =>
    options.UseNpgsql(builder.Configuration.GetConnectionString("DefaultConnection")));

// Черга між прийомом подій і записом у БД. Якщо БД не встигає і черга переповнена, найстаріші події
// витісняються — рахуємо їх, щоб втрати було видно в Prometheus, а не лише в БД.
var eventChannel = Channel.CreateBounded<EventData>(
    new BoundedChannelOptions(100000) { FullMode = BoundedChannelFullMode.DropOldest },
    _ => AppMetrics.EventsDropped.Inc());
builder.Services.AddSingleton(eventChannel);
// розмір черги читаємо в момент збору метрик Prometheus — значення завжди актуальне
Metrics.DefaultRegistry.AddBeforeCollectCallback(() => AppMetrics.ChannelBacklog.Set(eventChannel.Reader.Count));

builder.Services.AddHostedService<TelemetryWriterService>();
builder.Services.AddScoped<IAnalyticsService, AnalyticsService>();

builder.Services.AddCors(options =>
{
    options.AddPolicy("AllowAnySite", policy =>
        policy.AllowAnyOrigin()
              .AllowAnyMethod()
              .AllowAnyHeader());
});

var key = Encoding.ASCII.GetBytes("SuperSecretKeyForTelemetryDashboard12345!");
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuerSigningKey = true,
            IssuerSigningKey = new SymmetricSecurityKey(key),
            ValidateIssuer = false,
            ValidateAudience = false
        };
    });

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();

// У Docker PostgreSQL може стартувати повільніше за API — кілька спроб міграції.
using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
    for (var attempt = 1; ; attempt++)
    {
        try
        {
            db.Database.Migrate();
            break;
        }
        catch (Exception ex) when (attempt < 10 && ex is Npgsql.NpgsqlException or TimeoutException)
        {
            app.Logger.LogWarning(ex, "Database is not ready (attempt {Attempt}), retrying in 3s", attempt);
            Thread.Sleep(TimeSpan.FromSeconds(3));
        }
    }
}

// Swagger курсової: у Development або явно через EnableSwagger=true (docker-compose працює в Production,
// щоб назовні не віддавалися сторінки помилок зі стектрейсами).
if (app.Environment.IsDevelopment() || app.Configuration.GetValue<bool>("EnableSwagger"))
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseStaticFiles();

app.UseCors("AllowAnySite");

app.UseRouting();
app.UseHttpMetrics();   // http_requests_received_total, http_request_duration_seconds

app.UseAuthentication();
app.UseAuthorization();

app.MapControllers();
app.MapMetrics();        // GET /metrics для Prometheus
app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

app.Run();
