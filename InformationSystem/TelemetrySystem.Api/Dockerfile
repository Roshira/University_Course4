FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY TelemetrySystem.Api.csproj ./
RUN dotnet restore TelemetrySystem.Api.csproj
COPY . .
RUN dotnet publish TelemetrySystem.Api.csproj -c Release -o /app --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app
COPY --from=build /app .
# образ aspnet уже слухає 8080 (ASPNETCORE_HTTP_PORTS) і має непривілейованого користувача app
USER $APP_UID
EXPOSE 8080
ENTRYPOINT ["dotnet", "TelemetrySystem.Api.dll"]
