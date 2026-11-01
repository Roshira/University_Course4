import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterModule } from '@angular/router';
import { ApiService } from '../api.service';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  template: `
    <div class="auth-page">
      <div class="auth-card">
        <div class="auth-header">
          <div class="logo">🚀</div>
          <h1>Створити акаунт</h1>
          <p>Почніть збирати дані за лічені хвилини</p>
        </div>

        <form (ngSubmit)="onSubmit()" class="auth-form">
          <div class="input-group">
            <label>Назва компанії</label>
            <input type="text" [(ngModel)]="name" name="name" placeholder="ТОВ 'Мій Бізнес'" required>
          </div>

          <div class="input-group">
            <label>Email адреса</label>
            <input type="email" [(ngModel)]="email" name="email" placeholder="ceo@company.com" required>
          </div>

          <div class="input-group">
            <label>Пароль</label>
            <input type="password" [(ngModel)]="password" name="password" placeholder="Мінімум 6 символів" required>
          </div>

          <div class="error-box" *ngIf="error">
            <span>⚠️</span> {{ error }}
          </div>

          <button type="submit" [disabled]="loading" class="submit-btn register-btn">
            {{ loading ? 'Створення...' : 'Зареєструвати компанію' }}
          </button>
        </form>

        <div class="auth-footer">
          <p>Вже є акаунт? <a routerLink="/login">Увійти в панель</a></p>
        </div>
      </div>
    </div>
  `,
  styles: [`
    /* Стилі ідентичні LoginComponent для цілісності дизайну */
    :host { --primary: #10b981; --primary-hover: #059669; --bg: #f9fafb; --text-main: #111827; --text-muted: #6b7280; }
    
    .auth-page { 
      min-height: 100vh; display: flex; align-items: center; justify-content: center; 
      background: radial-gradient(circle at bottom right, #ecfdf5 0%, #f9fafb 100%);
      font-family: 'Inter', sans-serif;
    }

    .auth-card { 
      background: white; width: 100%; max-width: 420px; padding: 40px; 
      border-radius: 20px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1);
      animation: fadeIn 0.6s ease-out;
    }

    @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

    .auth-header { text-align: center; margin-bottom: 32px; }
    .logo { font-size: 40px; margin-bottom: 16px; }
    h1 { font-size: 24px; font-weight: 700; color: var(--text-main); margin: 0; }
    .auth-header p { color: var(--text-muted); margin-top: 8px; }

    .auth-form { display: flex; flex-direction: column; gap: 18px; }
    .input-group { display: flex; flex-direction: column; gap: 6px; }
    .input-group label { font-size: 14px; font-weight: 600; color: #374151; }
    
    input { padding: 12px 16px; border: 1px solid #d1d5db; border-radius: 10px; outline: none; transition: 0.2s; }
    input:focus { border-color: var(--primary); box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.1); }

    .error-box { background: #fef2f2; color: #dc2626; padding: 12px; border-radius: 10px; font-size: 14px; }

    .submit-btn { 
      background: var(--primary); color: white; padding: 14px; border: none; 
      border-radius: 10px; font-size: 16px; font-weight: 600; cursor: pointer;
      transition: all 0.2s; margin-top: 10px;
    }
    .submit-btn:hover { background: var(--primary-hover); transform: translateY(-1px); }
    .submit-btn:active { transform: translateY(0); }

    .auth-footer { text-align: center; margin-top: 24px; padding-top: 24px; border-top: 1px solid #f3f4f6; }
    .auth-footer a { color: var(--primary); font-weight: 600; text-decoration: none; }
  `]
})
export class RegisterComponent {
  name = ''; email = ''; password = ''; error = ''; loading = false;
  constructor(private api: ApiService, private router: Router) {}
  onSubmit() {
    this.loading = true;
    this.api.register({ name: this.name, email: this.email, password: this.password }).subscribe({
      next: () => this.router.navigate(['/login']),
      error: (err) => {
        this.error = err.error?.message || 'Помилка реєстрації';
        this.loading = false;
      }
    });
  }
}