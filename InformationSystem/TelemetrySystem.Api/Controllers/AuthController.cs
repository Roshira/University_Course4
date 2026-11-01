using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using TelemetrySystem.Api.Data;
using TelemetrySystem.Api.Models;
using TelemetrySystem.Api.Observability;

namespace TelemetrySystem.Api.Controllers;

[ApiController]
[Route("api/[controller]")]
public class AuthController : ControllerBase
{
    private const string SecretKey = "SuperSecretKeyForTelemetryDashboard12345!";
    private readonly AppDbContext _db;

    public AuthController(AppDbContext db) { _db = db; }

    public class LoginRequest { public string Email { get; set; } = ""; public string Password { get; set; } = ""; }
    public class RegisterRequest { public string Name { get; set; } = ""; public string Email { get; set; } = ""; public string Password { get; set; } = ""; }

    [HttpPost("register")]
    public async Task<IActionResult> Register([FromBody] RegisterRequest request)
    {
        if (await _db.Companies.AnyAsync(c => c.Email == request.Email))
            return BadRequest(new { Message = "Компанія з таким email вже існує" });

        var company = new Company
        {
            Name = request.Name,
            Email = request.Email,
            PasswordHash = HashPassword(request.Password)
        };

        _db.Companies.Add(company);
        await _db.SaveChangesAsync();

        return Ok(new { Message = "Реєстрація успішна" });
    }

    [HttpPost("login")]
    public async Task<IActionResult> Login([FromBody] LoginRequest request)
    {
        var company = await _db.Companies.FirstOrDefaultAsync(c => c.Email == request.Email);

        if (company != null && company.PasswordHash == HashPassword(request.Password))
        {
            var tokenHandler = new JwtSecurityTokenHandler();
            var key = Encoding.ASCII.GetBytes(SecretKey);
            var tokenDescriptor = new SecurityTokenDescriptor
            {
                Subject = new ClaimsIdentity(new[] {
                    new Claim(ClaimTypes.NameIdentifier, company.Id.ToString()),
                    new Claim("AppId", company.AppId.ToString())
                }),
                Expires = DateTime.UtcNow.AddHours(12),
                SigningCredentials = new SigningCredentials(new SymmetricSecurityKey(key), SecurityAlgorithms.HmacSha256Signature)
            };
            var token = tokenHandler.CreateToken(tokenDescriptor);
            AppMetrics.Logins.WithLabels("success").Inc();
            return Ok(new { Token = tokenHandler.WriteToken(token), AppId = company.AppId });
        }
        AppMetrics.Logins.WithLabels("failure").Inc();
        return Unauthorized(new { Message = "Невірний email або пароль" });
    }

    private string HashPassword(string password)
    {
        using var sha256 = SHA256.Create();
        var bytes = sha256.ComputeHash(Encoding.UTF8.GetBytes(password));
        return Convert.ToBase64String(bytes);
    }
}