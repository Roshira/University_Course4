using FluentAssertions;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using TelemetrySystem.Api.Controllers;
using TelemetrySystem.Api.Data;
using Xunit;

namespace TelemetrySystem.Api.Tests;

/// <summary>
/// Unit tests for the Authentication Controller endpoints.
/// </summary>
public class AuthControllerTests
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
    /// Verifies that a valid registration request returns an OK status and saves the company.
    /// </summary>
    [Fact]
    public async Task Register_ShouldReturnOk_WhenUserIsNew()
    {
        // Arrange
        var db = GetDbContext();
        var controller = new AuthController(db);
        var request = new AuthController.RegisterRequest
        {
            Name = "Test Co",
            Email = "test@co.com",
            Password = "password123"
        };

        // Act
        var result = await controller.Register(request);

        // Assert
        result.Should().BeOfType<OkObjectResult>();
        db.Companies.Should().Contain(c => c.Email == "test@co.com");
    }

    /// <summary>
    /// Ensures that registration fails with a BadRequest if the email is already registered.
    /// </summary>
    [Fact]
    public async Task Register_ShouldReturnBadRequest_WhenEmailExists()
    {
        // Arrange
        var db = GetDbContext();
        var controller = new AuthController(db);
        var request = new AuthController.RegisterRequest { Email = "exists@mail.com", Password = "1" };

        await controller.Register(new AuthController.RegisterRequest
        {
            Name = "Existing",
            Email = "exists@mail.com",
            Password = "1"
        });

        // Act
        var result = await controller.Register(request);

        // Assert
        result.Should().BeOfType<BadRequestObjectResult>();
    }
}